from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re

from config import BOT_TOKEN, PAYMENT_AMOUNT_MINOR, PAYMENT_CURRENCY, PAYMENT_PROVIDER, PAYMENT_PROVIDER_TOKEN

PREMIUM_DAYS = 30

@dataclass(frozen=True)
class PaymentReadiness:
    provider: str
    configured: bool
    message: str


def get_payment_readiness() -> PaymentReadiness:
    currency = PAYMENT_CURRENCY.upper()
    valid_currency = bool(re.fullmatch(r"[A-Z]{3}|XTR", currency))
    if PAYMENT_PROVIDER in {"telegram", "stars"} and PAYMENT_AMOUNT_MINOR > 0 and valid_currency:
        if currency == "XTR" and PAYMENT_PROVIDER in {"telegram", "stars"}:
            return PaymentReadiness(PAYMENT_PROVIDER, True, "Telegram Stars orqali 30 kunlik Premium xaridi mavjud.")
        if PAYMENT_PROVIDER == "telegram" and PAYMENT_PROVIDER_TOKEN:
            return PaymentReadiness("telegram", True, "Telegram Payments provider sozlangan.")
    return PaymentReadiness("none", False, "Checkout sozlanmagan. Xarid yoqilishi uchun PAYMENT_PROVIDER, PAYMENT_CURRENCY, PAYMENT_AMOUNT_MINOR va kerak bo‘lsa provider tokenini sozlang.")


def create_invoice_payload(telegram_id: int) -> str:
    if type(telegram_id) is not int or telegram_id <= 0 or not BOT_TOKEN:
        raise ValueError("Invoice uchun foydalanuvchi yoki bot konfiguratsiyasi yaroqsiz.")
    body = f"premium30:{telegram_id}"
    signature = hmac.new(BOT_TOKEN.encode(), body.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{body}:{signature}"


def verify_invoice_payload(payload: str, telegram_id: int) -> bool:
    if not isinstance(payload, str) or len(payload) > 128 or type(telegram_id) is not int:
        return False
    parts = payload.split(":")
    if len(parts) != 3 or parts[0] != "premium30":
        return False
    try:
        owner_id = int(parts[1])
    except ValueError:
        return False
    if owner_id != telegram_id or owner_id <= 0 or not BOT_TOKEN:
        return False
    expected = create_invoice_payload(owner_id)
    return hmac.compare_digest(expected, payload)


def apply_verified_payment(provider_event_id: str, telegram_id: int, amount_minor: int, currency: str, days: int = PREMIUM_DAYS) -> bool:
    """Persist a verified charge and extend Premium atomically; duplicate charges are no-ops."""
    from database.db import _utc_timestamp, get_connection, _parse_datetime

    if not provider_event_id or len(provider_event_id) > 128:
        raise ValueError("To‘lov identifikatori yaroqsiz.")
    if type(telegram_id) is not int or telegram_id <= 0:
        raise ValueError("Foydalanuvchi ID yaroqsiz.")
    if type(amount_minor) is not int or amount_minor <= 0:
        raise ValueError("To‘lov summasi yaroqsiz.")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}|XTR", currency):
        raise ValueError("To‘lov valyutasi yaroqsiz.")
    if type(days) is not int or not 1 <= days <= 3650:
        raise ValueError("Premium muddati 1–3650 kun oralig‘ida bo‘lishi kerak.")

    now = datetime.now(timezone.utc)
    now_s = _utc_timestamp(now)
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM payments WHERE provider_event_id = ?", (provider_event_id,)).fetchone():
            conn.rollback()
            return False
        user = conn.execute("SELECT is_premium, premium_started_at, premium_expires_at FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if user is None:
            conn.rollback()
            raise LookupError("To‘lov egasi bazada topilmadi.")
        old_expiry = _parse_datetime(user["premium_expires_at"])
        active = bool(user["is_premium"]) and old_expiry is not None and old_expiry > now
        base = old_expiry if active else now
        expires = _utc_timestamp(base + timedelta(days=days))
        started = user["premium_started_at"] if active and user["premium_started_at"] else now_s
        conn.execute(
            "INSERT INTO payments (provider_event_id, telegram_id, amount_minor, currency, status) VALUES (?, ?, ?, ?, 'successful')",
            (provider_event_id, telegram_id, amount_minor, currency),
        )
        conn.execute(
            "UPDATE users SET is_premium = 1, premium_started_at = ?, premium_expires_at = ?, premium_source = 'payment' WHERE telegram_id = ?",
            (started, expires, telegram_id),
        )
        conn.commit()
    return True
