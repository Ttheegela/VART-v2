import json
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import Engine, delete, select, update
from sqlalchemy.orm import Session

from app import csf, runs
from app import questions as qs
from app.contracts import BudgetExhausted
from app.db.models import Answer, Chunk, Document, Item, Run, RunItem, SuggestedFill
from app.ingest.store import store_statement
from app.llm.client import LLMError, LLMRequest, LLMResult
from app.redecide import redecide
from app.services import llm_budget
from tests import factories as f
from tests.fakes import ByStepLLM

MODELS = {"stance": "m/stance", "draft": "m/draft", "classify": "m/c", "recheck": "m/stance", "judge": "m/j"}
LINE = "Backups of data are created, protected, maintained and tested every day."
YES = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": LINE, "note": "states it"}]})


@pytest.fixture
def s(db: Engine) -> Iterator[Session]:
    with Session(db) as session:
        yield session


def _backups(s: Session):  # type: ignore[no-untyped-def]
    """A gap-check run over PR.DS-11 alone (four parts) with one policy line that every part retrieves."""
    ws = f.workspace(s)
    f.chunk(s, f.document(s, ws, filename="backup-policy.docx"), line_start=2, line_end=2, text=LINE)
    q = f.questionnaire(s, ws, source="csf", filename="csf-2.0")
    o = csf.framework().get("PR.DS-11")
    it = f.item(s, q, csf_id=o.id, code=o.id, row_ref=o.id, topic=o.category, question=o.question)
    s.commit()
    return ws, it, runs.create_run(s, ws.id, q.id, MODELS)


def _parts_of(s: Session, run_id: object) -> RunItem:
    s.expire_all()
    return s.scalars(select(RunItem).where(RunItem.run_id == run_id)).one()


def _reopen(s: Session, run: Run, parts: dict[str, object]) -> None:
    """The outcome back to pending with these stored parts, as a re-open leaves it."""
    s.execute(delete(Answer).where(Answer.run_id == run.id))
    s.execute(update(RunItem).where(RunItem.run_id == run.id).values(parts=parts, state="pending"))
    s.execute(update(Run).where(Run.id == run.id).values(status="running", finished_at=None))
    s.commit()


def test_a_gap_step_claims_outcomes_until_their_parts_add_up_to_eight(s: Session) -> None:
    ws = f.workspace(s)
    s.commit()
    q = csf.questionnaire_for(s, ws.id, "core")
    run = runs.create_run(s, ws.id, q.id, MODELS)
    llm = ByStepLLM({})  # no documents: no part has a passage, so a call would be a KeyError here
    weight = {o.id: max(1, len(o.parts)) for o in csf.in_scope("core")}
    first = runs.step(s, ws.id, run.id, llm, MODELS)
    # 1 + 1 + 1 + 3 parts; GV.PO-02's 4 would make 10
    assert [s.get_one(Item, i).csf_id for i in first] == ["GV.OC-03", "GV.RM-02", "GV.RR-02", "GV.PO-01"]
    steps = [first]
    while answered := runs.step(s, ws.id, run.id, llm, MODELS):
        steps.append(answered)
    for answered in steps:
        total = sum(weight[s.get_one(Item, i).csf_id or ""] for i in answered)
        assert total <= runs.STEP_PARTS or len(answered) == 1
    assert sum(len(a) for a in steps) == 36 and llm.requests == []
    ask = s.scalars(
        select(Answer).join(Item, Item.id == Answer.item_id).where(Item.csf_id == "GV.OC-03")
    ).one()
    assert (ask.label, ask.text, ask.citations) == ("unknown", "", [])
    o = csf.framework().get("GV.OC-03")
    assert csf.gap_label(o, "unknown", None, ask.statement_id) == "not_answered"


