import json
import uuid
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app import csf
from app.contracts import Citation, Decision, Draft, ItemInput, ItemResult, Retrieval
from app.db.models import Document, Workspace
from app.ingest.store import store_statement
from app.retrieve import retrieve
from evals import gap, run, score
from tests.fakes import FakeLLM

MODELS = {"stance": "m/s", "draft": "m/d", "classify": "m/c", "judge": "m/j", "recheck": "m/r"}
UNKNOWN = Decision("unknown", None, (), (), None, None, 0.0)


def _result(code: str, decision: Decision) -> ItemResult:
    item = ItemInput(code, "q", None)
    return ItemResult(item, Retrieval((), ()), (), decision, Draft("", "none"), 0.01, 1000)


def _perfect(pack: gap.GapPack) -> gap.GapObserved:
    """What a flawless engine would produce: each key's label, citing each key quote from a stored line."""
    results: dict[str, ItemResult] = {}
    statements = {o: f"s-{o}" for o in pack.answers}
    stored: dict[str, list[str]] = {
        sid: ["<PERSON> answered; reach <PERSON> at <PHONE>."] for sid in statements.values()
    }
    for code, k in pack.keys.items():
        cites = []
        for e in k.evidence:
            lines = stored.setdefault(f"d-{e.doc}", [])
            lines.append(e.quote)
            cites.append(Citation("c", f"d-{e.doc}", e.doc, len(lines), len(lines), e.quote, e.stance))
        cited = tuple(cites) if k.expected_label != "unknown" else ()
        decision = Decision(k.expected_label, k.expected_value, cited, (), None, None, 0.9)
        results[code] = _result(code, decision)
    labels = {o.id: csf.gap_label(o, None) for o in csf.framework().outcomes}
    labels.update({o: "confirmed_by_you" for o in statements})
    return gap.GapObserved(
        results=results,
        labels=labels,
        items=[o.id for o in csf.in_scope("core")],
        statements=statements,
        kinds={sid: "statement" for sid in statements.values()},
        doc_ids={d.id: f"d-{d.id}" for d in pack.facts.documents},
        stored=stored,
        nist={o.id: gap.shown(o) for o in csf.framework().outcomes},
        requests=["Passage 1: Dana Ortiz owns the security program."],  # sample documents name people
        probe_kept=0,
        probe_seen=2,
    )


def _with(obs: gap.GapObserved, code: str, decision: Decision) -> gap.GapObserved:
    return replace(obs, results={**obs.results, code: _result(code, decision)})


def _covered_citing(pack: gap.GapPack, doc_id: str) -> Decision:
    quote = pack.keys["PR.DS-01"].evidence[0].quote
    return Decision("verified", "Yes", (Citation("c", doc_id, "x", 1, 1, quote, "yes"),), (), None, None, 0.9)


def test_a_flawless_run_passes_every_gate() -> None:
    pack = gap.load()
    m = gap.score_gap(pack, _perfect(pack))
    assert all(g["pass"] for g in score.gates(m, gap.GATES).values()), m
    assert m["label_accuracy"] == 1.0 and m["cost_usd_per_core_run"] == 0.31  # 31 results at 0.01 USD


def test_a_trap_outcome_shown_as_covered_fails_trap_coverage() -> None:
    pack = gap.load()
    obs = _perfect(pack)
    draft_only = obs.results["RS.MA-01"].decision
    obs = _with(obs, "RS.MA-01", replace(draft_only, label="verified", value="Yes"))
    m = gap.score_gap(pack, obs)
    assert m["trap_coverage"] == 1.0 and not score.gates(m, gap.GATES)["trap_coverage"]["pass"]


def test_trap_coverage_is_measured_where_a_planned_only_sentence_is_the_only_mention() -> None:
    """Task 5 review carry: trap G4 is planned-only on DE.AE-06, which also has a final yes, so DE.AE-06 is
    not a trap outcome (it is a planted disagreement). The planned-only kind is measured on ID.RA-02 and
    DE.AE-07, whose controls no other statement speaks to."""
    pack = gap.load()
    traps = gap.trap_outcomes(pack)
    assert traps == ["ID.RA-02", "PR.IR-04", "DE.AE-07", "RS.MA-01", "RS.CO-02"]
    planned = {s for t in pack.facts.traps if t.kind == "planned_only" for s in t.statements}
    for code in ("ID.RA-02", "DE.AE-07"):
        assert {s.id for s in pack.facts.statements_for(pack.control[code])} <= planned
    covered = Decision("verified", "Yes", (), (), None, None, 0.9)
    m = gap.score_gap(pack, _with(_perfect(pack), "DE.AE-07", covered))
    assert m["trap_coverage"] == 1.0


