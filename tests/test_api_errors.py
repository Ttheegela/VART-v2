import importlib
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
    MAX_QUESTIONNAIRE_BYTES,
    MAX_QUESTIONNAIRES,
    MAX_REASON_CHARS,
    AnswerEdit,
    AnswerQuestionIn,
    DocumentPatch,
    Mapping,
    NotApplicableIn,
    clean_text,
)
from app.contracts import BudgetExhausted
from app.db.models import IpLimit, Questionnaire, Workspace
from app.ingest.parse import IngestError
from app.main import app
from app.services import ip_limits, llm_budget
from tests.apiclient import visitor
from tests.test_openapi import CONTRACT


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


def test_a_row_deleted_between_two_reads_is_a_gone_404() -> None:
    # Adversary-3 M7: a reset between an unlocked read and its locked re-read.
    from sqlalchemy.exc import NoResultFound

    r = _app(NoResultFound()).get("/boom")
    assert (r.status_code, r.json()["detail"]) == (404, errors.GONE)


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


# ------------------------------------------------------------------ fix round 1 (review + adversary 1)
U = "00000000-0000-4000-8000-000000000000"
MAPPING = {
    "sheet": None,
    "header_row": 1,
    "id_col": None,
    "question_col": "A",
    "answer_col": "B",
    "comments_col": None,
}
FILE = {"file": ("a.txt", b"hello", "text/plain")}
CALLS: dict[tuple[str, str], dict[str, object]] = {
    ("/api/documents", "get"): {},
    ("/api/documents", "post"): {"files": FILE},
    ("/api/documents/sample", "post"): {},
    ("/api/documents/{document_id}", "patch"): {"json": {}},
    ("/api/documents/{document_id}", "delete"): {},
    ("/api/documents/{document_id}/lines", "get"): {},
    ("/api/questionnaires", "get"): {},
    ("/api/questionnaires", "post"): {"files": FILE},
    ("/api/questionnaires/sample/{name}", "post"): {},
    ("/api/questionnaires/{questionnaire_id}", "get"): {},
    ("/api/questionnaires/{questionnaire_id}", "delete"): {},
    ("/api/questionnaires/{questionnaire_id}/mapping", "put"): {"json": MAPPING},
    ("/api/questionnaires/{questionnaire_id}/runs", "post"): {},
    ("/api/runs/{run_id}", "get"): {},
    ("/api/runs/{run_id}/step", "post"): {},
    ("/api/runs/{run_id}/answers", "get"): {},
    ("/api/runs/{run_id}/approve-verified", "post"): {},
    ("/api/runs/{run_id}/export", "get"): {},
    ("/api/runs/{run_id}/questions", "get"): {},
    ("/api/answers/{answer_id}", "get"): {},
    ("/api/answers/{answer_id}", "patch"): {"json": {"text": "x"}},
    ("/api/answers/{answer_id}/approve", "post"): {},
    ("/api/answers/{answer_id}/not-applicable", "post"): {"json": {"reason": "x"}},
    ("/api/questions/{question_id}/answer", "post"): {"json": {"text": "x"}},
    ("/api/questions/{question_id}/skip", "post"): {},
    ("/api/suggestions/{suggestion_id}/accept", "post"): {},
    ("/api/audit", "get"): {},
}
# Ruling 7: no operation is a stub after the Plan 3 merge; each is named by the test that exercises it.
D, Q, R, E, IV = (
    "tests.test_api_documents",
    "tests.test_api_questionnaires",
    "tests.test_api_runs",
    "tests.test_export",
    "tests.test_questions",
)
STUBS: set[tuple[str, str]] = set()
COVERED: dict[tuple[str, str], str] = {
    ("/api/documents", "get"): f"{D}::test_an_upload_is_parsed_classified_and_listed",
    ("/api/documents", "post"): f"{D}::test_an_upload_is_parsed_classified_and_listed",
    ("/api/documents/sample", "post"): f"{D}::test_the_sample_pack_loads_once_in_fact_sheet_order",
    ("/api/documents/{document_id}", "patch"): f"{D}::test_a_metadata_override_is_stored_as_the_users",
    ("/api/documents/{document_id}", "delete"): f"{D}::test_an_unused_document_is_deleted",
    ("/api/documents/{document_id}/lines", "get"): f"{D}::test_lines_are_read_in_a_bounded_window",
    ("/api/questionnaires", "get"): f"{Q}::test_the_samples_load_mapped",
    (
        "/api/questionnaires",
        "post",
    ): f"{Q}::test_an_upload_answers_the_detected_mapping_and_a_preview_without_items",
    ("/api/questionnaires/sample/{name}", "post"): f"{Q}::test_the_samples_load_mapped",
    (
        "/api/questionnaires/{questionnaire_id}",
        "get",
    ): f"{Q}::test_a_mapping_is_cached_so_a_get_does_not_read_the_file",
    (
        "/api/questionnaires/{questionnaire_id}",
        "delete",
    ): f"{Q}::test_delete_removes_items_and_is_refused_after_a_run",
    (
        "/api/questionnaires/{questionnaire_id}/mapping",
        "put",
    ): f"{Q}::test_confirming_the_mapping_creates_the_items",
    ("/api/questionnaires/{questionnaire_id}/runs", "post"): f"{R}::test_a_run_fills_through_the_step_loop",
    ("/api/runs/{run_id}", "get"): f"{R}::test_a_run_fills_through_the_step_loop",
    ("/api/runs/{run_id}/step", "post"): f"{R}::test_a_run_fills_through_the_step_loop",
    ("/api/runs/{run_id}/answers", "get"): f"{R}::test_a_run_fills_through_the_step_loop",
    ("/api/runs/{run_id}/approve-verified", "post"): f"{R}::test_approve_rules_and_bulk_approve",
    ("/api/runs/{run_id}/export", "get"): f"{E}::test_the_endpoint_exports_a_real_run_and_isolates_it",
    ("/api/runs/{run_id}/questions", "get"): f"{IV}::test_the_interview_over_http",
    ("/api/answers/{answer_id}", "get"): f"{R}::test_the_drawer_rereads_each_citation_with_context",
    ("/api/answers/{answer_id}", "patch"): f"{R}::test_approve_rules_and_bulk_approve",
    (
        "/api/answers/{answer_id}/approve",
        "post",
    ): f"{R}::test_bulk_approve_leaves_an_edited_answer_for_a_look",
    (
        "/api/answers/{answer_id}/not-applicable",
        "post",
    ): f"{R}::test_not_applicable_clears_what_the_engine_stored",
    ("/api/questions/{question_id}/answer", "post"): f"{IV}::test_the_interview_over_http",
    ("/api/questions/{question_id}/skip", "post"): f"{IV}::test_the_interview_over_http",
    ("/api/suggestions/{suggestion_id}/accept", "post"): f"{IV}::test_the_interview_over_http",
    ("/api/audit", "get"): f"{R}::test_the_audit_log_lists_this_workspaces_events_only",
}


