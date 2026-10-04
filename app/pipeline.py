"""One questionnaire item through the engine (spec 6.3). Contract stub written by Plan 2A Task 2; Plan 2A
Task 8 replaces this file."""

import uuid
from collections.abc import Mapping

from sqlalchemy.orm import Session

from app.contracts import ItemInput, ItemResult, Spend
from app.llm.client import LLMClient


def answer_item(
    session: Session,
    workspace_id: uuid.UUID,
    item: ItemInput,
    llm: LLMClient,
    models: Mapping[str, str],
    spend: Spend,
) -> ItemResult:
    raise NotImplementedError("Plan 2A Task 8")
