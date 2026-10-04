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
