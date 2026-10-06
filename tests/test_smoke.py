import subprocess
import sys
from functools import partial
from pathlib import Path

import httpx
import pytest

from scripts.smoke import check, main

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "smoke.py"

UI = '<div id="root"></div>'
HEALTHY: dict[str, object] = {"status": "ok", "db": "ok", "canary": None}
COOKIE = {"set-cookie": "vart_ws=abc; HttpOnly; Path=/"}
VERSION = {"version": "2.0.0.dev0", "models": {}, "sample_precomputed": True}
# (path, the name its FAIL line carries): one row per request check() makes.
CHECKS = [
    ("/", "UI"),
    ("/api/health", "health"),
    ("/api/workspace", "workspace cookie"),
    ("/api/version", "version"),
    ("/api/workspace/reset", "same-site write"),
]


def _transport(
    health: dict[str, object],
    root: str = UI,
    cookie: bool = True,
    answers: dict[str, httpx.Response | Exception] | None = None,
) -> httpx.MockTransport:
    """A healthy deploy. `answers` replaces what one path returns (a Response) or does (an Exception)."""

    def handler(request: httpx.Request) -> httpx.Response:
        answer = (answers or {}).get(request.url.path)
        if isinstance(answer, Exception):
            raise answer
        if answer is not None:
            return answer
        if request.url.path == "/":
            return httpx.Response(200, text=root)
        if request.url.path == "/api/health":
            return httpx.Response(200, json=health)
        if request.url.path == "/api/workspace":
            return httpx.Response(
                200, json={"created_at": "2026-10-03T00:00:00Z"}, headers=COOKIE if cookie else {}
            )
        if request.url.path == "/api/version":
            return httpx.Response(200, json=VERSION)
        if request.url.path == "/api/workspace/reset":  # the guard: Origin must name the host it reached
            same = request.headers.get("origin") == f"https://{request.url.host}"
            return httpx.Response(204) if same else httpx.Response(403, json={"detail": "cross-site"})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _fail(transport: httpx.MockTransport) -> str:
    """The message check() stops with. SystemExit(str) prints that str to stderr and exits 1: no traceback."""
    with httpx.Client(base_url="https://x", transport=transport) as c, pytest.raises(SystemExit) as raised:
        check(c)
    message = raised.value.code
    assert isinstance(message, str)
    assert "\n" not in message, "a FAIL line is one line"
    return message


def test_a_healthy_deploy_passes() -> None:
    with httpx.Client(base_url="https://x", transport=_transport(HEALTHY)) as c:
        assert check(c) == "ok: version 2.0.0.dev0, canary None"


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


@pytest.mark.parametrize(
    ("path", "name", "answer"),
    [
        ("/", "UI", httpx.Response(500, text=UI)),
        ("/api/health", "health", httpx.Response(503, json=HEALTHY)),
        ("/api/workspace", "workspace cookie", httpx.Response(429, json={}, headers=COOKIE)),
        ("/api/version", "version", httpx.Response(500, json=VERSION)),
        ("/api/workspace/reset", "same-site write", httpx.Response(403, json={"detail": "cross-site"})),
    ],
    ids=[name for _, name in CHECKS],
)
def test_a_status_other_than_200_fails_even_when_the_body_looks_fine(
    path: str, name: str, answer: httpx.Response
) -> None:
    message = _fail(_transport(HEALTHY, answers={path: answer}))
    assert message.startswith(f"FAIL: {name}: ")


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
@pytest.mark.parametrize(("path", "name"), CHECKS, ids=[name for _, name in CHECKS])
def test_a_connection_error_or_timeout_is_a_fail_line(
    path: str, name: str, error: type[httpx.TransportError]
) -> None:
    message = _fail(_transport(HEALTHY, answers={path: error("boom")}))
    assert message.startswith(f"FAIL: {name}: ")
    assert error.__name__ in message


def test_a_health_page_that_is_not_json_fails() -> None:
    # What a CDN fallback answers for an API path that is not deployed: 200 and the app shell.
    message = _fail(_transport(HEALTHY, answers={"/api/health": httpx.Response(200, text=UI)}))
    assert message.startswith("FAIL: health: ")


def test_health_status_is_read_from_the_json_not_searched_for() -> None:
    message = _fail(_transport({"status": "degraded", "canary": {"status": "ok"}}))
    assert message.startswith("FAIL: health: ")


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(httpx.Response(200, text="<html>Bad Gateway</html>"), id="html"),
        pytest.param(httpx.Response(200, text=""), id="empty"),
        pytest.param(httpx.Response(200, json=["2.0.0.dev0"]), id="not-an-object"),
        pytest.param(httpx.Response(200, json={"models": {}}), id="no-version"),
        pytest.param(httpx.Response(200, json={"version": 2}), id="version-not-a-string"),
    ],
)
def test_a_version_answer_that_is_not_a_version_fails(answer: httpx.Response) -> None:
    message = _fail(_transport(HEALTHY, answers={"/api/version": answer}))
    assert message.startswith("FAIL: version: ")


def test_a_multi_line_page_still_gives_a_one_line_message() -> None:
    assert _fail(_transport(HEALTHY, root="<html>\n<body>nginx</body>\n</html>")).startswith("FAIL: UI: ")


def test_a_long_page_is_cut_short() -> None:
    assert len(_fail(_transport(HEALTHY, root="x" * 5000))) < 400


def _run_main(monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport) -> int:
    monkeypatch.setattr(sys, "argv", ["smoke.py", "https://x/"])
    monkeypatch.setattr(httpx, "Client", partial(httpx.Client, transport=transport))
    return main()


def test_main_prints_the_ok_line_and_returns_0(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_main(monkeypatch, _transport(HEALTHY)) == 0
    assert capsys.readouterr().out == "ok: version 2.0.0.dev0, canary None\n"


def test_main_stops_with_a_fail_line_when_the_deploy_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit) as raised:
        _run_main(monkeypatch, _transport(HEALTHY, answers={"/": httpx.ConnectError("refused")}))
    assert isinstance(raised.value.code, str)
    assert raised.value.code.startswith("FAIL: UI: ")


@pytest.mark.parametrize(
    "url", ["http://[::1", "http://ex\x00ample.com"], ids=["bad-port", "control-character"]
)
def test_main_stops_with_a_fail_line_for_a_malformed_base_url(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setattr(sys, "argv", ["smoke.py", url])  # the real httpx.Client: nothing is requested
    with pytest.raises(SystemExit) as raised:
        main()
    message = raised.value.code
    assert isinstance(message, str)
    assert message.startswith("FAIL: base URL: ") and "\n" not in message


def test_a_malformed_base_url_exits_1_with_one_fail_line_and_no_traceback() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "http://[::1"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("FAIL: base URL: ") and result.stderr.count("\n") == 1


def test_a_deploy_whose_sample_would_go_live_fails() -> None:
    stale = httpx.Response(200, json={**VERSION, "sample_precomputed": False})
    assert "sample" in _fail(_transport(HEALTHY, answers={"/api/version": stale}))
