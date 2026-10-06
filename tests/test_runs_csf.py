import json
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, delete, select, update
from sqlalchemy.orm import Session

from app import csf, runs
from app.contracts import BudgetExhausted
from app.db.models import Answer, Item, Run, RunItem
from app.llm.client import LLMError, LLMRequest, LLMResult
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
