from __future__ import annotations

import asyncio
import ipaddress
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import requests

import bot
import database.db as db
import handlers.admin as admin
from handlers import rate_limit
from handlers.admin import admin_command, is_admin, register_admin_handlers
from handlers.tools import _dns_result_text, _ip_result_text, _safe_display, ask_dns_domain, ask_ip_address
from services.dns_service import lookup_dns_records, validate_domain_name
from services.ip_service import get_ip_details, validate_ip_address, validate_ipv4_address
from services.osint_service import check_public_username
from telegram.ext import Application, CallbackQueryHandler


def test_rate_limit_is_per_user_and_scope() -> None:
    rate_limit._last_requests.clear()

    assert rate_limit.consume_rate_limit(101, "dns", 5, now=10) is False
    assert rate_limit.consume_rate_limit(101, "dns", 5, now=12) is True
    assert rate_limit.consume_rate_limit(102, "dns", 5, now=12) is False
    assert rate_limit.consume_rate_limit(101, "ip", 5, now=12) is False
    assert rate_limit.consume_rate_limit(101, "dns", 5, now=15) is False


def test_rate_limit_decorator_blocks_repeated_handler_call(monkeypatch) -> None:
    rate_limit._last_requests.clear()
    handler_calls = []

    async def handler(update, context):
        handler_calls.append(update.effective_user.id)

    protected = rate_limit.rate_limited("test_scope", 30)(handler)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=801), callback_query=None)

    asyncio.run(protected(update, SimpleNamespace()))
    asyncio.run(protected(update, SimpleNamespace()))

    assert handler_calls == [801]


def test_sql_values_are_parameterized_and_table_survives(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "users.sqlite3")
    db.init_db()
    injected_value = "'); DROP TABLE users; --"

    db.ensure_user(701, injected_value, injected_value, "User")

    assert db.get_user(701)["username"] == injected_value
    with db.get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


@pytest.mark.parametrize("score", [-1, 11, 100000, True, 1.5])
def test_invalid_quiz_scores_are_rejected(monkeypatch, tmp_path, score) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "scores.sqlite3")
    db.init_db()
    db.ensure_user(702)

    with pytest.raises(ValueError):
        db.update_quiz_result(702, score)


def test_premium_duration_is_bounded_and_missing_user_rejected(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "premium.sqlite3")
    db.init_db()
    db.ensure_user(703)
    now = datetime.now()
    too_far = (now + timedelta(days=3651)).strftime("%Y-%m-%d %H:%M:%S")

    with pytest.raises(ValueError):
        db.update_user_premium(703, True, too_far, now.strftime("%Y-%m-%d %H:%M:%S"))
    with pytest.raises(LookupError):
        db.update_user_premium(704, False)


def test_dns_validation_rejects_local_names_and_private_answers(monkeypatch) -> None:
    assert validate_domain_name("localhost") is False
    assert validate_domain_name("service.internal") is False
    assert validate_domain_name("a" * 250 + ".com") is False
    assert validate_domain_name("-bad.example.com") is False

    class FakeResolver:
        timeout = 0
        lifetime = 0

        def resolve(self, domain: str, record_type: str):
            if record_type == "A":
                return ["127.0.0.1", "10.0.0.2", "8.8.8.8"]
            if record_type == "AAAA":
                return ["::1", "2001:4860:4860::8888"]
            return []

    monkeypatch.setattr("services.dns_service.dns.resolver.Resolver", FakeResolver)
    records = lookup_dns_records("example.com")

    assert records["A"] == ["8.8.8.8"]
    assert records["AAAA"] == ["2001:4860:4860::8888"]
    assert all(ipaddress.ip_address(value).is_global for value in records["A"] + records["AAAA"])


def test_ip_validation_rejects_overlong_values() -> None:
    assert validate_ipv4_address("8.8.8.8") is True
    assert validate_ipv4_address("8" * 100) is False
    assert validate_ipv4_address(None) is False
    assert validate_ip_address("2001:4860:4860::8888") is True
    assert validate_ip_address("2001::bad-ip") is False


def test_ipwhois_key_is_not_forwarded_to_fallback(monkeypatch) -> None:
    requests_seen = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ip": "8.8.8.8", "country": "Example"}

    def fake_get(url, **kwargs):
        requests_seen.append((url, kwargs))
        if "ipwho.is" in url:
            raise requests.ConnectionError("provider unavailable")
        return FakeResponse()

    monkeypatch.setattr("services.ip_service.requests.get", fake_get)
    result = get_ip_details("8.8.8.8", api_key="test-secret")

    assert result["status"] == "ok"
    assert requests_seen[0][1]["params"]["access_key"] == "test-secret"
    assert "access_key" not in requests_seen[1][1]["params"]
    assert requests_seen[0][1]["timeout"] == (3, 6)


