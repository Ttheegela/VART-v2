import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api import errors
from app.api.schemas import (
    MAX_ANSWER_CHARS,
    MAX_EDIT_CHARS,
    MAX_REASON_CHARS,
    AnswerEdit,
    AnswerQuestionIn,
    NotApplicableIn,
    clean_text,
)
from app.contracts import BudgetExhausted
from app.db.models import IpLimit, Questionnaire
from app.ingest.parse import IngestError
from app.services import ip_limits
from tests.apiclient import visitor


def _app(exc: Exception) -> TestClient:
    probe = FastAPI()
    errors.install(probe)

    @probe.get("/boom")
    def boom() -> None:
        raise exc

    return TestClient(probe, raise_server_exceptions=False)


def test_ingest_error_is_a_422_with_its_sentence() -> None:
    r = _app(IngestError("Files must be 4 MB or smaller.")).get("/boom")
    assert (r.status_code, r.json()) == (422, {"detail": "Files must be 4 MB or smaller."})


def test_budget_exhausted_is_a_429_with_retry_after() -> None:
    r = _app(BudgetExhausted("stance")).get("/boom")
    assert r.status_code == 429
    assert 1 <= int(r.headers["retry-after"]) <= 3600
    assert "budget" in r.json()["detail"]


def test_not_found_and_conflict_shapes() -> None:
    assert _app(errors.NotFound()).get("/boom").json() == {"detail": "Not found."}
    r = _app(errors.Conflict("Resolve the conflict first.")).get("/boom")
    assert (r.status_code, r.json()["detail"]) == (409, "Resolve the conflict first.")


def test_a_foreign_key_violation_is_a_404(db: Engine) -> None:
    # Carry-over (ingest adversary-3): an insert for a workspace that was reset mid-request.
    with Session(db) as s:
        s.add(Questionnaire(workspace_id=uuid.uuid4(), filename="q.csv", source="upload"))
        with pytest.raises(IntegrityError) as caught:
            s.flush()
    r = _app(caught.value).get("/boom")
    assert r.status_code == 404 and "reload the page" in r.json()["detail"]


def test_another_integrity_error_is_not_dressed_up_as_a_404(db: Engine) -> None:
    with Session(db) as s:
        s.add(Questionnaire(workspace_id=uuid.uuid4(), filename="q.csv", source="nope"))
        with pytest.raises(IntegrityError) as caught:
            s.flush()
    assert _app(caught.value).get("/boom").status_code == 500


def test_retry_after_budget_counts_to_the_next_hour() -> None:
    assert errors.retry_after_budget(datetime(2026, 10, 6, 12, 59, 30, tzinfo=UTC)) == 30
    assert errors.retry_after_budget(datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)) == 3600


def test_clean_text_strips_lone_surrogates_and_nul() -> None:
    # Triage row 41: a lone surrogate in a JSON string reached Postgres as a 500.
    assert clean_text("ok" + chr(0xD800) + " then" + chr(0) + " more") == "ok then more"


BODIES: list[tuple[type[BaseModel], str, int]] = [
    (AnswerEdit, "text", MAX_EDIT_CHARS),
    (NotApplicableIn, "reason", MAX_REASON_CHARS),
    (AnswerQuestionIn, "text", MAX_ANSWER_CHARS),
]


@pytest.mark.parametrize(("model", "field", "cap"), BODIES)
def test_free_text_is_cleaned_and_stripped_before_its_bounds(
    model: type[BaseModel], field: str, cap: int
) -> None:
    # Pre-flight P6: strip, then check the length, so blank text is a 422 and padding does not count.
    for blank in ("", "   ", " " + chr(0) + chr(0xDC00) + " "):
        with pytest.raises(ValidationError):
            model.model_validate({field: blank})
    with pytest.raises(ValidationError):
        model.model_validate({field: "x" * (cap + 1)})
    assert getattr(model.model_validate({field: "  " + "x" * cap + "  "}), field) == "x" * cap
    assert getattr(model.model_validate({field: " a" + chr(0) + "b "}), field) == "ab"
    with pytest.raises(ValidationError):
        model.model_validate({field: "ok", "extra": 1})


def _request() -> Request:
    return Request({"type": "http", "headers": [(b"x-real-ip", b"203.0.113.9")], "client": ("1.2.3.4", 1)})


def test_limit_counts_then_refuses_with_retry_after(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    # Pre-flight P12: the one per-network limit helper both lanes use.
    monkeypatch.setitem(ip_limits.LIMITS, "llm", (2, timedelta(hours=1)))
    with Session(db) as s:
        errors.limit(_request(), s, "llm")
        errors.limit(_request(), s, "llm")
        with pytest.raises(HTTPException) as refused:
            errors.limit(_request(), s, "llm")
    assert refused.value.status_code == 429
    assert refused.value.headers is not None and 1 <= int(refused.value.headers["Retry-After"]) <= 3600
    with Session(db) as s:  # the refused attempt was committed too
        assert s.scalar(select(IpLimit.hits)) == 3


def test_the_llm_limit_is_400_an_hour() -> None:
    assert ip_limits.LIMITS["llm"] == (400, timedelta(hours=1))


def test_workspace_says_when_it_expires(db: Engine) -> None:
    client, _ = visitor(db)
    body = client.get("/api/workspace").json()
    created, expires = (datetime.fromisoformat(body[k]) for k in ("created_at", "expires_at"))
    assert expires - created == timedelta(hours=24)


def test_a_stub_is_a_501_with_the_error_shape(db: Engine) -> None:
    client, _ = visitor(db)
    r = client.get("/api/documents")
    assert (r.status_code, r.json()) == (501, {"detail": "Not built yet."})
