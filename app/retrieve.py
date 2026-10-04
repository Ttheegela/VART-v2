"""Retrieve (spec 6.5). Contract stub written by Plan 2A Task 2; Plan 2A Task 5 replaces this file."""

import uuid

from sqlalchemy.orm import Session

from app.contracts import Passage, Retrieval


def build_query(question: str, topic: str | None) -> str:
    raise NotImplementedError("Plan 2A Task 5")


def retrieve(session: Session, workspace_id: uuid.UUID, question: str, topic: str | None) -> Retrieval:
    raise NotImplementedError("Plan 2A Task 5")


def document_passages(
    session: Session, workspace_id: uuid.UUID, document_id: uuid.UUID
) -> tuple[Passage, ...]:
    raise NotImplementedError("Plan 2A Task 5")
