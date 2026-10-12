from __future__ import annotations

from datetime import datetime, timedelta, timezone

from database.db import _parse_datetime, _utc_timestamp, get_connection


def grant_available_referral_rewards(referrer_id: int) -> list[dict]:
    """15 referrals unlock 30 days; 30 referrals unlock 90 days total (not 120)."""
    granted: list[dict] = []
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT COUNT(*) AS n FROM referrals WHERE referrer_id=?", (referrer_id,)).fetchone()
        count = int(row["n"] or 0)
        user = conn.execute(
            "SELECT is_premium, premium_started_at, premium_expires_at FROM users WHERE telegram_id=?",
            (referrer_id,),
        ).fetchone()
        if user is None:
            conn.rollback()
            return granted

        claim15 = conn.execute(
            "SELECT 1 FROM referral_reward_claims WHERE telegram_id=? AND milestone=15",
            (referrer_id,),
        ).fetchone()
        claim30 = conn.execute(
            "SELECT 1 FROM referral_reward_claims WHERE telegram_id=? AND milestone=30",
            (referrer_id,),
        ).fetchone()
        if count < 15 or claim30:
            conn.rollback()
            return granted

        old_expiry = _parse_datetime(user["premium_expires_at"])
        active = bool(user["is_premium"]) and old_expiry is not None and old_expiry > now
        base = old_expiry if active else now
        started = user["premium_started_at"] if active and user["premium_started_at"] else _utc_timestamp(now)

        if count >= 30:
            # The 30-invite tier means 90 days total. If 15-invite reward was
            # already paid, add only the remaining 60 days.
            extra_days = 60 if claim15 else 90
            if not claim15:
                conn.execute(
                    "INSERT INTO referral_reward_claims(telegram_id, milestone, granted_days) VALUES (?, 15, 30)",
                    (referrer_id,),
                )
            conn.execute(
                "INSERT INTO referral_reward_claims(telegram_id, milestone, granted_days) VALUES (?, 30, 60)",
                (referrer_id,),
            )
            granted.append({"milestone": 30, "days": extra_days, "total_days": 90})
        elif not claim15:
            extra_days = 30
            conn.execute(
                "INSERT INTO referral_reward_claims(telegram_id, milestone, granted_days) VALUES (?, 15, 30)",
                (referrer_id,),
            )
            granted.append({"milestone": 15, "days": extra_days, "total_days": 30})

        if granted:
            expires = _utc_timestamp(base + timedelta(days=sum(item["days"] for item in granted)))
            conn.execute(
                "UPDATE users SET is_premium=1, premium_started_at=?, premium_expires_at=?, premium_source='referral' WHERE telegram_id=?",
                (started, expires, referrer_id),
            )
        conn.commit()
    return granted
