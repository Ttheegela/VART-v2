from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.db.models import IpLimit
from app.services import ip_limits
from app.services.ip_limits import client_ip, hit, ip_hash, purge


def _request(headers: dict[str, str], client: tuple[str, int] | None = ("10.0.0.1", 1234)) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": client})


def test_client_ip_prefers_x_real_ip_then_forwarded_for_then_the_socket() -> None:
    assert client_ip(_request({"x-real-ip": "1.1.1.1", "x-forwarded-for": "2.2.2.2"})) == "1.1.1.1"
    assert client_ip(_request({"x-forwarded-for": "2.2.2.2, 3.3.3.3"})) == "2.2.2.2"
    assert client_ip(_request({})) == "10.0.0.1"
    assert client_ip(_request({}, client=None)) == "unknown"


def test_ip_hash_is_keyed_and_short() -> None:
    assert ip_hash("1.1.1.1", "a") != ip_hash("1.1.1.1", "b")
    assert len(ip_hash("1.1.1.1", "a")) == 32


def test_ip_hash_refuses_an_empty_secret() -> None:
    with pytest.raises(RuntimeError, match="SESSION_SECRET is not set"):
        ip_hash("1.1.1.1", "")


def test_retry_after_is_the_time_left_in_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(ip_limits.LIMITS, "upload", (2, timedelta(hours=1)))
    start = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    assert ip_limits.retry_after("upload", start) == 3600
    assert ip_limits.retry_after("upload", start + timedelta(minutes=30)) == 1800
    assert ip_limits.retry_after("upload", start + timedelta(seconds=3599, milliseconds=500)) == 1


def test_hits_over_the_limit_are_refused(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(ip_limits.LIMITS, "upload", (2, timedelta(hours=1)))
    now = datetime(2026, 10, 3, 12, 30, tzinfo=UTC)
    with Session(db) as s:
        assert [hit(s, "ipA", "upload", now) for _ in range(3)] == [True, True, False]
        assert hit(s, "ipA", "upload", now + timedelta(hours=1)) is True  # next window
        assert hit(s, "ipB", "upload", now) is True


def test_concurrent_hits_count_every_event(db: Engine) -> None:
    now = datetime(2026, 10, 3, 12, 30, tzinfo=UTC)

    def one(_: int) -> None:
        with Session(db) as s:
            hit(s, "ipC", "upload", now)
            s.commit()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(one, range(16)))
    with Session(db) as s:
        assert s.scalar(select(IpLimit.hits).where(IpLimit.ip_hash == "ipC")) == 16


def test_purge_drops_windows_older_than_two_days(db: Engine) -> None:
    now = datetime(2026, 10, 3, tzinfo=UTC)
    with Session(db) as s:
        hit(s, "old", "upload", now - timedelta(days=3))
        hit(s, "new", "upload", now)
        assert purge(s, now) == 1
        s.commit()
        assert [r for (r,) in s.execute(select(IpLimit.ip_hash))] == ["new"]