@pytest.mark.parametrize("doc", ["template", "draft"])
def test_a_covered_answer_citing_a_template_or_only_a_draft_fails_trap_coverage(doc: str) -> None:
    """decide drops a citation of a document the classifier marked not evidence, and caps an all-draft answer;
    this gate judges by the fact sheet's truth, so a misclassified template or draft is still caught."""
    pack = gap.load()
    obs = _perfect(pack)
    target = next(
        obs.doc_ids[d.id]
        for d in pack.facts.documents
        if (not d.evidence_allowed if doc == "template" else d.status == "draft" and d.evidence_allowed)
    )
    m = gap.score_gap(pack, _with(obs, "PR.DS-01", _covered_citing(pack, target)))
    assert m["trap_coverage"] == 1.0


@pytest.mark.parametrize(("code", "label"), [("ID.AM-03", "verified"), ("PR.AA-06", "partial")])
def test_an_honest_gap_shown_covered_or_partly_on_an_unrelated_line_fails_trap_coverage(
    code: str, label: str
) -> None:
    """Adversary I1: cited_coverage only re-reads the quote; nothing else stops 'never mentioned' turning
    Covered on a real but unrelated line."""
    pack = gap.load()
    obs = _perfect(pack)
    unrelated = obs.results["ID.AM-08"].decision.citations
    value = "Yes" if label == "verified" else "Partial"
    m = gap.score_gap(pack, _with(obs, code, Decision(label, value, unrelated, (), None, None, 0.9)))  # type: ignore[arg-type]
    assert m["trap_coverage"] == 1.0 and m["cited_coverage"] == 1.0


def test_a_missed_disagreement_and_a_missed_non_compliance_fail_their_recall() -> None:
    pack = gap.load()
    obs = _with(_with(_perfect(pack), "PR.AA-05", UNKNOWN), "ID.RA-02", UNKNOWN)
    m = gap.score_gap(pack, obs)
    assert (m["disagreements_caught"], m["stated_noncompliance"]) == (0.5, 0.5)
    assert gap.misses(pack, obs) == [
        "ID.RA-02: expected not_met, got gap",
        "PR.AA-05: expected documents_disagree, got gap",
    ]


def test_an_ask_me_label_without_a_statement_fails_honest_tiers() -> None:
    pack = gap.load()
    obs = _perfect(pack)
    sid = obs.statements["GV.RR-02"]
    unanswered = replace(obs, labels={**obs.labels, "GV.OV-01": "confirmed_by_you"})
    assert gap.score_gap(pack, unanswered)["honest_tiers"] < 1
    not_checked = replace(obs, items=[*obs.items, "GV.OC-01"])  # a not-checked outcome as an item
    assert gap.score_gap(pack, not_checked)["honest_tiers"] < 1
    assert gap.score_gap(pack, replace(obs, kinds={**obs.kinds, sid: "policy"}))["honest_tiers"] < 1
    assert gap.score_gap(pack, replace(obs, stored={**obs.stored, sid: []}))["honest_tiers"] < 1  # no lines
    labelled = replace(obs, labels={**obs.labels, "GV.OC-01": "covered"})  # not checked, with a label
    assert gap.score_gap(pack, labelled)["honest_tiers"] < 1
    ask_run = _with(obs, "GV.OV-01", UNKNOWN)  # an Ask-me outcome sent through the engine
    assert gap.score_gap(pack, ask_run)["honest_tiers"] < 1


def test_ask_me_outcomes_that_were_answered_but_never_stored_or_asked_fail_honest_tiers() -> None:
    """Review I1: the fixture, not what the run stored, says which Ask-me outcomes must show Confirmed by you;
    and every Ask-me outcome must be an item of the questionnaire."""
    pack = gap.load()
    obs = _perfect(pack)
    labels = {**obs.labels, **dict.fromkeys(pack.answers, "not_answered")}
    nothing_stored = replace(obs, statements={}, kinds={}, labels=labels)
    m = gap.score_gap(pack, nothing_stored)
    assert m["honest_tiers"] is not None and m["honest_tiers"] < 1
    assert m["redaction_private_leaks"] is None  # nothing stored: the redaction gate has nothing to measure
    no_ask_items = replace(obs, items=[i for i in obs.items if pack.tiers[i] != "ask"])
    assert gap.score_gap(pack, no_ask_items)["honest_tiers"] < 1