def test_a_refused_budget_keeps_the_paid_parts_and_the_next_step_pays_only_the_rest(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, it, run = _backups(s)
    monkeypatch.setitem(llm_budget.CAPS, "stance", 2)
    llm = ByStepLLM({"stance": YES}, cost=0.001)
    with pytest.raises(BudgetExhausted):
        runs.step(s, ws.id, run.id, llm, MODELS)
    ri = _parts_of(s, run.id)
    assert (sorted(ri.parts), ri.state, ri.attempts) == (["1", "2"], "pending", 0)
    assert s.scalar(select(Answer).where(Answer.run_id == run.id)) is None  # no outcome row until it is whole
    monkeypatch.setitem(llm_budget.CAPS, "stance", 10)
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert [q.item_id for q in llm.requests] == [f"PR.DS-11#{n}" for n in (1, 2, 3, 4)]  # each part paid once
    a = s.scalars(select(Answer).where(Answer.run_id == run.id)).one()
    assert (a.label, a.value, a.stances) == ("verified", "Yes", [])
    assert a.text.startswith("Evidenced: parts 1, 2, 3, 4.")
    assert a.chunk_ids == _parts_of(s, run.id).parts["1"]["chunk_ids"]  # the parts' union: one chunk here
    s.refresh(run)
    assert (run.status, float(run.cost_usd)) == ("done", pytest.approx(0.004))


def test_a_stored_part_with_other_wording_is_run_again(s: Session) -> None:
    ws, it, run = _backups(s)
    llm = ByStepLLM({"stance": YES})
    runs.step(s, ws.id, run.id, llm, MODELS)
    stored = dict(_parts_of(s, run.id).parts)
    stored["2"] = {**stored["2"], "question": "Are backups of data kept somewhere safe?"}  # an older cut
    _reopen(s, run, stored)
    llm.requests.clear()
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert [q.item_id for q in llm.requests] == ["PR.DS-11#2"]
    assert _parts_of(s, run.id).parts["2"]["question"] == csf.framework().get("PR.DS-11").parts[1]


def test_a_stored_part_judged_by_another_model_or_prompt_is_run_again(s: Session) -> None:
    ws, it, run = _backups(s)
    llm = ByStepLLM({"stance": YES})
    runs.step(s, ws.id, run.id, llm, MODELS)
    stored = dict(_parts_of(s, run.id).parts)
    assert (stored["1"]["stance_prompt"], stored["1"]["model"]) == ("stance@p3", MODELS["stance"])
    stored["3"] = {
        **stored["3"],
        "model": "old/stance-model",
    }  # judged before a model change (adversary-1 M5)
    stored["4"] = {**stored["4"], "stance_prompt": "stance@p2"}  # and before a prompt change
    _reopen(s, run, stored)
    llm.requests.clear()
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert [q.item_id for q in llm.requests] == ["PR.DS-11#3", "PR.DS-11#4"]


def test_a_step_past_its_deadline_releases_the_outcome_and_keeps_its_parts(s: Session) -> None:
    ws, it, run = _backups(s)
    llm = ByStepLLM({"stance": YES})
    late = lambda: 0.0 if len(llm.requests) < 2 else 1e9  # noqa: E731 - the deadline passes after part 2
    assert runs.step(s, ws.id, run.id, llm, MODELS, clock=late) == []
    ri = _parts_of(s, run.id)
    assert (sorted(ri.parts), ri.state, ri.attempts) == (["1", "2"], "pending", 0)
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert [q.item_id for q in llm.requests] == [f"PR.DS-11#{n}" for n in (1, 2, 3, 4)]


def test_a_failed_outcome_keeps_its_paid_parts_and_says_it_failed(s: Session) -> None:
    ws, it, run = _backups(s)

    class FailsAfterOne(ByStepLLM):
        def complete(self, req: LLMRequest) -> LLMResult:
            if self.requests:
                self.requests.append(req)
                raise LLMError("the reply did not match the schema")
            return super().complete(req)

    llm = FailsAfterOne({"stance": YES})
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert [q.item_id for q in llm.requests] == ["PR.DS-11#1", "PR.DS-11#2", "PR.DS-11#2"]  # retried once
    a = s.scalars(select(Answer).where(Answer.run_id == run.id)).one()
    assert (a.label, a.text) == ("unknown", runs.FAILED_TEXT)  # what a re-open and the gap view look for
    assert sorted(_parts_of(s, run.id).parts) == ["1"]


def test_an_outcome_id_the_data_no_longer_has_is_answered_as_a_question(s: Session) -> None:
    ws = f.workspace(s)
    q = f.questionnaire(s, ws, source="csf", filename="csf-2.0")
    it = f.item(s, q, csf_id="GV.ZZ-99", code="GV.ZZ-99", question="Is a withdrawn outcome met?")
    s.commit()
    run = runs.create_run(s, ws.id, q.id, MODELS)
    assert runs.step(s, ws.id, run.id, ByStepLLM({}), MODELS) == [it.id]  # adversary-1 N1: no 500
    assert s.scalars(select(Answer.label).where(Answer.run_id == run.id)).one() == "unknown"


def test_no_transaction_is_open_while_a_part_runs(s: Session) -> None:
    ws, it, run = _backups(s)

    class Watching(ByStepLLM):
        def complete(self, req: LLMRequest) -> LLMResult:
            assert not s.in_transaction(), f"{req.item_id} ran inside an open transaction"
            return super().complete(req)

    llm = Watching({"stance": YES})
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert len(llm.requests) == 4


def _done(s: Session):  # type: ignore[no-untyped-def]
    ws, it, run = _backups(s)
    runs.step(s, ws.id, run.id, ByStepLLM({"stance": YES}), MODELS)
    return ws, it, run


def _stale(s: Session, run_id: object, part: str) -> None:
    """Make one stored part look judged on other passages (as before a new upload changed its retrieval)."""
    ri = _parts_of(s, run_id)
    ri.parts = {**ri.parts, part: {**ri.parts[part], "chunk_ids": []}}
    s.commit()


def test_check_again_with_nothing_changed_stays_done(s: Session) -> None:
    ws, it, run = _done(s)
    assert runs.reopen_changed(s, ws.id, run.id) == 0
    s.refresh(run)
    assert run.status == "done"
    assert s.scalars(select(Answer).where(Answer.run_id == run.id)).one().label == "verified"


def test_check_again_reruns_every_part_of_an_affected_outcome(s: Session) -> None:
    ws, it, run = _done(s)
    _stale(s, run.id, "3")  # one part's evidence changed: the whole outcome is affected (CSF spec 5.6)
    assert runs.reopen_changed(s, ws.id, run.id) == 1
    assert runs.reopen_changed(s, ws.id, run.id) == 0  # a second press re-opens nothing more
    s.refresh(run)
    ri = _parts_of(s, run.id)
    assert (run.status, ri.state, ri.parts) == ("running", "pending", {})
    assert s.scalar(select(Answer).where(Answer.run_id == run.id)) is None
    llm = ByStepLLM({"stance": YES})
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert [q.item_id for q in llm.requests] == [f"PR.DS-11#{n}" for n in (1, 2, 3, 4)]


def test_check_again_reopens_a_failed_outcome_and_a_part_judged_by_another_model(s: Session) -> None:
    ws, it, run = _done(s)
    a = s.scalars(select(Answer).where(Answer.run_id == run.id)).one()
    a.text = runs.FAILED_TEXT  # every part stored, the evidence unchanged, but the write failed (adv-1 M4)
    s.commit()
    assert runs.reopen_changed(s, ws.id, run.id) == 1
    runs.step(s, ws.id, run.id, ByStepLLM({"stance": YES}), MODELS)
    ri = _parts_of(s, run.id)
    ri.parts = {**ri.parts, "2": {**ri.parts["2"], "model": "old/stance-model"}}  # adversary-1 M5
    s.commit()
    assert runs.reopen_changed(s, ws.id, run.id) == 1


class _NoOnPart3(ByStepLLM):
    """Says yes for every part but part 3, which its passage does not answer (a Gap)."""

    def complete(self, req: LLMRequest) -> LLMResult:
        if req.item_id.endswith("#3"):
            self.requests.append(req)
            irrelevant = {"passage": 1, "stance": "irrelevant", "quote": "", "note": "x"}
            return LLMResult(text=json.dumps({"passages": [irrelevant]}), input_tokens=1, output_tokens=1)
        return super().complete(req)


def _confirmed(s: Session):  # type: ignore[no-untyped-def]
    """PR.DS-11 with parts 1, 2 and 4 Covered by the policy and part 3 a Gap, then part 3 filled through the
    real accept path: the outcome reads Confirmed by you (Ruling 6)."""
    ws, it, run = _backups(s)
    runs.step(s, ws.id, run.id, _NoOnPart3({"stance": YES}), MODELS)
    said = store_statement(s, ws.id, LINE, filename="answer-002.txt", today=date(2026, 10, 6))
    chunk = s.scalars(select(Chunk).where(Chunk.document_id == said.id)).one()
    cite = {
        "chunk_id": str(chunk.id),
        "document_id": str(said.id),
        "filename": said.filename,
        "line_start": chunk.line_start,
        "line_end": chunk.line_end,
        "quote": LINE,
        "stance": "yes",
        "note": "",
    }
    sg = SuggestedFill(
        workspace_id=ws.id,
        run_id=run.id,
        item_id=it.id,
        statement_id=said.id,
        label="verified",
        value="Yes",
        text=f'Yes. "{LINE}"',
        citations=[cite],
        confidence=0.9,
        part=3,
    )
    s.add(sg)
    s.commit()
    a = qs.accept_suggestion(s, ws.id, sg.id)
    assert (a.label, a.statement_id) == ("user_confirmed", said.id)
    return ws, it, run, said


def test_check_again_keeps_the_visitors_outcomes_and_accepted_parts(s: Session) -> None:
    ws, it, run = _done(s)
    _stale(s, run.id, "3")
    a = s.scalars(select(Answer).where(Answer.run_id == run.id)).one()
    a.approved_at = datetime.now(UTC)
    s.commit()
    assert runs.reopen_changed(s, ws.id, run.id) == 0  # approved: the visitor's


def test_check_again_reruns_the_document_parts_of_an_outcome_confirmed_by_a_fill(s: Session) -> None:
    ws, it, run, said = _confirmed(s)
    assert runs.reopen_changed(s, ws.id, run.id) == 0  # nothing changed
    filled = _parts_of(s, run.id).parts["3"]
    assert filled["statement_id"] == str(said.id)
    _stale(s, run.id, "1")  # preflight I2 and review I2: the documents behind part 1 changed
    assert runs.reopen_changed(s, ws.id, run.id) == 1
    assert _parts_of(s, run.id).parts == {"3": filled}  # only the accepted part is kept
    llm = ByStepLLM({"stance": YES})
    assert runs.step(s, ws.id, run.id, llm, MODELS) == [it.id]
    assert [q.item_id for q in llm.requests] == [f"PR.DS-11#{n}" for n in (1, 2, 4)]
    a = s.scalars(select(Answer).where(Answer.run_id == run.id)).one()
    assert (a.label, a.statement_id) == ("user_confirmed", said.id)  # Covered with a part of theirs


def test_a_draft_override_redecides_an_outcome_confirmed_by_a_fill(s: Session) -> None:
    ws, it, run, said = _confirmed(s)
    doc = s.scalars(select(Document).where(Document.filename == "backup-policy.docx")).one()
    doc.status = "draft"
    s.commit()
    assert redecide(s, ws.id, doc.id) == 1  # review I2: the document-judged parts are decided again
    a = s.scalars(select(Answer).where(Answer.run_id == run.id)).one()
    assert (a.label, a.value, a.statement_id) == ("partial", "Partial", None)
    parts = _parts_of(s, run.id).parts
    assert [parts[k]["label"] for k in "1234"] == ["partial", "partial", "verified", "partial"]


def test_check_again_after_a_model_change_reopens_once(s: Session) -> None:
    ws, it, run = _done(s)
    new = {**MODELS, "stance": "m/new-stance"}
    _stale(s, run.id, "1")
    assert runs.reopen_changed(s, ws.id, run.id, new) == 1
    runs.step(s, ws.id, run.id, ByStepLLM({"stance": YES}), new)
    assert runs.reopen_changed(s, ws.id, run.id, new) == 0  # review I1: judged by the deployed model


def test_check_again_compares_passages_as_a_set(s: Session) -> None:
    ws, it, run = _backups(s)
    doc = s.scalars(select(Document).where(Document.workspace_id == ws.id)).one()
    f.chunk(s, doc, line_start=4, line_end=4, text="Data backups are kept off site.")
    s.commit()
    runs.step(s, ws.id, run.id, ByStepLLM({"stance": YES}), MODELS)
    ri = _parts_of(s, run.id)
    assert len(ri.parts["1"]["chunk_ids"]) == 2
    ri.parts = {**ri.parts, "1": {**ri.parts["1"], "chunk_ids": ri.parts["1"]["chunk_ids"][::-1]}}
    s.commit()
    assert runs.reopen_changed(s, ws.id, run.id) == 0  # review M1


def test_a_reopen_keeps_open_per_part_fills_and_dismisses_whole_item_ones(s: Session) -> None:
    ws, it, run = _done(s)
    said = store_statement(s, ws.id, LINE, filename="answer-002.txt", today=date(2026, 10, 6))
    cited = [{"quote": LINE}]
    fill = {"workspace_id": ws.id, "run_id": run.id, "item_id": it.id, "statement_id": said.id}
    s.add_all(
        [
            SuggestedFill(**fill, label="verified", value="Yes", citations=cited, part=2),
            SuggestedFill(**fill, label="verified", value="Yes", citations=cited, part=0),
        ]
    )
    s.commit()
    _stale(s, run.id, "1")
    assert runs.reopen_changed(s, ws.id, run.id) == 1
    states = dict(s.execute(select(SuggestedFill.part, SuggestedFill.status)).tuples().all())
    assert states == {2: "open", 0: "dismissed"}  # adversary-1 I4 (c)


def test_a_stored_answer_alone_reopens_nothing(s: Session) -> None:
    """adversary-1 I4: a statement never takes one of a part's K passage slots, so storing the visitor's
    answer changes no part's evidence."""
    ws = f.workspace(s)
    for n in range(4):  # 8 passages, every one of them taken: a statement would push one out
        doc = f.document(s, ws, filename=f"backup-{n}.docx")
        f.chunk(s, doc, line_start=1, line_end=1, text=f"Backups of data, copy {n}.")
        f.chunk(s, doc, line_start=2, line_end=2, text=f"Data backups, site {n}.")
    q = f.questionnaire(s, ws, source="csf", filename="csf-2.0")
    o = csf.framework().get("PR.DS-11")
    f.item(s, q, csf_id=o.id, code=o.id, row_ref=o.id, topic=o.category, question=o.question)
    s.commit()
    run = runs.create_run(s, ws.id, q.id, MODELS)
    runs.step(s, ws.id, run.id, ByStepLLM({"stance": YES}), MODELS)
    assert all(len(p["chunk_ids"]) == 8 for p in _parts_of(s, run.id).parts.values())
    store_statement(s, ws.id, " ".join(o.parts), filename="answer-001.txt", today=date(2026, 10, 6))
    assert runs.reopen_changed(s, ws.id, run.id) == 0
