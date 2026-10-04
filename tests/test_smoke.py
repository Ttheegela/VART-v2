import httpx
import pytest

from scripts.smoke import check


def _transport(
    health: dict[str, object], root: str = '<div id="root"></div>', cookie: bool = True
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text=root)
        if request.url.path == "/api/health":
            return httpx.Response(200, json=health)
        if request.url.path == "/api/workspace":
            return httpx.Response(
                200,
                json={"created_at": "2026-10-03T00:00:00Z"},
                headers={"set-cookie": "vart_ws=abc; HttpOnly; Path=/"} if cookie else {},
            )
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "2.0.0.dev0", "models": {}})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_a_healthy_deploy_passes() -> None:
    with httpx.Client(
        base_url="https://x", transport=_transport({"status": "ok", "db": "ok", "canary": None})
    ) as c:
        assert check(c).startswith("ok")


def test_a_missing_ui_fails() -> None:
    with (
        httpx.Client(base_url="https://x", transport=_transport({"status": "ok"}, root="Not Found")) as c,
        pytest.raises(SystemExit, match="UI"),
    ):
        check(c)


def test_a_degraded_deploy_fails() -> None:
    with (
        httpx.Client(base_url="https://x", transport=_transport({"status": "degraded"})) as c,
        pytest.raises(SystemExit, match="health"),
    ):
        check(c)


def test_a_missing_workspace_cookie_fails() -> None:
    with (
        httpx.Client(base_url="https://x", transport=_transport({"status": "ok"}, cookie=False)) as c,
        pytest.raises(SystemExit, match="workspace cookie"),
    ):
        check(c)