def test_redaction_scans_statements_for_every_name_word_and_requests_for_what_no_document_holds() -> None:
    pack = gap.load()
    assert {"Dana", "Ortiz", "Tomas Brandt", "+1 512 555 0187", "dana.ortiz@kestrelyn.example"} <= set(
        pack.private
    )
    assert "Tomas Brandt" in pack.unseen and "Dana Ortiz" not in pack.unseen  # sample documents name Dana
    obs = _perfect(pack)
    sid = obs.statements["GV.RR-02"]
    first_name = replace(
        obs, stored={**obs.stored, sid: ["<PERSON>, Head of Security. Reach Dana at <PHONE>."]}
    )
    assert gap.score_gap(pack, first_name)["redaction_private_leaks"] == 1.0
    for leaked in (
        "Ask Tomas Brandt, our risk analyst.",
        "Call +1 512 555 0187.",
        "key sk9Kestrel" + "2026xQ",
    ):
        m = gap.score_gap(pack, replace(obs, requests=[*obs.requests, leaked]))
        assert m["redaction_private_leaks"] >= 1, leaked
    assert not score.gates(gap.score_gap(pack, first_name), gap.GATES)["redaction_private_leaks"]["pass"]


def test_a_checked_outcome_judged_on_a_statement_fails_statements_as_evidence() -> None:
    pack = gap.load()
    obs = _perfect(pack)
    assert gap.score_gap(pack, replace(obs, probe_kept=1))["statements_as_evidence"] == 1.0
    cites = (Citation("c", obs.statements["GV.SC-01"], "answer-GV.SC-01.txt", 1, 1, "x", "yes"),)
    m = gap.score_gap(pack, _with(obs, "PR.DS-01", Decision("verified", "Yes", cites, (), None, None, 0.9)))
    assert m["statements_as_evidence"] == 1.0
    assert gap.score_gap(pack, replace(obs, probe_seen=0))["statements_as_evidence"] is None


@pytest.mark.parametrize(
    ("answers", "message"),
    [({"GV.OC-3": "Dana Ortiz owns it."}, "not an Ask-me outcome: GV.OC-3"), ({}, "planted strings missing")],
)
def test_a_fixture_typo_stops_the_load_instead_of_dropping_a_planted_string(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, answers: dict[str, str], message: str
) -> None:
    path = tmp_path / "gap-dev-answers.json"
    path.write_text(json.dumps(answers))
    monkeypatch.setattr(gap, "ANSWERS", path)
    with pytest.raises(ValueError, match=message):
        gap.load()


def test_nist_text_intact_fails_on_a_changed_outcome_or_a_failing_drift_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack = gap.load()
    obs = _perfect(pack)
    changed = {**obs.nist["PR.DS-01"], "outcome": "Data is encrypted"}
    assert gap.score_gap(pack, replace(obs, nist={**obs.nist, "PR.DS-01": changed}))["nist_text_intact"] < 1
    missing = {k: v for k, v in obs.nist.items() if k != "GV.OC-01"}
    assert gap.score_gap(pack, replace(obs, nist=missing))["nist_text_intact"] < 1
    monkeypatch.setattr(gap.csf_data, "check", lambda: ["csf-2.0.json is stale"])
    assert gap.score_gap(pack, obs)["nist_text_intact"] == 0.0


def test_gates_fail_closed_when_there_is_nothing_to_measure() -> None:
    pack = replace(gap.load(), keys={}, nist={}, tiers={}, answers={})
    obs = replace(_perfect(gap.load()), results={}, probe_seen=0)
    g = score.gates(gap.score_gap(pack, obs), gap.GATES)
    assert set(g) == set(gap.GATES)
    for name in gap.GATES:
        assert g[name]["value"] is None and not g[name]["pass"] and "nothing to measure" in g[name]["reason"]


def test_a_key_outcome_without_a_result_stops_the_scoring() -> None:
    pack = gap.load()
    obs = _perfect(pack)
    with pytest.raises(ValueError, match="PR.DS-01"):
        gap.score_gap(pack, replace(obs, results={c: r for c, r in obs.results.items() if c != "PR.DS-01"}))