def _url(path: str) -> str:
    return (
        path.replace("{name}", "vsq-a")
        .replace("_id}", "}")
        .format_map({k: U for k in ("document", "questionnaire", "run", "answer", "question", "suggestion")})
    )


def test_every_contract_operation_is_a_stub_or_tested() -> None:
    assert set(CALLS) == CONTRACT
    assert not STUBS & set(COVERED)
    assert STUBS | set(COVERED) == CONTRACT
    for name in COVERED.values():
        module, test = name.split("::")
        assert callable(getattr(importlib.import_module(module), test, None)), name


@pytest.mark.parametrize(("path", "method"), sorted(CALLS))
def test_every_operation_is_reachable_and_built(db: Engine, path: str, method: str) -> None:
    # Review I-3: every operation is reachable and none is shadowed; after the merge none is a 501 stub.
    client, _ = visitor(db)
    r = client.request(method.upper(), _url(path), **CALLS[(path, method)])  # type: ignore[arg-type]
    assert r.status_code not in (405, 501), (path, method, r.status_code)
    assert r.content != b'{"detail":"Not Found"}', (path, method)  # the router's miss, not the app's 404


def _workspaces(db: Engine) -> int:
    with Session(db) as s:
        return len(s.scalars(select(Workspace.id)).all())


@pytest.mark.parametrize(("method", "path"), [("GET", "/api/documents"), ("POST", "/api/documents/sample")])
def test_only_get_workspace_creates_a_workspace(db: Engine, method: str, path: str) -> None:
    # Adversary C1: without a live workspace every other endpoint is the GONE 404; no cookie, nothing counted.
    r = TestClient(app).request(method, path)
    assert (r.status_code, r.json()) == (404, {"detail": errors.GONE})
    assert "set-cookie" not in r.headers
    assert _workspaces(db) == 0
    with Session(db) as s:
        assert s.scalar(select(IpLimit.hits)) is None


@pytest.mark.parametrize(
    "headers",
    [{"Sec-Fetch-Site": "cross-site"}, {"Origin": "https://evil.example"}, {"Origin": "null"}],
)
def test_a_cross_site_write_is_a_403(db: Engine, headers: dict[str, str]) -> None:
    # Adversary C1: a cross-site form POST (SameSite=Lax sends no cookie, but the guard runs first anyway).
    client, _ = visitor(db)
    for method, path in (
        ("POST", "/api/workspace/reset"),
        ("POST", "/api/documents/sample"),
        ("PATCH", f"/api/answers/{U}"),
        ("DELETE", f"/api/documents/{U}"),
    ):
        r = client.request(method, path, headers=headers, data={"a": "b"})
        assert (r.status_code, r.json()) == (403, {"detail": errors.CROSS_SITE}), (method, path)
    assert _workspaces(db) == 1  # the reset did not run


