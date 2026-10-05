"""One questionnaire item through the engine (spec 6.3): retrieve, stance, decide, draft and check. Plan 3's
step runner calls answer_item for each claimed item and stores the result; the eval harness calls it too.
Every model call is spent first (spend commits at once, app.services.llm_budget.spender) and no database
transaction is open while a model runs."""

import uuid
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts import BudgetExhausted, ItemInput, ItemResult, Spend, Stance
from app.db.models import Document
from app.decide import decide
from app.draft import write_draft
from app.llm.client import LLMClient, LLMRequest, LLMResult
from app.retrieve import retrieve
from app.stance import stance


class _Meter:
    """Adds up the cost and latency of the calls one item makes."""

    def __init__(self, inner: LLMClient) -> None:
        self.inner = inner
        self.cost_usd = 0.0
        self.latency_ms = 0

    def complete(self, req: LLMRequest) -> LLMResult:
        result = self.inner.complete(req)
        self.cost_usd += result.cost_usd or 0.0
        self.latency_ms += result.latency_ms or 0
        return result


def answer_item(
    session: Session,
    workspace_id: uuid.UUID,
    item: ItemInput,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
) -> ItemResult:
    """Raises BudgetExhausted when the stance call is refused and LLMError when it fails; the draft step
    degrades to a template answer by itself."""
    retrieval = retrieve(session, workspace_id, item.question, item.topic)
    documents = list(session.scalars(select(Document.filename).where(Document.workspace_id == workspace_id)))
    session.commit()  # end the read transaction before any model call
    meter = _Meter(llm)
    stances: tuple[Stance, ...] = ()
    if retrieval.passages:
        if not spend("stance"):
            raise BudgetExhausted("stance")
        stances = stance(meter, item, retrieval.passages, models["stance"])
    decision = decide(retrieval.passages, stances, retrieval.dropped)
    draft = write_draft(meter, item, decision, models["draft"], spend, documents)
    return ItemResult(item, retrieval, stances, decision, draft, round(meter.cost_usd, 6), meter.latency_ms)