def test_run_answers_checked_outcomes_stores_ask_answers_and_deletes_its_workspace(
    db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = gap.load()
    with Session(db) as s:
        other = Workspace()
        s.add(other)
        s.commit()
        bystander = other.id
    loaded: list[str] = []

    def ingest(session: Session, ws: uuid.UUID, filename: str, data: bytes, **kw: Any) -> Document:
        assert kw["source"] == "sample" and kw["spend"] is gap.always
        loaded.append(filename)
        d = Document(workspace_id=ws, filename=filename, source="sample", sha256="0" * 64, kind="policy")
        session.add(d)
        session.commit()
        return d

    def check(session: Any, ws: Any, o: csf.Outcome, llm: Any, models: Any, spend: Any) -> ItemResult | None:
        assert spend is gap.always
        return None if o.tier == "ask" else _result(o.id, UNKNOWN)

    monkeypatch.setattr(gap, "ingest_document", ingest)
    monkeypatch.setattr(csf, "check_outcome", check)
    llm = FakeLLM([])
    report = gap.run(llm, MODELS)

    assert loaded == [d.filename for d in pack.facts.documents]  # the 22 dev documents, then the plan
    assert sorted(report["items"]) == sorted(pack.keys) and llm.requests == []
    m = report["metrics"]
    assert (m["honest_tiers"], m["redaction_private_leaks"], m["nist_text_intact"]) == (1.0, 0.0, 1.0)
    assert m["label_accuracy"] == round(3 / 31, 4)  # only the three planted gaps are right
    assert set(report["gates"]) == set(gap.GATES) and set(report["models"]) == {"stance", "draft"}
    with Session(db) as s:
        assert s.scalars(select(Workspace.id)).all() == [bystander]


def test_the_real_loop_answers_every_checked_outcome_before_storing_an_ask_me_answer(
    db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ruling 1: real ingest, questionnaire, statements, redaction and the Ruling 9 probe; only the Checked
    outcomes' model steps are stubbed."""
    events: list[tuple[str, str]] = []

    def check(session: Session, ws: uuid.UUID, o: csf.Outcome, llm: Any, models: Any, spend: Any) -> Any:
        if o.tier == "ask":
            return None
        events.append(("check", o.id))
        return _result(o.id, UNKNOWN)

    def store(session: Session, ws: uuid.UUID, text: str, *, filename: str, today: date) -> Document:
        events.append(("store", filename))
        return store_statement(session, ws, text, filename=filename, today=today)

    monkeypatch.setattr(csf, "check_outcome", check)
    monkeypatch.setattr(gap, "store_statement", store)
    report = gap.run(FakeLLM([]), MODELS)  # every dev document classifies by rules: no model call

    kinds = [k for k, _ in events]
    assert kinds == ["check"] * 31 + ["store"] * 4  # Ruling 1, defence in depth behind Ruling 9
    m = report["metrics"]
    assert (m["honest_tiers"], m["redaction_private_leaks"], m["statements_as_evidence"]) == (1.0, 0.0, 0.0)
    assert report["gates"]["statements_as_evidence"]["pass"]  # measured: the probe found stored answers


def test_the_statements_gate_fires_on_the_real_loop_when_answers_are_not_kept_out(
    db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def check(session: Session, ws: uuid.UUID, o: csf.Outcome, llm: Any, models: Any, spend: Any) -> Any:
        return None if o.tier == "ask" else _result(o.id, UNKNOWN)

    monkeypatch.setattr(csf, "check_outcome", check)
    monkeypatch.setattr(csf, "evidence", lambda s, ws, o: retrieve(s, ws, o.question or "", o.category))
    report = gap.run(FakeLLM([]), MODELS)
    assert report["metrics"]["statements_as_evidence"] >= 1
    assert not report["gates"]["statements_as_evidence"]["pass"]


@pytest.mark.parametrize(("passing", "code"), [(True, 0), (False, 1)])
def test_main_writes_the_gap_pack_to_its_own_results_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, passing: bool, code: int
) -> None:
    monkeypatch.setattr(run, "RESULTS", tmp_path)
    monkeypatch.setattr(run, "RECORDED", tmp_path)
    metrics = {"label_accuracy": 0.9 if passing else 0.5}
    report = {
        "pack": "gap-dev",
        "models": {},
        "prompts": [],
        "metrics": metrics,
        "gates": score.gates(metrics, {"label_accuracy": (">=", 0.8)}),
        "label_misses": [],
    }
    monkeypatch.setattr(gap, "run", lambda llm, models: report)
    assert run.main(["--pack", "gap-dev"]) == code
    assert json.loads((tmp_path / "gap-dev.json").read_text())["pack"] == "gap-dev"
    assert (tmp_path / "gap-dev.md").read_text().startswith("# Eval results: gap-dev pack")
    assert not (tmp_path / "latest.json").exists()
