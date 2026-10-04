"""Check a deployed VART: UI served from the CDN, health ok, workspace cookie, version.

python scripts/smoke.py https://vart.vercel.app

Prints one "ok:" line and exits 0, or one "FAIL: <check>: <reason>" line and exits 1.
"""

import argparse
from typing import Any

import httpx


def fail(name: str, reason: str, got: object = None) -> SystemExit:
    seen = "" if got is None else f", got {str(got)[:200]!r}"  # repr keeps a multi-line page on one line
    return SystemExit(f"FAIL: {name}: {reason}{seen}")


def get(c: httpx.Client, name: str, path: str) -> httpx.Response:
    """GET `path`. An unreachable deploy (connect error, timeout, ...) or any status but 200 fails `name`."""
    try:
        response = c.get(path)
    except httpx.HTTPError as e:
        raise fail(name, f"GET {path} failed: {e!r}") from e
    if response.status_code != 200:
        raise fail(name, f"GET {path} answered {response.status_code}", response.text)
    return response


def get_json(c: httpx.Client, name: str, path: str) -> dict[str, Any]:
    response = get(c, name, path)
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise fail(name, f"GET {path} did not answer a JSON object", response.text)
    return body


def check(c: httpx.Client) -> str:
    ui = get(c, "UI", "/").text
    if 'id="root"' not in ui:
        raise fail("UI", 'GET / has no id="root" (the PriorPath cdn=true incident looked like this)', ui)
    health = get_json(c, "health", "/api/health")
    if health.get("status") != "ok":
        raise fail("health", 'GET /api/health is not "status": "ok"', health)
    ws = get(c, "workspace cookie", "/api/workspace")
    if "vart_ws=" not in ws.headers.get("set-cookie", ""):
        raise fail(
            "workspace cookie", "GET /api/workspace set no vart_ws cookie", ws.headers.get("set-cookie")
        )
    version = get_json(c, "version", "/api/version")
    if not isinstance(version.get("version"), str):
        raise fail("version", 'GET /api/version has no string "version"', version)
    return f"ok: version {version['version']}, canary {health.get('canary')}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_url")
    args = ap.parse_args()
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=60) as c:
        print(check(c))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
