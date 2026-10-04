"""Interview (spec 6.9). Contract stub written by Plan 2A Task 2; Plan 2A Task 9 replaces this file."""

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.contracts import OpenItem, QueueEntry, Spend, Suggestion
from app.llm.client import LLMClient


def high_weight(topic: str | None) -> bool:
    raise NotImplementedError("Plan 2A Task 9")


def plan_queue(items: Sequence[OpenItem]) -> list[QueueEntry]:
    raise NotImplementedError("Plan 2A Task 9")


def follow_up(question: str, answer: str) -> str | None:
    raise NotImplementedError("Plan 2A Task 9")


def recheck(
    session: Session,
    workspace_id: uuid.UUID,
    statement_id: uuid.UUID,
    topic: str | None,
    items: Sequence[OpenItem],
    llm: LLMClient,
    model: str,
    spend: Spend,
) -> list[Suggestion]:
    raise NotImplementedError("Plan 2A Task 9")
