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
    stored: dict[str, list[str]] = {"s1": ["Kestrelyn follows HIPAA."]}
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
    labels["GV.OC-03"] = "confirmed_by_you"
    return gap.GapObserved(
        results=results,
        labels=labels,
        items=[o.id for o in csf.in_scope("core")],
        statements={"GV.OC-03": "s1"},
        kinds={"s1": "statement"},
        doc_ids={d.id: f"d-{d.id}" for d in pack.facts.documents},
        stored=stored,
        leaks=0,
        private=4,
        nist={o.id: gap.shown(o) for o in csf.framework().outcomes},
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


@pytest.mark.parametrize("doc", ["template", "statement", "draft"])
def test_a_covered_answer_citing_a_template_a_statement_or_only_a_draft_fails_trap_coverage(doc: str) -> None:
    """decide drops a citation of a document the classifier marked not evidence, and caps an all-draft answer;
    this gate judges by the fact sheet's truth, so a misclassified template or draft is still caught. A
    statement is no fact-sheet document: a Checked answer citing one broke Ruling 1."""
    pack = gap.load()
    obs = _perfect(pack)
    if doc == "statement":
        target = "s1"
    else:
        target = next(
            obs.doc_ids[d.id]
            for d in pack.facts.documents
            if (not d.evidence_allowed if doc == "template" else d.status == "draft" and d.evidence_allowed)
        )
    m = gap.score_gap(pack, _with(obs, "PR.DS-01", _covered_citing(pack, target)))
    assert m["trap_coverage"] == 1.0


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
    unanswered = replace(obs, labels={**obs.labels, "GV.OV-01": "confirmed_by_you"})
    assert gap.score_gap(pack, unanswered)["honest_tiers"] < 1
    not_checked = replace(obs, items=[*obs.items, "GV.OC-01"])  # a not-checked outcome as an item
    assert gap.score_gap(pack, not_checked)["honest_tiers"] < 1
    assert gap.score_gap(pack, replace(obs, kinds={"s1": "policy"}))["honest_tiers"] < 1  # not a statement
    assert gap.score_gap(pack, replace(obs, stored={**obs.stored, "s1": []}))["honest_tiers"] < 1  # no lines
    labelled = replace(obs, labels={**obs.labels, "GV.OC-01": "covered"})  # not checked, with a label
    assert gap.score_gap(pack, labelled)["honest_tiers"] < 1
    ask_run = _with(obs, "GV.OV-01", UNKNOWN)  # an Ask-me outcome sent through the engine
    assert gap.score_gap(pack, ask_run)["honest_tiers"] < 1


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
    pack = replace(gap.load(), keys={}, nist={}, tiers={})
    obs = replace(_perfect(gap.load()), results={}, private=0)
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
    """Ruling 1: real ingest, questionnaire, retrieval and statements; only the model steps are replaced by
    citing every retrieved passage. A statement stored mid-run would be retrievable evidence for the Checked
    outcomes after it."""
    events: list[tuple[str, str]] = []
    cited: set[str] = set()

    def check(session: Session, ws: uuid.UUID, o: csf.Outcome, llm: Any, models: Any, spend: Any) -> Any:
        if o.tier == "ask":
            return None
        events.append(("check", o.id))
        r = retrieve(session, ws, o.question or "", o.category)
        cites = tuple(
            Citation(p.chunk_id, p.doc.id, p.doc.filename, p.line_start, p.line_start, p.lines[0], "yes")
            for p in r.passages
        )
        cited.update(c.document_id for c in cites)
        decision = Decision("verified", "Yes", cites, (), None, None, 0.9)
        return ItemResult(csf.item_input(o), r, (), decision, Draft("", "none"), 0.0, 0)

    statement_ids: list[str] = []

    def store(session: Session, ws: uuid.UUID, text: str, *, filename: str, today: date) -> Document:
        events.append(("store", filename))
        doc = store_statement(session, ws, text, filename=filename, today=today)
        statement_ids.append(str(doc.id))
        return doc

    monkeypatch.setattr(csf, "check_outcome", check)
    monkeypatch.setattr(gap, "store_statement", store)
    report = gap.run(FakeLLM([]), MODELS)  # every dev document classifies by rules: no model call

    kinds = [k for k, _ in events]
    assert kinds == ["check"] * 31 + ["store"] * 4
    assert cited and not cited & set(statement_ids)
    assert report["metrics"]["honest_tiers"] == 1.0 and report["metrics"]["redaction_private_leaks"] == 0.0


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
