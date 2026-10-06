import json

from scripts.export_openapi import OUT, render


def test_committed_openapi_is_current() -> None:
    assert OUT.read_text(encoding="utf-8") == render(), (
        "run: python scripts/export_openapi.py && cd web && npm run gen:api"
    )


def test_health_and_workspace_are_public_and_internal_routes_are_not() -> None:
    paths = set(json.loads(render())["paths"])
    assert {"/api/health", "/api/version", "/api/workspace", "/api/workspace/reset"} <= paths
    assert not [p for p in paths if p.startswith("/api/internal")]


OLD = {"/api/health", "/api/version", "/api/workspace", "/api/workspace/reset"}
CONTRACT = {
    ("/api/documents", "get"),
    ("/api/documents", "post"),
    ("/api/documents/sample", "post"),
    ("/api/documents/{document_id}", "patch"),
    ("/api/documents/{document_id}", "delete"),
    ("/api/documents/{document_id}/lines", "get"),
    ("/api/questionnaires", "get"),
    ("/api/questionnaires", "post"),
    ("/api/questionnaires/sample/{name}", "post"),
    ("/api/questionnaires/{questionnaire_id}", "get"),
    ("/api/questionnaires/{questionnaire_id}", "delete"),
    ("/api/questionnaires/{questionnaire_id}/mapping", "put"),
    ("/api/questionnaires/{questionnaire_id}/runs", "post"),
    ("/api/runs/{run_id}", "get"),
    ("/api/runs/{run_id}/step", "post"),
    ("/api/runs/{run_id}/answers", "get"),
    ("/api/runs/{run_id}/approve-verified", "post"),
    ("/api/runs/{run_id}/export", "get"),
    ("/api/runs/{run_id}/questions", "get"),
    ("/api/answers/{answer_id}", "get"),
    ("/api/answers/{answer_id}", "patch"),
    ("/api/answers/{answer_id}/approve", "post"),
    ("/api/answers/{answer_id}/not-applicable", "post"),
    ("/api/questions/{question_id}/answer", "post"),
    ("/api/questions/{question_id}/skip", "post"),
    ("/api/suggestions/{suggestion_id}/accept", "post"),
    ("/api/audit", "get"),
}


def test_the_frozen_contract_is_exactly_these_operations() -> None:
    spec = json.loads(render())
    ops = {(p, m) for p, item in spec["paths"].items() for m in item if p not in OLD}
    assert ops == CONTRACT


def test_every_refusal_has_the_error_shape() -> None:
    # Pre-flight P1: only the contract's operations; /api/health's 503 is a HealthOut by design.
    spec = json.loads(render())
    checked = 0
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if (path, method) not in CONTRACT:
                continue
            for status in ("404", "409", "429", "503"):
                ref = op["responses"][status]["content"]["application/json"]["schema"]["$ref"]
                assert ref.endswith("/ErrorOut"), (path, method, status)
                checked += 1
    assert checked == 4 * len(CONTRACT)


# Review I-1: these raise a sentence 422 ({"detail": str}) as well as FastAPI's list form.
SENTENCE_422 = {
    ("/api/documents", "post"),
    ("/api/documents/{document_id}/lines", "get"),
    ("/api/questionnaires", "post"),
    ("/api/questionnaires/sample/{name}", "post"),
    ("/api/questionnaires/{questionnaire_id}/mapping", "put"),
    ("/api/questionnaires/{questionnaire_id}/runs", "post"),
    ("/api/questions/{question_id}/answer", "post"),
}


def test_a_sentence_422_documents_both_shapes() -> None:
    spec = json.loads(render())
    for path, method in SENTENCE_422:
        schema = spec["paths"][path][method]["responses"]["422"]["content"]["application/json"]["schema"]
        refs = {s["$ref"].rsplit("/", 1)[1] for s in schema["anyOf"]}
        assert refs == {"ErrorOut", "HTTPValidationError"}, (path, method)


def test_document_patch_does_not_advertise_null_for_not_null_columns() -> None:
    props = json.loads(render())["components"]["schemas"]["DocumentPatch"]["properties"]
    for field in ("kind", "status", "evidence_allowed"):
        assert "null" not in json.dumps(props[field]), field
