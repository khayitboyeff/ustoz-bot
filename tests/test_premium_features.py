from __future__ import annotations

from datetime import datetime, timedelta, timezone

import database.db as db
from content.ctf_challenges import CTF_CHALLENGES
from database.features import get_ctf_challenge
from services import payment_service
from services.ctf_service import challenges, hint, submit


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "features.sqlite3")
    db.init_db()
    db.ensure_user(7654321, "learner", "Learner", "Test")


def test_invoice_payload_is_signed_and_bound_to_user(monkeypatch):
    monkeypatch.setattr(payment_service, "BOT_TOKEN", "test-token-not-real")
    payload = payment_service.create_invoice_payload(12345)
    assert payment_service.verify_invoice_payload(payload, 12345)
    assert not payment_service.verify_invoice_payload(payload, 54321)
    assert not payment_service.verify_invoice_payload(payload + "x", 12345)


def test_verified_payment_is_atomic_idempotent_and_extends_expiry(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    first = payment_service.apply_verified_payment("charge-001", 7654321, 100, "XTR", days=30)
    assert first is True
    status1 = db.get_user(7654321)
    assert status1["is_premium"] == 1
    first_expiry = datetime.fromisoformat(status1["premium_expires_at"].replace("Z", "+00:00"))
    second = payment_service.apply_verified_payment("charge-001", 7654321, 100, "XTR", days=30)
    assert second is False
    status2 = db.get_user(7654321)
    second_expiry = datetime.fromisoformat(status2["premium_expires_at"].replace("Z", "+00:00"))
    assert second_expiry == first_expiry
    assert payment_service.apply_verified_payment("charge-002", 7654321, 100, "XTR", days=30)
    status3 = db.get_user(7654321)
    third_expiry = datetime.fromisoformat(status3["premium_expires_at"].replace("Z", "+00:00"))
    assert third_expiry >= first_expiry + timedelta(days=29)


def test_premium_ctf_is_blocked_for_free_user_and_awards_once(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    items = challenges()
    premium_item = next(item for item in items if item["is_premium"])
    result = submit(7654321, premium_item["id"], "placeholder")
    assert result["reason"] == "premium"

    db.update_user_premium(
        7654321,
        True,
        (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(timespec="seconds").replace("+00:00", "Z"),
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        source="admin_test",
    )
    source = next(item for item in CTF_CHALLENGES if item["slug"] == premium_item["slug"])
    solved = submit(7654321, premium_item["id"], source["answer"])
    assert solved["ok"] is True
    assert solved["awarded"] == premium_item["points"]
    repeated = submit(7654321, premium_item["id"], source["answer"])
    assert repeated["ok"] is True
    assert repeated["awarded"] == 0


def test_ctf_hint_usage_is_recorded_without_revealing_answer(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    item = next(challenge for challenge in challenges() if not challenge["is_premium"])
    first = hint(7654321, item["id"])
    second = hint(7654321, item["id"])
    assert first["hint"]
    assert first["hints_used"] == 1
    assert second["hints_used"] == 2


def test_ai_tutor_sends_bounded_history_and_returns_provider_text(monkeypatch):
    import json
    from services import ai_service

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "Defensive answer"}}]}).encode()

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(ai_service, "AI_API_KEY", "test-key")
    monkeypatch.setattr(ai_service, "AI_BASE_URL", "https://ai.example/v1")
    monkeypatch.setattr(ai_service, "AI_MODEL", "test-model")
    monkeypatch.setattr(ai_service, "AI_TIMEOUT_SECONDS", 10)
    monkeypatch.setattr(ai_service, "increment_ai_usage", lambda user_id, limit: True)
    monkeypatch.setattr(ai_service, "has_active_premium", lambda user_id: False)
    monkeypatch.setattr(ai_service.urllib.request, "urlopen", fake_urlopen)

    history = [{"role": "user", "content": "Old question"}, {"role": "assistant", "content": "Old answer"}]
    result = ai_service.ask_tutor(7654321, "How do I harden SSH?", "en", history)

    assert result["ok"] is True
    assert result["text"] == "Defensive answer"
    assert captured["payload"]["messages"][0]["role"] == "system"
    assert captured["payload"]["messages"][1:3] == history
    assert captured["payload"]["messages"][-1]["content"] == "How do I harden SSH?"
    assert captured["timeout"] == 10


