import json
import uuid
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import csf
from app.contracts import Draft, ItemInput
from app.db.models import DocumentLine, Item, Questionnaire
from app.draft import check
from app.ingest.store import store_statement
from app.retrieve import retrieve
from app.services.llm_budget import spender
from tests import factories as f
from tests.fakes import FakeLLM

MODELS = {"stance": "m/stance", "draft": "m/draft"}
QUOTE = "Customer data at rest is encrypted with AES-256."


@pytest.fixture
def s(db: Engine) -> Iterator[Session]:
    with Session(db) as session:
        yield session


def _one(tier: str) -> csf.Outcome:
    return next(o for o in csf.framework().outcomes if o.tier == tier)


def test_the_framework_holds_every_outcome_with_its_tier() -> None:
    fw = csf.framework()
    assert (len(fw.outcomes), fw.version) == (106, "2.0")
    assert Counter(o.tier for o in fw.outcomes) == {"checked": 31, "ask": 5, "not_checked": 70}
    assert all(o.question for o in fw.outcomes if o.tier != "not_checked")
    assert all(o.question is None for o in fw.outcomes if o.tier == "not_checked")
    assert fw.get("PR.AA-05").function == "Protect" and "AC-06" in fw.get("PR.AA-05").related_controls
    with pytest.raises(KeyError):
        fw.get("PR.AA-99")


@pytest.mark.parametrize(
    ("label", "value", "want"),
    [
        ("verified", "Yes", "covered"),
        ("partial", "Partial", "partly_covered"),
        ("verified", "No", "not_met"),
        ("conflict", None, "documents_disagree"),
        ("unknown", None, "gap"),
        ("na", None, None),
        (None, None, None),  # not run yet
    ],
)
def test_gap_labels_map_decides_output_as_the_spec_table_says(
    label: str | None, value: str | None, want: str | None
) -> None:
    assert csf.gap_label(_one("checked"), label, value) == want  # type: ignore[arg-type]


def test_ask_me_is_confirmed_only_with_a_stored_statement() -> None:
    ask = _one("ask")
    assert csf.gap_label(ask, "user_confirmed", None, uuid.uuid4()) == "confirmed_by_you"
    assert csf.gap_label(ask, "user_confirmed", None, None) == "not_answered"
    assert csf.gap_label(ask, None) == "not_answered"
    assert (
        csf.gap_label(ask, "verified", "Yes") == "not_answered"
    )  # a document label never confirms an Ask-me
    assert csf.gap_label(_one("checked"), "user_confirmed", None, uuid.uuid4()) == "confirmed_by_you"


def test_not_checked_outcomes_never_carry_a_label() -> None:
    o = _one("not_checked")
    for label, value in (("verified", "Yes"), ("unknown", None), ("user_confirmed", None), (None, None)):
        assert csf.gap_label(o, label, value, uuid.uuid4()) is None  # type: ignore[arg-type]


def test_every_label_has_its_display_words() -> None:
    assert csf.GAP_WORDS == {
        "covered": "Covered",
        "partly_covered": "Partly covered",
        "not_met": "Not met (stated)",
        "documents_disagree": "Documents disagree",
        "gap": "Gap",
        "confirmed_by_you": "Confirmed by you",
        "not_answered": "Not answered",
    }


def test_a_scope_is_the_core_or_one_function() -> None:
    core = csf.in_scope("core")
    assert len(core) == 36 and all(o.tier != "not_checked" for o in core)
    assert {o.function for o in csf.in_scope("protect")} == {"Protect"}
    assert Counter(o.tier for o in csf.in_scope("govern")) == {"checked": 2, "ask": 5}
    for bad in ("Protect", "all", ""):
        with pytest.raises(ValueError, match="unknown scope"):
            csf.in_scope(bad)


def test_an_outcome_is_asked_as_its_question_with_its_category_as_topic() -> None:
    o = csf.framework().get("PR.DS-01")
    assert csf.item_input(o) == ItemInput("PR.DS-01", o.question, "Data Security")
    with pytest.raises(ValueError, match="no question"):
        csf.item_input(_one("not_checked"))


def _load_edited(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, edit: Callable[[list[dict]], None]) -> None:
    raw = json.loads(csf.DATA.read_text(encoding="utf-8"))
    edit(raw["outcomes"])
    bad = tmp_path / "csf.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(csf, "DATA", bad)
    csf.framework.cache_clear()