@pytest.mark.parametrize(
    "headers",
    [{}, {"Sec-Fetch-Site": "same-origin"}, {"Origin": "http://testserver"}, {"Sec-Fetch-Site": "none"}],
)
def test_a_same_origin_write_passes_the_guard(db: Engine, headers: dict[str, str]) -> None:
    client, _ = visitor(db)
    r = client.post(f"/api/runs/{U}/step", headers=headers)
    assert (r.status_code, r.json()) == (404, {"detail": "Not found."})  # the handler ran: the run is unknown


def test_a_cross_site_read_is_not_refused(db: Engine) -> None:
    client, _ = visitor(db)
    assert client.get("/api/workspace", headers={"Origin": "https://evil.example"}).status_code == 200


def _refused(scope: llm_budget.Scope) -> TestClient:
    return _app(llm_budget.Refused("stance", scope))


def test_each_budget_scope_has_its_sentence_and_retry_after() -> None:
    # Adversary I5: a day cap is not "this workspace, this hour".
    sentences = {}
    for scope in ("workspace", "network", "hour", "day"):
        r = _refused(scope).get("/boom")  # type: ignore[arg-type]
        assert r.status_code == 429
        sentences[scope] = r.json()["detail"]
        assert 1 <= int(r.headers["retry-after"]) <= (86400 if scope == "day" else 3600), scope
    assert len(set(sentences.values())) == 4
    assert "workspace" in sentences["workspace"] and "network" in sentences["network"]
    assert "today" in sentences["day"] and "midnight UTC" in sentences["day"]


def test_retry_after_for_the_day_counts_to_midnight_utc() -> None:
    now = datetime(2026, 10, 6, 23, 0, 0, tzinfo=UTC)
    assert errors.retry_after_budget(now, "day") == 3600
    assert errors.retry_after_budget(now.replace(hour=1), "day") == 23 * 3600


def test_a_plain_budget_exhausted_reads_as_the_workspace_scope() -> None:
    assert _app(BudgetExhausted("stance")).get("/boom").json() == _refused("workspace").get("/boom").json()


def _workspace(db: Engine) -> uuid.UUID:
    with Session(db) as s:
        ws = Workspace(ip_hash="x" * 32)
        s.add(ws)
        s.commit()
        return ws.id


def test_the_llm_limit_counts_each_model_call(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    # Adversary I2: per network per model call, inside the spender, not per request.
    monkeypatch.setitem(ip_limits.LIMITS, "llm", (2, timedelta(hours=1)))
    ws = _workspace(db)
    with Session(db) as s:
        spend = llm_budget.spender(s, ws, network="net-a")
        assert [spend("stance"), spend("draft"), spend("stance")] == [True, True, False]
        assert llm_budget.refusal_scope(s, ws, "stance", network="net-a") == "network"
        # another network is unaffected
        assert llm_budget.spender(s, ws, network="net-b")("stance") is True


def test_refusal_scope_names_the_workspace_cap(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 1)
    ws = _workspace(db)
    with Session(db) as s:
        spend = llm_budget.spender(s, ws, network="net-a")
        assert [spend("stance"), spend("stance")] == [True, False]
        assert llm_budget.refusal_scope(s, ws, "stance", network="net-a") == "workspace"


def test_refusal_scope_names_the_global_day(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_budget, "GLOBAL_PER_DAY", 1)
    ws = _workspace(db)
    with Session(db) as s:
        spend = llm_budget.spender(s, ws)
        assert [spend("stance"), spend("stance")] == [True, False]
        assert llm_budget.refusal_scope(s, ws, "stance") == "day"


def test_document_patch_refuses_null_for_not_null_columns() -> None:
    # Pre-flight P8: an explicit null would be a NOT NULL 500.
    for field in ("kind", "status", "evidence_allowed"):
        with pytest.raises(ValidationError):
            DocumentPatch.model_validate({field: None})
    patch = DocumentPatch.model_validate({"effective_date": None, "scope": None})
    assert patch.model_dump(exclude_unset=True) == {"effective_date": None, "scope": None}
    assert DocumentPatch.model_validate({}).model_dump(exclude_unset=True) == {}


def test_mapping_sheet_is_at_most_31_characters_and_scope_is_optional() -> None:
    # Adversary I4 (Excel's sheet-name limit); review I-2 (Plan 6B's csf scope).
    with pytest.raises(ValidationError):
        Mapping.model_validate({**MAPPING, "sheet": "x" * 32})
    assert Mapping.model_validate({**MAPPING, "sheet": "x" * 31}).scope is None
    assert Mapping.model_validate({**MAPPING, "scope": "GV"}).scope == "GV"


def test_questionnaire_caps() -> None:
    # Adversary I3: the one stored upload is bounded per workspace and per file.
    assert (MAX_QUESTIONNAIRES, MAX_QUESTIONNAIRE_BYTES) == (5, 1024 * 1024)
