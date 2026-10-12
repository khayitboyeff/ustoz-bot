from __future__ import annotations

from datetime import datetime, timedelta, timezone

from config import ADMIN_IDS
from database.db import get_user
from database.db import update_user_premium


def get_premium_status(telegram_id: int) -> dict:
    user = get_user(telegram_id)
    if user is None:
        return {
            "is_active": False,
            "started_at": None,
            "expires_at": None,
            "source": "none",
        }
    return {
        "is_active": bool(user["is_premium"]),
        "started_at": user.get("premium_started_at"),
        "expires_at": user.get("premium_expires_at"),
        "source": user.get("premium_source", "none"),
    }


def has_active_premium(telegram_id: int) -> bool:
    return get_premium_status(telegram_id)["is_active"]


def _require_admin(actor_admin_id: int) -> None:
    if type(actor_admin_id) is not int or actor_admin_id not in ADMIN_IDS:
        raise PermissionError("Premium huquqini faqat sozlangan admin boshqarishi mumkin.")


def grant_admin_test_premium(telegram_id: int, actor_admin_id: int, days: int) -> None:
    _require_admin(actor_admin_id)
    if type(days) is not int or not 1 <= days <= 3650:
        raise ValueError("Premium muddati 1 dan 3650 kungacha bo‘lishi kerak.")
    status = get_premium_status(telegram_id)
    if status["source"] == "payment" and status["is_active"]:
        raise ValueError("To‘lov orqali berilgan Premium muddatini admin testi bilan o‘zgartirib bo‘lmaydi.")
    now = datetime.now(timezone.utc)
    base = now
    if status["is_active"] and status["expires_at"]:
        expiry = datetime.fromisoformat(status["expires_at"].replace("Z", "+00:00"))
        base = max(now, expiry)
    started = status["started_at"] if status["is_active"] and status["started_at"] else now.isoformat(timespec="seconds").replace("+00:00", "Z")
    expires = (base + timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")
    update_user_premium(
        telegram_id,
        True,
        expires,
        started,
        source="admin_test",
        actor_admin_id=actor_admin_id,
    )


def revoke_premium(telegram_id: int, actor_admin_id: int) -> None:
    _require_admin(actor_admin_id)
    update_user_premium(
        telegram_id,
        False,
        source="admin_test",
        actor_admin_id=actor_admin_id,
    )