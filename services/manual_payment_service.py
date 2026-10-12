from __future__ import annotations

from datetime import datetime, timedelta, timezone

from database.db import _parse_datetime, _utc_timestamp, get_connection

PLAN_PRICES_UZS = {1: 15_000, 3: 40_000, 6: 70_000, 12: 100_000}
PLAN_DAYS = {1: 30, 3: 90, 6: 180, 12: 365}


def create_request(telegram_id: int, months: int, amount: int, file_id: str, kind: str) -> int:
    if type(telegram_id) is not int or telegram_id <= 0:
        raise ValueError("Foydalanuvchi ID noto‘g‘ri.")
    if months not in PLAN_PRICES_UZS or amount != PLAN_PRICES_UZS[months]:
        raise ValueError("Tarif yoki summa noto‘g‘ri.")
    if not isinstance(file_id, str) or not file_id or len(file_id) > 1024:
        raise ValueError("Chek fayli yaroqsiz.")
    if kind not in {"photo", "document"}:
        raise ValueError("Faqat rasm yoki hujjat chek qabul qilinadi.")
    with get_connection() as conn:
        user = conn.execute("SELECT 1 FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        if not user:
            raise LookupError("Avval /start orqali ro‘yxatdan o‘ting.")
        pending = conn.execute(
            "SELECT id FROM manual_payment_requests WHERE telegram_id=? AND status='pending'",
            (telegram_id,),
        ).fetchone()
        if pending:
            raise ValueError(f"Sizda #{int(pending['id'])} raqamli chek tekshiruvda. Natijani kuting.")
        cur = conn.execute(
            """INSERT INTO manual_payment_requests
               (telegram_id, plan_months, amount_uzs, receipt_file_id, receipt_kind)
               VALUES (?, ?, ?, ?, ?)""",
            (telegram_id, months, amount, file_id, kind),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_request(request_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM manual_payment_requests WHERE id=?", (request_id,)).fetchone()
        return dict(row) if row else None


def review_request(request_id: int, admin_id: int, *, approve: bool, months: int | None = None) -> dict:
    """Atomically review one receipt. Replayed callbacks never grant Premium twice."""
    if type(request_id) is not int or request_id <= 0 or type(admin_id) is not int or admin_id <= 0:
        raise ValueError("So‘rov yoki admin ID noto‘g‘ri.")
    if approve and months not in PLAN_DAYS:
        raise ValueError("Obuna muddati 1, 3, 6 yoki 12 oy bo‘lishi kerak.")
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM manual_payment_requests WHERE id=?", (request_id,)).fetchone()
        if row is None:
            conn.rollback()
            return {"ok": False, "reason": "missing"}
        if row["status"] != "pending":
            conn.rollback()
            return {"ok": False, "reason": "already_reviewed", "telegram_id": int(row["telegram_id"])}
        if approve and int(row["amount_uzs"]) != PLAN_PRICES_UZS[int(months)]:
            conn.rollback()
            return {"ok": False, "reason": "amount_mismatch", "telegram_id": int(row["telegram_id"])}
        if not approve:
            conn.execute(
                "UPDATE manual_payment_requests SET status='rejected', reviewed_by=?, reviewed_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",
                (admin_id, request_id),
            )
            conn.commit()
            return {"ok": True, "status": "rejected", "telegram_id": int(row["telegram_id"])}

        user = conn.execute(
            "SELECT is_premium, premium_started_at, premium_expires_at FROM users WHERE telegram_id=?",
            (row["telegram_id"],),
        ).fetchone()
        if user is None:
            conn.rollback()
            return {"ok": False, "reason": "user_missing"}
        days = PLAN_DAYS[months]
        old_expiry = _parse_datetime(user["premium_expires_at"])
        active = bool(user["is_premium"]) and old_expiry is not None and old_expiry > now
        base = old_expiry if active else now
        started = user["premium_started_at"] if active and user["premium_started_at"] else _utc_timestamp(now)
        expires = _utc_timestamp(base + timedelta(days=days))
        event_id = f"manual-receipt:{request_id}"
        if conn.execute("SELECT 1 FROM payments WHERE provider_event_id=?", (event_id,)).fetchone():
            conn.rollback()
            return {"ok": False, "reason": "already_reviewed", "telegram_id": int(row["telegram_id"])}
        conn.execute(
            "INSERT INTO payments(provider_event_id, telegram_id, amount_minor, currency, status) VALUES(?, ?, ?, 'UZS', 'successful')",
            (event_id, int(row["telegram_id"]), int(row["amount_uzs"])),
        )
        conn.execute(
            "UPDATE users SET is_premium=1, premium_started_at=?, premium_expires_at=?, premium_source='payment' WHERE telegram_id=?",
            (started, expires, int(row["telegram_id"])),
        )
        conn.execute(
            """UPDATE manual_payment_requests SET status='approved', reviewed_by=?, granted_days=?,
               reviewed_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'""",
            (admin_id, days, request_id),
        )
        conn.commit()
        return {
            "ok": True, "status": "approved", "telegram_id": int(row["telegram_id"]),
            "days": days, "months": months, "expires_at": expires,
        }
