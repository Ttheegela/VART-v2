"""Check a deployed VART: UI served from the CDN, health ok, workspace cookie, version.

python scripts/smoke.py https://vart.vercel.app
"""

import argparse

import httpx


def fail(what: str, got: object) -> SystemExit:
    return SystemExit(f"FAIL: {what} — got {str(got)[:300]}")


def check(c: httpx.Client) -> str:
    root = c.get("/")
    if root.status_code != 200 or 'id="root"' not in root.text:
        raise fail("UI at / (the PriorPath cdn=true incident looked like this)", root.text)
    health = c.get("/api/health")
    if health.status_code != 200 or '"status":"ok"' not in health.text.replace(" ", ""):
        raise fail("health", health.text)
    ws = c.get("/api/workspace")
    if ws.status_code != 200 or "vart_ws=" not in ws.headers.get("set-cookie", ""):
        raise fail("workspace cookie", ws.headers)
    version = c.get("/api/version").json()
    return f"ok: version {version['version']}, canary {health.json().get('canary')}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_url")
    args = ap.parse_args()
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=60) as c:
        print(check(c))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