@pytest.mark.parametrize(
    ("edit", "msg"),
    [
        (lambda os: os[0].update(tier="chekced"), "GV.OC-01: unknown tier"),
        (
            lambda os: os[0].update(tier="checked", question=None),
            "GV.OC-01: a checked outcome needs a question",
        ),
        (lambda os: os[0].update(tier="ask", question="  "), "GV.OC-01: a ask outcome needs a question"),
        (lambda os: os[1].update(id=os[0]["id"]), "GV.OC-01: duplicate id"),
        (lambda os: os[0].update(id="GV.OC-1"), "not a CSF outcome id"),
        (lambda os: os[0].update(function="Govren"), "GV.OC-01: unknown function"),
        (
            lambda os: next(o for o in os if o["tier"] == "checked").update(parts=["  "]),
            "a checked outcome needs parts",
        ),
        (lambda os: os[0].update(parts=["Is it done?"]), "GV.OC-01: only a checked outcome has parts"),
    ],
)
def test_the_loader_rejects_a_bad_data_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, edit: Callable[[list[dict]], None], msg: str
) -> None:
    try:
        _load_edited(monkeypatch, tmp_path, edit)
        with pytest.raises(ValueError, match=msg):
            csf.framework()
    finally:
        monkeypatch.undo()
        csf.framework.cache_clear()


def test_the_built_in_questionnaire_holds_one_item_per_outcome_in_scope(s: Session) -> None:
    ws = f.workspace(s)
    s.commit()
    q = csf.questionnaire_for(s, ws.id, "protect")
    items = s.scalars(select(Item).where(Item.questionnaire_id == q.id).order_by(Item.position)).all()
    want = csf.in_scope("protect")
    assert (q.source, q.filename, q.mapping["scope"], q.mapping["csf_version"]) == (
        "csf",
        "csf-2.0",
        "protect",
        "2.0",
    )
    assert [(i.position, i.code, i.csf_id, i.row_ref) for i in items] == [
        (n, o.id, o.id, o.id) for n, o in enumerate(want, 1)
    ]
    assert [(i.topic, i.question) for i in items] == [(o.category, o.question) for o in want]


def test_the_questionnaire_is_reused_per_scope(s: Session) -> None:
    ws = f.workspace(s)
    s.commit()
    first = csf.questionnaire_for(s, ws.id, "core").id
    assert csf.questionnaire_for(s, ws.id, "core").id == first
    assert csf.questionnaire_for(s, ws.id, "detect").id != first
    other = f.workspace(s)
    s.commit()
    assert csf.questionnaire_for(s, other.id, "core").id != first  # never another workspace's
    assert s.scalar(select(func.count(Questionnaire.id))) == 3


def test_a_later_mapping_key_does_not_hide_the_questionnaire(s: Session) -> None:
    ws = f.workspace(s)
    s.commit()
    q = csf.questionnaire_for(s, ws.id, "core")
    q.mapping = {**q.mapping, "confirmed": True}  # Plan 3 adds keys to a mapping
    s.commit()
    assert csf.questionnaire_for(s, ws.id, "core").id == q.id
    assert s.scalar(select(func.count(Questionnaire.id))) == 1


