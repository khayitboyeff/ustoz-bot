from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import dns.exception
import dns.resolver

from database.db import ensure_user, get_admin_stats, get_leaderboard, get_user, init_db, update_quiz_result, update_user_premium
from services.dns_service import lookup_dns_records, lookup_dns_records_async, validate_domain_name
from services.ip_service import validate_ipv4_address
from services.osint_service import check_public_username


def test_validate_ipv4_address() -> None:
    assert validate_ipv4_address("8.8.8.8") is True
    assert validate_ipv4_address("127.0.0.1") is True
    assert validate_ipv4_address("not-an-ip") is False


def test_validate_domain_name() -> None:
    assert validate_domain_name("example.com") is True
    assert validate_domain_name("bad domain") is False
    assert validate_domain_name("localhost") is False


def test_lookup_dns_records(monkeypatch) -> None:
    class FakeAnswer:
        def __init__(self, value: str):
            self.value = value

        def __str__(self) -> str:
            return self.value

    class FakeResolver:
        def __init__(self) -> None:
            self.timeout = 0
            self.lifetime = 0

        def resolve(self, domain: str, record_type: str):
            mapping = {
                "A": [FakeAnswer("93.184.216.34")],
                "AAAA": [],
                "MX": [FakeAnswer("mail.example.com")],
                "NS": [FakeAnswer("ns1.example.com")],
            }
            if record_type not in mapping:
                raise ValueError("Unsupported type")
            return mapping[record_type]

    monkeypatch.setattr("services.dns_service.dns.resolver.Resolver", FakeResolver)
    result = lookup_dns_records("example.com")
    assert result["A"] == ["93.184.216.34"]
    assert result["MX"] == ["mail.example.com"]


def test_async_dns_resolves_records_with_timeout(monkeypatch) -> None:
    class FakeAnswer:
        def __init__(self, value: str):
            self.value = value

        def __str__(self) -> str:
            return self.value

    class FakeResolver:
        timeout = 0
        lifetime = 0

        async def resolve(self, domain: str, record_type: str, lifetime: float):
            assert domain == "example.com"
            assert lifetime == 5
            mapping = {
                "A": [FakeAnswer("93.184.216.34")],
                "AAAA": [FakeAnswer("2606:2800:220:1:248:1893:25c8:1946")],
                "MX": [],
                "NS": [],
            }
            if record_type in {"MX", "NS"}:
                raise dns.resolver.NoAnswer
            return mapping[record_type]

    monkeypatch.setattr("services.dns_service.dns.asyncresolver.Resolver", FakeResolver)
    result = asyncio.run(lookup_dns_records_async("example.com", timeout=5))

    assert result["A"] == ["93.184.216.34"]
    assert result["AAAA"] == ["2606:2800:220:1:248:1893:25c8:1946"]


def test_async_dns_timeout_is_reported_and_does_not_log_domain(monkeypatch, caplog) -> None:
    class FakeResolver:
        timeout = 0
        lifetime = 0

        async def resolve(self, domain: str, record_type: str, lifetime: float):
            raise dns.exception.Timeout

    monkeypatch.setattr("services.dns_service.dns.asyncresolver.Resolver", FakeResolver)

    try:
        asyncio.run(lookup_dns_records_async("example.com", timeout=5))
    except TimeoutError:
        pass
    else:
        raise AssertionError("Expected DNS timeout to be reported")
    assert "example.com" not in caplog.text
    assert "Timeout" in caplog.text


def test_async_dns_queries_record_types_concurrently(monkeypatch) -> None:
    started: set[str] = set()
    all_started = asyncio.Event()

    class FakeResolver:
        timeout = 0
        lifetime = 0

        async def resolve(self, domain: str, record_type: str, lifetime: float):
            started.add(record_type)
            if len(started) == 4:
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=0.25)
            raise dns.resolver.NoAnswer

    monkeypatch.setattr("services.dns_service.dns.asyncresolver.Resolver", FakeResolver)
    result = asyncio.run(lookup_dns_records_async("example.com", timeout=1))

    assert started == {"A", "AAAA", "MX", "NS"}
    assert all(not result[record_type] for record_type in started)


def test_check_public_username(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

    monkeypatch.setattr("services.osint_service.requests.get", lambda *args, **kwargs: FakeResponse())
    result = check_public_username("octocat")
    assert len(result) == 3
    assert all("platform" in item for item in result)


def test_admin_stats_and_premium_logic() -> None:
    init_db()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ensure_user(999901, "adminuser", "Admin", "User")
    ensure_user(999902, "plainuser", "Plain", "User")
    update_user_premium(999901, True, (now + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"), (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"))
    update_user_premium(999902, False, None, None)

    stats = get_admin_stats()
    assert stats["total_users"] >= 2
    assert stats["premium_users"] >= 1
    assert stats["avg_test_score"] >= 0

    user = get_user(999901)
    assert user is not None
    assert user["is_premium"] == 1
    assert user["premium_expires_at"] is not None


def test_leaderboard_uses_real_database_scores(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("database.db.DB_PATH", tmp_path / "leaderboard.sqlite3")
    init_db()
    ensure_user(1001, "top", "Top", "User")
    ensure_user(1002, "next", "Next", "User")
    ensure_user(1003, "no-score", "No", "Score")
    update_quiz_result(1001, 8)
    update_quiz_result(1002, 5)

    rows = get_leaderboard(limit=2)

    assert [row["telegram_id"] for row in rows] == [1001, 1002]
    assert [row["test_score"] for row in rows] == [8, 5]