def test_username_osint_disables_redirects_and_rejects_invalid_input(monkeypatch) -> None:
    calls = []

    class FakeResponse:
        status_code = 302

    def fake_get(url, **kwargs):
        calls.append(kwargs)
        return FakeResponse()

    monkeypatch.setattr("services.osint_service.requests.get", fake_get)
    assert check_public_username("@@admin") == []
    assert check_public_username("x" * 51) == []
    result = check_public_username("@public_user")

    assert len(result) == 3
    assert all(call["allow_redirects"] is False for call in calls)
    assert all(call["timeout"] == (3, 5) for call in calls)


def test_empty_ip_and_dns_inputs_are_rejected_without_network(monkeypatch) -> None:
    monkeypatch.setattr("handlers.tools.get_ip_details", lambda *_: pytest.fail("IP lookup should not run"))
    monkeypatch.setattr("handlers.tools.lookup_dns_records_async", lambda *_args, **_kwargs: pytest.fail("DNS lookup should not run"))

    assert asyncio.run(_ip_result_text("")) == "IP manzil kiritilmadi."
    assert asyncio.run(_dns_result_text("")) == "Domen nomi kiritilmadi."


def test_ip_and_dns_inline_callbacks_tolerate_missing_command_args() -> None:
    rate_limit._last_requests.clear()

    async def make_update(user_id, callback_data):
        query = SimpleNamespace(
            data=callback_data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=user_id),
            effective_message=SimpleNamespace(),
        )
        context = SimpleNamespace(args=None, user_data={})
        return update, context, query

    async def run():
        ip_update, ip_context, ip_query = await make_update(811, "menu:ip")
        await ask_ip_address(ip_update, ip_context)
        assert ip_context.user_data["pending_lookup"] == "ip"
        assert "IPv4 yoki IPv6" in ip_query.edit_message_text.await_args.args[0]

        dns_update, dns_context, dns_query = await make_update(812, "menu:dns")
        await ask_dns_domain(dns_update, dns_context)
        assert dns_context.user_data["pending_lookup"] == "dns"
        assert "Domen nomini yuboring" in dns_query.edit_message_text.await_args.args[0]

    asyncio.run(run())


def test_ip_lookup_supports_ipv6_and_service_failure(monkeypatch) -> None:
    address = "2001:4860:4860::8888"
    monkeypatch.setattr(
        "handlers.tools.get_ip_details",
        lambda value: {
            "status": "ok", "ip": value, "country": "Example", "region": "Region",
            "city": "City", "provider": "Provider", "type": "IPv6",
        },
    )
    successful_text = asyncio.run(_ip_result_text(address))
    assert f"IP: {address}" in successful_text
    assert "Tizim: IPv6" in successful_text

    monkeypatch.setattr("handlers.tools.get_ip_details", lambda *_: {"status": "error", "message": "xizmat ishlamadi"})
    assert "xizmat ishlamadi" in asyncio.run(_ip_result_text(address))


def test_dns_lookup_formats_results_and_handles_timeout(monkeypatch) -> None:
    async def successful_lookup(domain, timeout):
        return {"A": ["8.8.8.8"], "AAAA": [], "MX": ["mx.example.com"], "NS": []}

    monkeypatch.setattr(
        "handlers.tools.lookup_dns_records_async",
        successful_lookup,
    )
    result = asyncio.run(_dns_result_text("example.com"))
    assert "A: 8.8.8.8" in result
    assert "MX: mx.example.com" in result
    assert "AAAA: topilmadi" in result

    async def timeout_async(_domain, timeout):
        raise TimeoutError("DNS timeout")

    monkeypatch.setattr("handlers.tools.lookup_dns_records_async", timeout_async)
    assert "DNS tekshiruvini hozir bajarib bo‘lmadi" in asyncio.run(_dns_result_text("example.com"))


def test_invalid_ip_and_dns_values_are_rejected_without_network(monkeypatch) -> None:
    monkeypatch.setattr("handlers.tools.get_ip_details", lambda *_: pytest.fail("Invalid IP reached service"))
    monkeypatch.setattr("handlers.tools.lookup_dns_records_async", lambda *_args, **_kwargs: pytest.fail("Invalid domain reached resolver"))

    assert "IPv4 yoki IPv6" in asyncio.run(_ip_result_text("not-an-ip"))
    assert "Noto‘g‘ri domen" in asyncio.run(_dns_result_text("bad domain"))
    assert "juda uzun" in asyncio.run(_dns_result_text("a" * 300))


def test_pending_ip_state_routes_invalid_ipv6_to_ip_error(monkeypatch) -> None:
    from handlers.start import handle_unknown_text

    reply_text = AsyncMock()
    message = SimpleNamespace(text="2001::not-ip", reply_text=reply_text)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=813),
        effective_message=message,
        message=message,
        callback_query=None,
    )
    context = SimpleNamespace(user_data={"pending_lookup": "ip"})
    rate_limit._last_requests.clear()

    asyncio.run(handle_unknown_text(update, context))

    assert "IPv4 yoki IPv6" in reply_text.await_args.args[0]
    assert "pending_lookup" not in context.user_data