def test_a_changed_tier_list_gives_a_new_questionnaire(s: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = f.workspace(s)
    s.commit()
    first = csf.questionnaire_for(s, ws.id, "govern").id
    fw = csf.framework()
    reworded = replace(
        fw,
        outcomes=tuple(
            replace(o, question="Is the policy approved?") if o.id == "GV.PO-01" else o for o in fw.outcomes
        ),
    )
    monkeypatch.setattr(csf, "framework", lambda: reworded)
    q = csf.questionnaire_for(s, ws.id, "govern")
    assert q.id != first
    asked = s.scalar(select(Item.question).where(Item.questionnaire_id == q.id, Item.csf_id == "GV.PO-01"))
    assert asked == "Is the policy approved?"
    first = q.id
    recut = replace(
        reworded,
        outcomes=tuple(
            replace(o, parts=("Is the policy approved?",)) if o.id == "GV.PO-01" else o
            for o in reworded.outcomes
        ),
    )
    monkeypatch.setattr(csf, "framework", lambda: recut)
    assert (
        csf.questionnaire_for(s, ws.id, "govern").id != first
    )  # a changed part alone gives a new questionnaire


def test_an_unknown_scope_creates_nothing(s: Session) -> None:
    ws = f.workspace(s)
    s.commit()
    with pytest.raises(ValueError, match="unknown scope"):
        csf.questionnaire_for(s, ws.id, "Protect")
    assert s.scalar(select(func.count(Questionnaire.id))) == 0


def test_a_checked_outcome_runs_the_ordinary_pipeline(s: Session) -> None:
    ws = f.workspace(s)
    doc = f.document(s, ws, filename="crypto-policy.docx")
    f.chunk(s, doc, line_start=4, line_end=4, text=QUOTE)
    s.commit()
    yes = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": QUOTE, "note": "states it"}]})
    nothing = json.dumps({"passages": [{"passage": 1, "stance": "irrelevant", "quote": "", "note": "other"}]})
    llm = FakeLLM([yes, nothing, nothing])  # confidentiality, integrity, availability
    o = csf.framework().get("PR.DS-01")
    r = csf.check_outcome(s, ws.id, o, llm, MODELS, spender(s, ws.id))
    assert r is not None and r.item == csf.item_input(o)
    assert csf.gap_label(o, r.decision.label, r.decision.value) == "partly_covered"
    assert [req.step for req in llm.requests] == ["stance"] * 3
    text = f'Evidenced: part 1. No evidence: parts 2, 3. {o.parts[0]} Yes. The crypto policy says: "{QUOTE}"'
    assert r.draft == Draft(text, "template")
    # M4: every quote in the explanation is a cited line (the part numbers are code's, not evidence)
    assert [p for p in check(r.draft.text, r.decision, ["crypto-policy.docx"]) if p.startswith("quote")] == []


def test_ask_me_and_not_checked_outcomes_never_reach_a_model(s: Session) -> None:
    ws = f.workspace(s)
    doc = f.document(s, ws)
    f.chunk(s, doc, text="Leadership sets the cybersecurity risk tolerance every year.")
    s.commit()
    llm = FakeLLM([])  # any model call raises AssertionError
    ask = next(o for o in csf.framework().outcomes if o.tier == "ask")
    assert csf.check_outcome(s, ws.id, ask, llm, MODELS, spender(s, ws.id)) is None
    unchecked = next(o for o in csf.framework().outcomes if o.tier == "not_checked")
    with pytest.raises(ValueError, match="not checked"):
        csf.check_outcome(s, ws.id, unchecked, llm, MODELS, spender(s, ws.id))
    assert llm.requests == []


def test_ask_me_outcomes_are_queued_once_and_an_answer_confirms_them(s: Session) -> None:
    core = csf.in_scope("core")
    queue = csf.ask_queue(core, {})
    assert [e.key for e in queue] == [o.id for o in core if o.tier == "ask"]
    assert all(e.reason == "unknown" and e.question == csf.framework().get(e.key).question for e in queue)
    assert "GV.RR-02" not in [e.key for e in csf.ask_queue(core, {"GV.RR-02": 1})]  # asked once already

    ws = f.workspace(s)
    s.commit()
    o = csf.framework().get("GV.RR-02")
    doc = store_statement(
        s,
        ws.id,
        "Dana Ortiz, Head of Security, owns the program.",
        filename="answer-GV.RR-02.txt",
        today=date(2026, 10, 5),
    )
    lines = s.scalars(select(DocumentLine.text).where(DocumentLine.document_id == doc.id)).all()
    assert doc.kind == "statement" and "Dana Ortiz" not in " ".join(lines)  # redacted before storage
    assert csf.gap_label(o, "user_confirmed", None, doc.id) == "confirmed_by_you"


def test_a_checked_outcome_is_judged_on_documents_never_on_a_stored_answer(s: Session) -> None:
    """Ruling 9: a visitor's Ask-me answer about the same topic is no evidence for a Checked outcome; it is
    never a candidate, so it takes no passage slot (6B adversary-1 I4; it was a 'statement' drop before).
    (It reaches Checked outcomes only as a 6B suggestion.)"""
    ws = f.workspace(s)
    s.commit()
    statement = store_statement(
        s,
        ws.id,
        "All customer data at rest is encrypted with AES-256 in our vendor portal.",
        filename="answer-GV.SC-01.txt",
        today=date(2026, 10, 5),
    )
    quote = "All customer data at rest is encrypted with AES-256 in our vendor portal."
    stance = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": quote, "note": "states it"}]})
    llm = FakeLLM([stance, json.dumps({"text": f'Yes. "{quote}"'})])
    o = csf.framework().get("PR.DS-01")
    r = csf.check_outcome(s, ws.id, o, llm, MODELS, spender(s, ws.id))
    assert r is not None and r.decision.citations == () and r.retrieval.passages == ()
    assert r.decision.dropped == () and r.retrieval.dropped == ()
    plain = retrieve(s, ws.id, csf.part_inputs(o)[0].question, o.category)  # what it would have taken
    assert [p.doc.id for p in plain.passages] == [str(statement.id)]
    assert csf.gap_label(o, r.decision.label, r.decision.value) == "gap" and llm.requests == []
