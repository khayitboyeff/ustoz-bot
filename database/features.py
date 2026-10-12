from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import date, datetime, timedelta, timezone

from database.db import get_connection, _utc_timestamp, get_completed_lessons, get_user, get_user_profile_stats


def _hash_answer(value: str) -> str:
    normalized = " ".join(value.casefold().strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def kv_get(key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM bot_kv WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def kv_set(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO bot_kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def ensure_referral_code(telegram_id: int) -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT referral_code FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if row is None:
            raise LookupError("Foydalanuvchi topilmadi.")
        if row["referral_code"]:
            return row["referral_code"]
        for _ in range(8):
            code = secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:12]
            try:
                conn.execute("UPDATE users SET referral_code = ? WHERE telegram_id = ?", (code, telegram_id))
                conn.commit()
                return code
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("Referral kod yaratilmadi.")


def apply_referral(invitee_id: int, referrer_code: str) -> bool:
    if not referrer_code or len(referrer_code) > 32:
        return False
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        referrer = conn.execute("SELECT telegram_id FROM users WHERE referral_code = ?", (referrer_code.strip(),)).fetchone()
        if referrer is None:
            return False
        referrer_id = int(referrer["telegram_id"])
        if referrer_id == invitee_id:
            return False
        existing = conn.execute("SELECT invitee_id FROM referrals WHERE invitee_id = ?", (invitee_id,)).fetchone()
        if existing is not None:
            return False
        invitee = conn.execute("SELECT referred_by FROM users WHERE telegram_id = ?", (invitee_id,)).fetchone()
        if invitee is None or invitee["referred_by"]:
            return False
        bonus = int(kv_get("referral_bonus_points", "5") or "5")
        if bonus < 0 or bonus > 100:
            bonus = 0
        conn.execute(
            "INSERT INTO referrals (invitee_id, referrer_id, bonus_granted) VALUES (?, ?, ?)",
            (invitee_id, referrer_id, 1 if bonus else 0),
        )
        conn.execute("UPDATE users SET referred_by = ? WHERE telegram_id = ?", (referrer_id, invitee_id))
        if bonus:
            conn.execute(
                """
                INSERT INTO user_activity (telegram_id, bonus_points) VALUES (?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET bonus_points = user_activity.bonus_points + excluded.bonus_points
                """,
                (referrer_id, bonus),
            )
        conn.commit()
        return True


def count_referrals(telegram_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM referrals WHERE referrer_id = ?", (telegram_id,)).fetchone()
        return int(row["c"])


def list_channels(active_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM required_channels"
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY id"
    with get_connection() as conn:
        return [dict(row) for row in conn.execute(sql).fetchall()]


def add_channel(chat_id: str, username: str | None, invite_link: str | None, title: str | None) -> None:
    chat_id = (chat_id or "").strip()
    if not chat_id or len(chat_id) > 64:
        raise ValueError("Kanal identifikatori yaroqsiz.")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO required_channels (chat_id, username, invite_link, title)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                username = excluded.username,
                invite_link = excluded.invite_link,
                title = excluded.title,
                is_active = 1
            """,
            (chat_id, username, invite_link, title),
        )
        conn.commit()


def remove_channel(channel_pk: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE required_channels SET is_active = 0 WHERE id = ?", (channel_pk,))
        conn.commit()


def subscription_required() -> bool:
    return kv_get("subscription_required", "0") == "1"


def set_subscription_required(enabled: bool) -> None:
    kv_set("subscription_required", "1" if enabled else "0")


def record_activity(telegram_id: int) -> dict:
    today = datetime.now(timezone.utc).date().isoformat()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM user_activity WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO user_activity (telegram_id, streak, last_active_date, total_active_days) VALUES (?, 1, ?, 1)",
                (telegram_id, today),
            )
            conn.commit()
            return {"streak": 1, "new_day": True}
        last = row["last_active_date"]
        if last == today:
            return {"streak": int(row["streak"]), "new_day": False}
        yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        streak = int(row["streak"]) + 1 if last == yesterday else 1
        conn.execute(
            """
            UPDATE user_activity
            SET streak = ?, last_active_date = ?, total_active_days = total_active_days + 1
            WHERE telegram_id = ?
            """,
            (streak, today, telegram_id),
        )
        conn.commit()
        return {"streak": streak, "new_day": True}


def complete_daily_task(telegram_id: int, task_key: str) -> bool:
    if task_key not in {"lesson", "quiz", "ctf"}:
        raise ValueError("Noma’lum kunlik vazifa.")
    day = datetime.now(timezone.utc).date().isoformat()
    with get_connection() as conn:
        before = conn.total_changes
        conn.execute(
            "INSERT OR IGNORE INTO daily_task_completions (telegram_id, task_key, day) VALUES (?, ?, ?)",
            (telegram_id, task_key, day),
        )
        inserted = conn.total_changes > before
        if inserted:
            conn.execute(
                """
                INSERT INTO user_activity (telegram_id, bonus_points) VALUES (?, 2)
                ON CONFLICT(telegram_id) DO UPDATE SET bonus_points = user_activity.bonus_points + 2
                """,
                (telegram_id,),
            )
        conn.commit()
        return inserted


def grant_achievement(telegram_id: int, key: str) -> bool:
    with get_connection() as conn:
        before = conn.total_changes
        conn.execute(
            "INSERT OR IGNORE INTO user_achievements (telegram_id, achievement_key) VALUES (?, ?)",
            (telegram_id, key),
        )
        inserted = conn.total_changes > before
        conn.commit()
        return inserted


def list_achievements(telegram_id: int) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT achievement_key FROM user_achievements WHERE telegram_id = ? ORDER BY granted_at",
            (telegram_id,),
        ).fetchall()
        return [row["achievement_key"] for row in rows]


def get_activity(telegram_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM user_activity WHERE telegram_id = ?", (telegram_id,)).fetchone()
        return dict(row) if row else {"telegram_id": telegram_id, "streak": 0, "bonus_points": 0, "total_active_days": 0}


def increment_ai_usage(telegram_id: int, limit: int) -> bool:
    if type(limit) is not int or limit < 0:
        raise ValueError("AI limiti yaroqsiz.")
    day = datetime.now(timezone.utc).date().isoformat()
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT requests FROM ai_usage WHERE telegram_id = ? AND day = ?",
            (telegram_id, day),
        ).fetchone()
        used = int(row["requests"]) if row else 0
        if used >= limit:
            conn.rollback()
            return False
        conn.execute(
            """
            INSERT INTO ai_usage (telegram_id, day, requests) VALUES (?, ?, 1)
            ON CONFLICT(telegram_id, day) DO UPDATE SET requests = ai_usage.requests + 1
            """,
            (telegram_id, day),
        )
        conn.commit()
        return True


def seed_ctf_challenges(challenges: list[dict]) -> None:
    with get_connection() as conn:
        for item in challenges:
            conn.execute(
                """
                INSERT OR IGNORE INTO ctf_challenges
                (slug, category, difficulty, title, prompt, context_text, hint, answer_hash, points, is_premium)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET is_premium = excluded.is_premium
                """,
                (
                    item["slug"], item["category"], item["difficulty"], item["title"], item["prompt"],
                    item["context_text"], item["hint"], _hash_answer(item["answer"]), item["points"], int(bool(item.get("is_premium", False))),
                ),
            )
        conn.commit()


def list_ctf_challenges() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, slug, category, difficulty, title, prompt, context_text, hint, points, is_premium FROM ctf_challenges ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]


def get_ctf_challenge(challenge_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, slug, category, difficulty, title, prompt, context_text, hint, points, is_premium FROM ctf_challenges WHERE id = ?",
            (challenge_id,),
        ).fetchone()
        return dict(row) if row else None


def submit_ctf_answer(telegram_id: int, challenge_id: int, answer: str) -> dict:
    if type(telegram_id) is not int or telegram_id <= 0:
        raise ValueError("telegram_id yaroqsiz.")
    digest = _hash_answer(answer or "")
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        challenge = conn.execute("SELECT * FROM ctf_challenges WHERE id = ?", (challenge_id,)).fetchone()
        if challenge is None:
            conn.rollback()
            return {"ok": False, "reason": "missing"}
        already = conn.execute(
            "SELECT 1 FROM ctf_solves WHERE telegram_id = ? AND challenge_id = ?",
            (telegram_id, challenge_id),
        ).fetchone()
        correct = digest == challenge["answer_hash"]
        conn.execute(
            "INSERT INTO ctf_attempts (telegram_id, challenge_id, is_correct) VALUES (?, ?, ?)",
            (telegram_id, challenge_id, int(correct)),
        )
        awarded = 0
        if correct and already is None:
            hint_row = conn.execute(
                "SELECT hints_used FROM ctf_hint_usage WHERE telegram_id = ? AND challenge_id = ?",
                (telegram_id, challenge_id),
            ).fetchone()
            hints_used = int(hint_row["hints_used"]) if hint_row else 0
            conn.execute(
                "INSERT INTO ctf_solves (telegram_id, challenge_id, hints_used) VALUES (?, ?, ?)",
                (telegram_id, challenge_id, hints_used),
            )
            awarded = int(challenge["points"])
            conn.execute(
                """
                INSERT INTO user_activity (telegram_id, bonus_points) VALUES (?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET bonus_points = user_activity.bonus_points + excluded.bonus_points
                """,
                (telegram_id, awarded),
            )
        conn.commit()
        return {"ok": correct, "already_solved": already is not None, "awarded": awarded if correct else 0}


def ctf_progress(telegram_id: int) -> dict:
    with get_connection() as conn:
        solved = conn.execute(
            "SELECT COUNT(*) AS c FROM ctf_solves WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        points = conn.execute(
            """
            SELECT COALESCE(SUM(c.points), 0) AS p
            FROM ctf_solves s JOIN ctf_challenges c ON c.id = s.challenge_id
            WHERE s.telegram_id = ?
            """,
            (telegram_id,),
        ).fetchone()
        return {"solved": int(solved["c"]), "points": int(points["p"])}


def use_ctf_hint(telegram_id: int, challenge_id: int) -> dict | None:
    """Return a challenge hint and persist hint usage for progress/analytics."""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        challenge = conn.execute("SELECT id, hint FROM ctf_challenges WHERE id = ?", (challenge_id,)).fetchone()
        if challenge is None:
            conn.rollback()
            return None
        row = conn.execute(
            "SELECT hints_used FROM ctf_hint_usage WHERE telegram_id = ? AND challenge_id = ?",
            (telegram_id, challenge_id),
        ).fetchone()
        used = int(row["hints_used"]) if row else 0
        used += 1
        conn.execute(
            """
            INSERT INTO ctf_hint_usage (telegram_id, challenge_id, hints_used, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(telegram_id, challenge_id) DO UPDATE SET
                hints_used = excluded.hints_used, updated_at = CURRENT_TIMESTAMP
            """,
            (telegram_id, challenge_id, used),
        )
        conn.execute(
            "UPDATE ctf_solves SET hints_used = ? WHERE telegram_id = ? AND challenge_id = ?",
            (used, telegram_id, challenge_id),
        )
        solved = conn.execute("SELECT 1 FROM ctf_solves WHERE telegram_id = ? AND challenge_id = ?", (telegram_id, challenge_id)).fetchone() is not None
        conn.commit()
        return {"hint": challenge["hint"], "already_solved": solved, "hints_used": used}


def get_daily_task_progress(telegram_id: int) -> dict:
    day = datetime.now(timezone.utc).date().isoformat()
    with get_connection() as conn:
        rows = conn.execute("SELECT task_key FROM daily_task_completions WHERE telegram_id = ? AND day = ?", (telegram_id, day)).fetchall()
    done = {str(row["task_key"]) for row in rows}
    return {"day": day, "done": sorted(done), "tasks": {"lesson": "Tugallangan dars", "quiz": "Quiz yakunlash", "ctf": "CTF topshirig‘i"}}


def issue_certificate(telegram_id: int, display_name: str, course_key: str = "cyber-basics") -> dict:
    name = " ".join((display_name or "").split())[:80]
    if not name:
        raise ValueError("Sertifikat uchun ism kiriting.")
    stats = get_user_profile_stats(telegram_id)
    lessons = get_completed_lessons(telegram_id)
    user = stats["user"]
    if user is None:
        raise LookupError("Foydalanuvchi topilmadi.")
    if len(lessons) < 12 or int(user.get("test_score") or 0) < 7:
        raise PermissionError("Sertifikat uchun kamida 12 dars va quizda 7+ ball talab qilinadi.")
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM certificates WHERE telegram_id = ? AND course_key = ?",
            (telegram_id, course_key),
        ).fetchone()
        if existing is not None:
            return dict(existing)
        cert_id = secrets.token_urlsafe(12)
        conn.execute(
            "INSERT INTO certificates (id, telegram_id, course_key, display_name) VALUES (?, ?, ?, ?)",
            (cert_id, telegram_id, course_key, name),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM certificates WHERE id = ?", (cert_id,)).fetchone()
        return dict(row)


def get_certificate(cert_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM certificates WHERE id = ?", (cert_id,)).fetchone()
        return dict(row) if row else None


def upsert_portfolio(telegram_id: int, display_name: str, is_public: bool, contact_email: str | None = None) -> dict:
    name = " ".join((display_name or "").split())[:80]
    if not name:
        raise ValueError("Ko‘rsatish uchun ism kerak.")
    email = (contact_email or "").strip()
    if email and ("@" not in email or len(email) > 120):
        raise ValueError("Email ixtiyoriy, lekin format yaroqsiz.")
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM portfolios WHERE telegram_id = ?", (telegram_id,)).fetchone()
        token = row["public_token"] if row else secrets.token_urlsafe(16)
        conn.execute(
            """
            INSERT INTO portfolios (telegram_id, display_name, is_public, public_token, contact_email, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                display_name = excluded.display_name,
                is_public = excluded.is_public,
                contact_email = excluded.contact_email,
                updated_at = excluded.updated_at
            """,
            (telegram_id, name, int(is_public), token, email or None, _utc_timestamp()),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM portfolios WHERE telegram_id = ?", (telegram_id,)).fetchone())


def add_portfolio_project(telegram_id: int, title: str, description: str, technologies: str) -> None:
    title = " ".join((title or "").split())[:80]
    description = (description or "").strip()[:500]
    technologies = (technologies or "").strip()[:200]
    if not title or not description:
        raise ValueError("Loyiha nomi va tavsifi kerak.")
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM portfolio_projects WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if int(count["c"]) >= 10:
            raise ValueError("Maksimal 10 ta loyiha.")
        conn.execute(
            "INSERT INTO portfolio_projects (telegram_id, title, description, technologies) VALUES (?, ?, ?, ?)",
            (telegram_id, title, description, technologies),
        )
        conn.commit()


def get_portfolio(telegram_id: int, *, public_only: bool = False) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM portfolios WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if row is None:
            return None
        if public_only and not row["is_public"]:
            return None
        projects = conn.execute(
            "SELECT title, description, technologies FROM portfolio_projects WHERE telegram_id = ? ORDER BY id",
            (telegram_id,),
        ).fetchall()
        data = dict(row)
        if public_only:
            data.pop("contact_email", None)
        data["projects"] = [dict(item) for item in projects]
        return data


def get_public_portfolio(token: str) -> dict | None:
    if not token or len(token) > 64:
        return None
    with get_connection() as conn:
        row = conn.execute("SELECT telegram_id FROM portfolios WHERE public_token = ? AND is_public = 1", (token,)).fetchone()
        if row is None:
            return None
    return get_portfolio(int(row["telegram_id"]), public_only=True)


def create_team(owner_id: int, name: str) -> dict:
    name = " ".join((name or "").split())[:40]
    if not name:
        raise ValueError("Jamoa nomi kerak.")
    code = secrets.token_urlsafe(8)
    with get_connection() as conn:
        existing = conn.execute("SELECT team_id FROM team_members WHERE telegram_id = ?", (owner_id,)).fetchone()
        if existing is not None:
            raise ValueError("Siz allaqachon jamoadasiz.")
        cur = conn.execute("INSERT INTO teams (name, owner_id, invite_code) VALUES (?, ?, ?)", (name, owner_id, code))
        team_id = int(cur.lastrowid)
        conn.execute("INSERT INTO team_members (team_id, telegram_id) VALUES (?, ?)", (team_id, owner_id))
        conn.commit()
        return {"id": team_id, "name": name, "invite_code": code}


def join_team(telegram_id: int, invite_code: str) -> dict:
    code = (invite_code or "").strip()
    if not code or len(code) > 64:
        raise ValueError("Taklif kodi yaroqsiz.")
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        team = conn.execute("SELECT * FROM teams WHERE invite_code = ?", (code,)).fetchone()
        if team is None:
            conn.rollback()
            raise LookupError("Jamoa topilmadi.")
        member = conn.execute("SELECT team_id FROM team_members WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if member is not None:
            conn.rollback()
            raise ValueError("Siz allaqachon jamoadasiz.")
        conn.execute("INSERT INTO team_members (team_id, telegram_id) VALUES (?, ?)", (team["id"], telegram_id))
        conn.commit()
        return dict(team)


def leave_team(telegram_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM team_members WHERE telegram_id = ?", (telegram_id,))
        conn.commit()


def get_user_team(telegram_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT t.* FROM teams t
            JOIN team_members m ON m.team_id = t.id
            WHERE m.telegram_id = ?
            """,
            (telegram_id,),
        ).fetchone()
        return dict(row) if row else None


def create_competition(admin_id: int, title: str, hours: int) -> dict:
    title = " ".join((title or "").split())[:80]
    if not title or type(hours) is not int or not 1 <= hours <= 168:
        raise ValueError("Musobaqa nomi va 1–168 soat oralig‘i kerak.")
    start = datetime.now(timezone.utc)
    end = start + timedelta(hours=hours)
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO competitions (title, starts_at, ends_at, status, created_by) VALUES (?, ?, ?, 'active', ?)",
            (title, start.isoformat(), end.isoformat(), admin_id),
        )
        conn.commit()
        return {"id": int(cur.lastrowid), "title": title, "ends_at": end.isoformat()}


def add_competition_score(competition_id: int, telegram_id: int, delta: int) -> dict:
    if type(delta) is not int or delta <= 0 or delta > 1000:
        raise ValueError("Ball yaroqsiz.")
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        comp = conn.execute("SELECT * FROM competitions WHERE id = ?", (competition_id,)).fetchone()
        if comp is None or comp["status"] != "active":
            conn.rollback()
            raise PermissionError("Musobaqa faol emas.")
        ends = datetime.fromisoformat(comp["ends_at"])
        if ends.tzinfo is None:
            ends = ends.replace(tzinfo=timezone.utc)
        if now > ends:
            conn.execute("UPDATE competitions SET status = 'ended' WHERE id = ?", (competition_id,))
            conn.commit()
            raise PermissionError("Musobaqa vaqti tugagan.")
        team = conn.execute("SELECT team_id FROM team_members WHERE telegram_id = ?", (telegram_id,)).fetchone()
        team_id = int(team["team_id"]) if team else None
        conn.execute(
            """
            INSERT INTO competition_scores (competition_id, telegram_id, team_id, score, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(competition_id, telegram_id) DO UPDATE SET
                score = competition_scores.score + excluded.score,
                updated_at = excluded.updated_at
            """,
            (competition_id, telegram_id, team_id, delta, now.isoformat()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT score FROM competition_scores WHERE competition_id = ? AND telegram_id = ?",
            (competition_id, telegram_id),
        ).fetchone()
        return {"score": int(row["score"])}


def competition_leaderboard(competition_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT telegram_id, team_id, score FROM competition_scores
            WHERE competition_id = ?
            ORDER BY score DESC, telegram_id ASC
            """,
            (competition_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def record_payment_event(provider_event_id: str, telegram_id: int, amount_minor: int, currency: str, status: str) -> bool:
    if not provider_event_id or len(provider_event_id) > 128:
        raise ValueError("To‘lov identifikatori yaroqsiz.")
    if status not in {"pending", "successful", "failed", "refunded"}:
        raise ValueError("To‘lov holati yaroqsiz.")
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT status FROM payments WHERE provider_event_id = ?", (provider_event_id,)).fetchone()
        if existing is not None:
            conn.rollback()
            return False
        conn.execute(
            "INSERT INTO payments (provider_event_id, telegram_id, amount_minor, currency, status) VALUES (?, ?, ?, ?, ?)",
            (provider_event_id, telegram_id, amount_minor, currency, status),
        )
        conn.commit()
        return True


def create_broadcast(admin_id: int, body: str) -> int:
    text = (body or "").strip()
    if not text or len(text) > 3500:
        raise ValueError("Xabar 1–3500 belgi bo‘lishi kerak.")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO broadcast_jobs (admin_id, body, status) VALUES (?, ?, 'pending')",
            (admin_id, text),
        )
        conn.commit()
        return int(cur.lastrowid)


def confirm_broadcast(admin_id: int, job_id: int) -> dict | None:
    """Atomically claim a pending broadcast so two callbacks cannot send it twice."""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM broadcast_jobs WHERE id = ? AND admin_id = ?", (job_id, admin_id)).fetchone()
        if row is None or row["status"] != "pending":
            conn.rollback()
            return None
        cur = conn.execute(
            "UPDATE broadcast_jobs SET status = 'confirmed', confirmed_at = ? WHERE id = ? AND admin_id = ? AND status = 'pending'",
            (_utc_timestamp(), job_id, admin_id),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return None
        conn.commit()
        return dict(conn.execute("SELECT * FROM broadcast_jobs WHERE id = ?", (job_id,)).fetchone())


def mark_broadcast_sent(job_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE broadcast_jobs SET status = 'sent' WHERE id = ?", (job_id,))
        conn.commit()


def list_user_ids() -> list[int]:
    with get_connection() as conn:
        return [int(row["telegram_id"]) for row in conn.execute("SELECT telegram_id FROM users").fetchall()]
