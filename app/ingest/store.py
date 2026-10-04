"""Ingest service (spec 6.4, 9). Contract stub written by Plan 2A Task 2; Plan 2B Task 4 replaces this
file."""

import uuid
from datetime import date
from typing import Literal

from sqlalchemy.orm import Session

from app.contracts import Spend
from app.db.models import Document
from app.llm.client import LLMClient

MAX_DOCUMENTS = 20  # spec 9, per workspace (statements excluded)
MAX_WORKSPACE_LINES = 20_000  # spec 9, per workspace


def ingest_document(
    session: Session,
    workspace_id: uuid.UUID,
    filename: str,
    data: bytes,
    *,
    source: Literal["sample", "upload", "drive"],
    llm: LLMClient | None,
    model: str,
    spend: Spend,
) -> Document:
    raise NotImplementedError("Plan 2B Task 4")


def store_statement(
    session: Session, workspace_id: uuid.UUID, text: str, *, filename: str, today: date
) -> Document:
    raise NotImplementedError("Plan 2B Task 4")