def test_pending_dns_state_routes_invalid_value_to_dns_error() -> None:
    from handlers.start import handle_unknown_text

    reply_text = AsyncMock()
    message = SimpleNamespace(text="not a domain", reply_text=reply_text)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=814),
        effective_message=message,
        message=message,
        callback_query=None,
    )
    context = SimpleNamespace(user_data={"pending_lookup": "dns"})
    rate_limit._last_requests.clear()

    asyncio.run(handle_unknown_text(update, context))

    assert "Noto‘g‘ri domen" in reply_text.await_args.args[0]
    assert "pending_lookup" not in context.user_data


def test_osint_http_timeout_is_handled(monkeypatch) -> None:
    def fail_request(*args, **kwargs):
        assert kwargs["timeout"] == (3, 5)
        raise requests.Timeout("provider timed out")

    monkeypatch.setattr("services.osint_service.requests.get", fail_request)

    results = check_public_username("safe_username")

    assert len(results) == 3
    assert [result["platform"] for result in results] == ["Telegram", "Instagram", "GitHub"]
    assert results[2]["status"] == "tarmoq/API mavjud emas; profil havolasini qo‘lda tekshiring"


def test_non_admin_is_not_authorized(monkeypatch) -> None:
    monkeypatch.setattr("handlers.admin.ADMIN_IDS", [9001])
    assert is_admin(9002) is False
    assert is_admin(9001) is True


def test_non_admin_cannot_change_premium(monkeypatch) -> None:
    reply_text = AsyncMock()
    message = SimpleNamespace(text="/admin_premium 703 true 30", reply_text=reply_text)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=9002),
        effective_message=message,
        callback_query=None,
    )
    premium_update = Mock()
    monkeypatch.setattr(admin, "ADMIN_IDS", [9001])
    monkeypatch.setattr(admin, "grant_admin_test_premium", premium_update)

    asyncio.run(admin_command(update, SimpleNamespace(args=["703", "true", "30"])))

    premium_update.assert_not_called()
    assert "admin huquqi" in reply_text.await_args.args[0]


def test_admin_broadcast_callback_is_narrowly_registered_and_server_authorized(monkeypatch) -> None:
    application = Application.builder().token("123456:TEST_TOKEN").build()
    register_admin_handlers(application)

    callbacks = [
        handler
        for handlers in application.handlers.values()
        for handler in handlers
        if isinstance(handler, CallbackQueryHandler)
    ]
    broadcast_callbacks = [handler for handler in callbacks if handler.pattern.pattern == r"^broadcast:(confirm|cancel):\d+$"]
    assert len(broadcast_callbacks) == 1

    import handlers.admin as admin
    reply = AsyncMock()
    query = SimpleNamespace(data="broadcast:confirm:1", answer=AsyncMock(), message=SimpleNamespace(reply_text=reply))
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=44))
    monkeypatch.setattr(admin, "ADMIN_IDS", [99])
    asyncio.run(admin.broadcast_callback(update, SimpleNamespace()))
    query.answer.assert_awaited_once()
    assert query.answer.await_args.kwargs["show_alert"] is True


def test_config_uses_environment_variables_and_dotenv_fallback(tmp_path) -> None:
    source = Path(__file__).resolve().parents[1] / "config.py"
    env = os.environ.copy()
    env.update({
        "BOT_TOKEN": "host-token-placeholder",
        "ADMIN_IDS": "999999",
        "IPWHOIS_API_KEY": "host-key-placeholder",
    })
    empty_env_dir = tmp_path / "without-env"
    empty_env_dir.mkdir()
    shutil.copy2(source, empty_env_dir / "config.py")
    no_file = subprocess.run(
        [sys.executable, "-c", "import config; assert config.BOT_TOKEN == 'host-token-placeholder'; assert config.ADMIN_IDS == [999999]; assert config.IPWHOIS_API_KEY == 'host-key-placeholder'"],
        cwd=empty_env_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert no_file.returncode == 0, "Configuration did not read process environment variables."

    dotenv_dir = tmp_path / "with-env"
    dotenv_dir.mkdir()
    shutil.copy2(source, dotenv_dir / "config.py")
    (dotenv_dir / ".env").write_text(
        "BOT_TOKEN=file-token-placeholder\\nADMIN_IDS=901,902\\nIPWHOIS_API_KEY=file-key-placeholder\\n",
        encoding="utf-8",
    )
    with_file = subprocess.run(
        [sys.executable, "-c", "import config; assert config.BOT_TOKEN == 'host-token-placeholder'; assert config.ADMIN_IDS == [999999]; assert config.IPWHOIS_API_KEY == 'host-key-placeholder'"],
        cwd=dotenv_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert with_file.returncode == 0, "Process environment did not take precedence over .env."

def test_global_error_log_does_not_include_exception_message(caplog) -> None:
    context = SimpleNamespace(error=RuntimeError("BOT_TOKEN=must-not-be-logged"))

    asyncio.run(bot.handle_update_error(None, context))

    assert "must-not-be-logged" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_external_text_is_sanitized_before_display() -> None:
    assert _safe_display("safe\nINJECTED\x00") == "safe INJECTED"
    assert len(_safe_display("x" * 500)) == 120