def test_manual_receipt_approval_is_admin_reviewable_and_idempotent(tmp_path, monkeypatch):
    import database.db as db
    from services.manual_payment_service import create_request, review_request, PLAN_PRICES_UZS

    _db(tmp_path, monkeypatch)
    request_id = create_request(7654321, 3, PLAN_PRICES_UZS[3], "fake-file-id", "photo")
    approved = review_request(request_id, 999, approve=True, months=3)
    assert approved["ok"] is True
    assert approved["days"] == 90
    user = db.get_user(7654321)
    assert user["is_premium"] == 1
    expiry1 = user["premium_expires_at"]
    duplicate = review_request(request_id, 999, approve=True, months=3)
    assert duplicate["ok"] is False
    assert db.get_user(7654321)["premium_expires_at"] == expiry1


def test_manual_receipt_rejection_never_grants_premium(tmp_path, monkeypatch):
    import database.db as db
    from services.manual_payment_service import create_request, review_request, PLAN_PRICES_UZS

    _db(tmp_path, monkeypatch)
    request_id = create_request(7654321, 1, PLAN_PRICES_UZS[1], "receipt-id", "document")
    result = review_request(request_id, 999, approve=False)
    assert result["ok"] is True
    assert result["status"] == "rejected"
    assert db.get_user(7654321)["is_premium"] == 0


def test_custom_lesson_supports_video_url_and_file(tmp_path, monkeypatch):
    import database.db as db
    from services.lesson_service import create_custom_lesson, list_custom_lessons, attach_video_file

    _db(tmp_path, monkeypatch)
    lesson_id = create_custom_lesson("Xavfsiz dars", "Bu yangi dars uchun yetarlicha uzun o‘quv matnidir.", "https://example.com/video", 999)
    assert attach_video_file(lesson_id, "telegram-file-id")
    lesson = next(item for item in list_custom_lessons() if item["id"] == lesson_id)
    assert lesson["video_url"] == "https://example.com/video"
    assert lesson["video_file_id"] == "telegram-file-id"


def test_referral_milestones_are_granted_once(tmp_path, monkeypatch):
    import database.db as db
    from services.referral_rewards import grant_available_referral_rewards

    _db(tmp_path, monkeypatch)
    with db.get_connection() as conn:
        conn.execute("INSERT INTO users(telegram_id, username, first_name, last_name, referral_code) VALUES(?, ?, ?, ?, ?)",
                     (7654322, "inviter", "Invite", "R", "REFCODE"))
        for i in range(15):
            conn.execute("INSERT INTO users(telegram_id, username) VALUES(?, ?)", (8000000+i, f"invite{i}"))
            conn.execute("INSERT INTO referrals(invitee_id, referrer_id, bonus_granted) VALUES(?, ?, 0)", (8000000+i, 7654322))
        conn.commit()
    first = grant_available_referral_rewards(7654322)
    assert first == [{"milestone": 15, "days": 30, "total_days": 30}]
    assert grant_available_referral_rewards(7654322) == []
    with db.get_connection() as conn:
        for i in range(15, 30):
            conn.execute("INSERT INTO users(telegram_id, username) VALUES(?, ?)", (8000000+i, f"invite{i}"))
            conn.execute("INSERT INTO referrals(invitee_id, referrer_id, bonus_granted) VALUES(?, ?, 0)", (8000000+i, 7654322))
        conn.commit()
    second = grant_available_referral_rewards(7654322)
    assert second == [{"milestone": 30, "days": 60, "total_days": 90}]
    assert grant_available_referral_rewards(7654322) == []


def test_pending_receipt_blocks_duplicate_and_amount_mismatch(tmp_path, monkeypatch):
    import database.db as db
    from services.manual_payment_service import create_request, review_request, PLAN_PRICES_UZS

    _db(tmp_path, monkeypatch)
    request_id = create_request(7654321, 1, PLAN_PRICES_UZS[1], "receipt-first", "photo")
    try:
        create_request(7654321, 1, PLAN_PRICES_UZS[1], "receipt-second", "photo")
    except ValueError as exc:
        assert "tekshiruvda" in str(exc)
    else:
        raise AssertionError("A user must not create multiple pending receipts")
    mismatch = review_request(request_id, 999, approve=True, months=12)
    assert mismatch == {"ok": False, "reason": "amount_mismatch", "telegram_id": 7654321}
    assert db.get_user(7654321)["is_premium"] == 0
    assert review_request(request_id, 999, approve=True, months=1)["ok"] is True


def test_admin_stats_include_stars_and_pending_receipt_counts(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO payments(provider_event_id, telegram_id, amount_minor, currency, status) VALUES (?, ?, ?, ?, ?)",
            ("stars-charge-test", 7654321, 50, "XTR", "successful"),
        )
        conn.commit()
    stats = db.get_admin_stats()
    assert stats["successful_payments"] == 1
    assert stats["stars_payments_count"] == 1
    assert stats["stars_received"] == 50
    assert stats["pending_manual_payments"] == 0
