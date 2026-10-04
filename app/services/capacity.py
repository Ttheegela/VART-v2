from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

# Neon Free gives 1 GB of Postgres storage per project (20 GB per account); stay well under it.
# Source: https://neon.com/docs/introduction/plans (checked 2026-10-04)
MAX_DB_BYTES = 400 * 1024 * 1024


def demo_is_full(session: Session) -> bool:
    return bool(session.scalar(text("select pg_database_size(current_database())")) > MAX_DB_BYTES)


def ensure_capacity(session: Session) -> None:
    if demo_is_full(session):
        raise HTTPException(status_code=503, detail="the demo is full right now; please try again later")
