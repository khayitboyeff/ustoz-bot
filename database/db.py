from __future__ import annotations

import sqlite3
import json
import random
import uuid
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from config import DATABASE_PATH
from database.schema_extra import apply_extended_schema
from services.question_bank import generate_verified_questions, normalize_question_text

BASE_DIR = Path(__file__).resolve().parent.parent
_configured_db_path = Path(DATABASE_PATH).expanduser() if DATABASE_PATH else Path("database/cyberlearn.db")
DB_PATH = (_configured_db_path if _configured_db_path.is_absolute() else BASE_DIR / _configured_db_path).resolve()
MAX_QUIZ_SCORE = 10
MAX_PREMIUM_DAYS = 3650


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _is_premium_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return True
    expires_dt = _parse_datetime(expires_at)
    if expires_dt is None:
        return True
    return expires_dt <= datetime.now(timezone.utc)


def _utc_timestamp(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
                test_score INTEGER DEFAULT 0,
                quiz_attempts INTEGER DEFAULT 0,
                is_premium INTEGER DEFAULT 0,
                premium_started_at TEXT,
                premium_expires_at TEXT,
                premium_source TEXT NOT NULL DEFAULT 'admin_test'
            )
            """
        )
        columns = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "premium_started_at" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN premium_started_at TEXT")
        if "premium_expires_at" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN premium_expires_at TEXT")
        if "premium_source" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN premium_source TEXT NOT NULL DEFAULT 'admin_test'")
        conn.execute(
            "UPDATE users SET is_premium = 0 WHERE is_premium = 1 AND premium_expires_at IS NOT NULL AND datetime(premium_expires_at) <= datetime('now')"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lesson_progress (
                telegram_id INTEGER NOT NULL,
                lesson_id INTEGER NOT NULL,
                completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (telegram_id, lesson_id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lesson_progress_user ON lesson_progress(telegram_id, lesson_id)")
        conn.execute("""CREATE TABLE IF NOT EXISTS premium_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, is_active INTEGER NOT NULL DEFAULT 1, created_by INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS premium_category_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1, created_by INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(category_id) REFERENCES premium_categories(id)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_premium_topics_category ON premium_category_topics(category_id, is_active)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                telegram_id INTEGER PRIMARY KEY,
                language TEXT NOT NULL DEFAULT 'uz',
                notifications_enabled INTEGER NOT NULL DEFAULT 0 CHECK (notifications_enabled IN (0, 1))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_admin_id INTEGER NOT NULL,
                target_user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_log(created_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id TEXT NOT NULL UNIQUE,
                semantic_key TEXT NOT NULL UNIQUE,
                normalized_question TEXT NOT NULL UNIQUE,
                topic TEXT NOT NULL,
                difficulty TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')),
                question_type TEXT NOT NULL,
                question TEXT NOT NULL,
                options_json TEXT NOT NULL,
                correct_index INTEGER NOT NULL CHECK (correct_index BETWEEN 0 AND 3),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quiz_questions_topic ON quiz_questions(topic, difficulty, id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_question_history (
                telegram_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL REFERENCES quiz_questions(id),
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                times_seen INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (telegram_id, question_id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quiz_history_question ON quiz_question_history(question_id, telegram_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_runs (
                run_id TEXT PRIMARY KEY,
                telegram_id INTEGER NOT NULL,
                question_ids_json TEXT NOT NULL,
                current_index INTEGER NOT NULL DEFAULT 0,
                score INTEGER NOT NULL DEFAULT 0,
                reused_questions INTEGER NOT NULL DEFAULT 0,
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quiz_runs_user_active ON quiz_runs(telegram_id, completed, created_at)")
        quiz_run_columns = [row[1] for row in conn.execute("PRAGMA table_info(quiz_runs)").fetchall()]
        if "premium_only" not in quiz_run_columns:
            conn.execute("ALTER TABLE quiz_runs ADD COLUMN premium_only INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_run_answers (
                run_id TEXT NOT NULL REFERENCES quiz_runs(run_id),
                position INTEGER NOT NULL,
                question_id INTEGER NOT NULL REFERENCES quiz_questions(id),
                selected_index INTEGER NOT NULL,
                is_correct INTEGER NOT NULL,
                answered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (run_id, position)
            )
            """
        )
        for question in generate_verified_questions():
            conn.execute(
                """
                INSERT OR IGNORE INTO quiz_questions (
                    public_id, semantic_key, normalized_question, topic, difficulty,
                    question_type, question, options_json, correct_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    question["public_id"],
                    question["semantic_key"],
                    question["normalized_question"],
                    question["topic"],
                    question["difficulty"],
                    question["question_type"],
                    question["question"],
                    json.dumps(question["options"], ensure_ascii=False),
                    question["answer"],
                ),
            )
        apply_extended_schema(conn)
        conn.commit()


def add_verified_questions(questions: Iterable[dict], batch_size: int = 500) -> int:
    if type(batch_size) is not int or not 1 <= batch_size <= 5000:
        raise ValueError("batch_size 1 dan 5000 gacha bo‘lishi kerak.")
    inserted = 0
    batch = []
    with get_connection() as conn:
        for question in questions:
            options = question.get("options")
            answer = question.get("answer")
            required_text = ("public_id", "semantic_key", "topic", "difficulty", "question_type", "question")
            if any(not isinstance(question.get(field), str) or not question[field].strip() for field in required_text):
                raise ValueError("Savol metama’lumotlari to‘liq bo‘lishi kerak.")
            if question["difficulty"] not in {"easy", "medium", "hard"}:
                raise ValueError("Savol qiyinlik darajasi yaroqsiz.")
            if not isinstance(options, list) or len(options) != 4 or any(not isinstance(option, str) or not option.strip() for option in options):
                raise ValueError("Har bir savolda to‘rtta matnli variant bo‘lishi kerak.")
            if type(answer) is not int or not 0 <= answer < len(options):
                raise ValueError("To‘g‘ri javob indeksi yaroqsiz.")
            if len(set(option.casefold().strip() for option in options)) != len(options):
                raise ValueError("Javob variantlari o‘zaro takrorlanmasligi kerak.")
            normalized = normalize_question_text(question["question"])
            batch.append((
                question["public_id"], question["semantic_key"], normalized,
                question["topic"], question["difficulty"], question["question_type"],
                question["question"], json.dumps(options, ensure_ascii=False), answer,
            ))
            if len(batch) >= batch_size:
                before = conn.total_changes
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO quiz_questions (
                        public_id, semantic_key, normalized_question, topic, difficulty,
                        question_type, question, options_json, correct_index
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )
                inserted += conn.total_changes - before
                batch.clear()
        if batch:
            before = conn.total_changes
            conn.executemany(
                """
                INSERT OR IGNORE INTO quiz_questions (
                    public_id, semantic_key, normalized_question, topic, difficulty,
                    question_type, question, options_json, correct_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
            inserted += conn.total_changes - before
        conn.commit()
    return inserted


def ensure_user(telegram_id: int, username: str | None = None, first_name: str | None = None, last_name: str | None = None) -> None:
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO users (telegram_id, username, first_name, last_name, created_at, last_seen_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (telegram_id, username, first_name, last_name),
            )
        else:
            conn.execute(
                """
                UPDATE users
                SET username = ?, first_name = ?, last_name = ?, last_seen_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
                """,
                (username, first_name, last_name, telegram_id),
            )
        conn.commit()


def _normalize_user_row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    user = dict(row)
    user["is_premium"] = 1 if int(user.get("is_premium", 0)) == 1 and not _is_premium_expired(user.get("premium_expires_at")) else 0
    return user


def _deactivate_expired_premium(conn: sqlite3.Connection, row: sqlite3.Row | None) -> sqlite3.Row | None:
    if row is None:
        return None
    if int(row["is_premium"] or 0) == 1 and _is_premium_expired(row["premium_expires_at"]):
        conn.execute(
            "UPDATE users SET is_premium = 0, premium_source = 'none' WHERE telegram_id = ?",
            (row["telegram_id"],),
        )
        conn.commit()
        return conn.execute("SELECT * FROM users WHERE telegram_id = ?", (row["telegram_id"],)).fetchone()
    return row


def get_user(telegram_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        row = _deactivate_expired_premium(conn, row)
        return _normalize_user_row(row)


def get_all_users() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [_normalize_user_row(row) for row in rows if _normalize_user_row(row) is not None]


def get_admin_stats() -> dict:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()
        active_premium = conn.execute(
            "SELECT COUNT(*) as count FROM users WHERE is_premium = 1 AND premium_expires_at IS NOT NULL AND datetime(premium_expires_at) > datetime('now')"
        ).fetchone()
        avg_score = conn.execute("SELECT COALESCE(AVG(test_score), 0) as avg FROM users").fetchone()
        quiz_stats = conn.execute(
            "SELECT COALESCE(SUM(quiz_attempts), 0) AS quizzes FROM users"
        ).fetchone()
        quiz_score_stats = conn.execute(
            "SELECT COALESCE(SUM(score), 0) AS total_score FROM quiz_runs WHERE completed = 1"
        ).fetchone()
        answer_stats = conn.execute(
            "SELECT COUNT(*) AS answers FROM quiz_run_answers"
        ).fetchone()
        lesson_stats = conn.execute("SELECT COUNT(*) AS completed FROM lesson_progress").fetchone()
        active_lessons = conn.execute("SELECT COUNT(*) AS count FROM custom_lessons WHERE is_active=1").fetchone()
        certificates = conn.execute("SELECT COUNT(*) AS count FROM certificates").fetchone()
        successful_payments = conn.execute(
            "SELECT COUNT(*) AS count FROM payments WHERE status='successful'"
        ).fetchone()
        stars_payments = conn.execute(
            "SELECT COUNT(*) AS count, COALESCE(SUM(amount_minor), 0) AS total FROM payments WHERE status='successful' AND currency='XTR'"
        ).fetchone()
        pending_manual_payments = conn.execute(
            "SELECT COUNT(*) AS count FROM manual_payment_requests WHERE status='pending'"
        ).fetchone()
        return {
            "total_users": int(total["count"] or 0),
            "premium_users": int(active_premium["count"] or 0),
            "avg_test_score": float(avg_score["avg"] or 0),
            "total_quizzes": int(quiz_stats["quizzes"] or 0),
            "recorded_quiz_score": int(quiz_score_stats["total_score"] or 0),
            "total_answers": int(answer_stats["answers"] or 0),
            "lessons_completed": int(lesson_stats["completed"] or 0),
            "active_custom_lessons": int(active_lessons["count"] or 0),
            "certificates_issued": int(certificates["count"] or 0),
            "successful_payments": int(successful_payments["count"] or 0),
            "stars_payments_count": int(stars_payments["count"] or 0),
            "stars_received": int(stars_payments["total"] or 0),
            "pending_manual_payments": int(pending_manual_payments["count"] or 0),
        }


def record_admin_action(actor_admin_id: int, action: str, target_user_id: int = 0, metadata: dict | None = None) -> None:
    if type(actor_admin_id) is not int or actor_admin_id <= 0:
        raise ValueError("Admin ID musbat butun son bo‘lishi kerak.")
    if not action or len(action) > 64:
        raise ValueError("Audit action yaroqsiz.")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO admin_audit_log (actor_admin_id, target_user_id, action, metadata_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (actor_admin_id, target_user_id, action, json.dumps(metadata or {}, sort_keys=True), _utc_timestamp()),
        )
        conn.commit()


def get_leaderboard(limit: int = 10) -> list[dict]:
    safe_limit = max(1, min(int(limit), 100))
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT telegram_id, username, first_name, test_score, quiz_attempts
            FROM users
            WHERE test_score > 0
            ORDER BY test_score DESC, quiz_attempts DESC, telegram_id ASC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_leaderboard_with_user(telegram_id: int, limit: int = 10) -> dict:
    safe_limit = max(1, min(int(limit), 100))
    with get_connection() as conn:
        top_rows = conn.execute(
            """
            SELECT telegram_id, username, first_name, test_score, quiz_attempts
            FROM users WHERE test_score > 0
            ORDER BY test_score DESC, quiz_attempts DESC, telegram_id ASC LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        mine = conn.execute(
            """
            SELECT u.telegram_id, u.username, u.first_name, u.test_score, u.quiz_attempts,
                (SELECT COUNT(*) + 1 FROM users other
                 WHERE other.test_score > u.test_score
                    OR (other.test_score = u.test_score AND other.quiz_attempts > u.quiz_attempts)
                    OR (other.test_score = u.test_score AND other.quiz_attempts = u.quiz_attempts AND other.telegram_id < u.telegram_id)
                ) AS rank
            FROM users u WHERE u.telegram_id = ? AND u.test_score > 0
            """,
            (telegram_id,),
        ).fetchone()
        return {"top": [dict(row) for row in top_rows], "user": dict(mine) if mine else None}


def get_user_profile_stats(telegram_id: int) -> dict:
    with get_connection() as conn:
        user_row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        user_row = _deactivate_expired_premium(conn, user_row)
        if user_row is None:
            return {"user": None, "quiz_count": 0, "total_correct": 0, "total_answers": 0, "accuracy": 0.0, "total_score": 0, "lessons_completed": 0}
        quiz_row = conn.execute(
            "SELECT COUNT(*) AS count, COALESCE(SUM(score), 0) AS total_score FROM quiz_runs WHERE telegram_id = ? AND completed = 1",
            (telegram_id,),
        ).fetchone()
        answer_row = conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(is_correct), 0) AS correct FROM quiz_run_answers a JOIN quiz_runs r ON r.run_id = a.run_id WHERE r.telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        lesson_row = conn.execute(
            "SELECT COUNT(*) AS count FROM lesson_progress WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        total_answers = int(answer_row["total"] or 0)
        total_correct = int(answer_row["correct"] or 0)
        return {
            "user": _normalize_user_row(user_row),
            "quiz_count": max(int(quiz_row["count"] or 0), int(user_row["quiz_attempts"] or 0)),
            "total_correct": total_correct,
            "total_answers": total_answers,
            "accuracy": (total_correct * 100.0 / total_answers) if total_answers else 0.0,
            "total_score": int(quiz_row["total_score"] or 0),
            "lessons_completed": int(lesson_row["count"] or 0),
        }


def mark_lesson_completed(telegram_id: int, lesson_id: int) -> None:
    if type(telegram_id) is not int or telegram_id <= 0 or type(lesson_id) is not int or lesson_id <= 0:
        raise ValueError("Foydalanuvchi va dars ID musbat butun son bo‘lishi kerak.")
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO lesson_progress (telegram_id, lesson_id) VALUES (?, ?)",
            (telegram_id, lesson_id),
        )
        conn.commit()


def get_completed_lessons(telegram_id: int) -> set[int]:
    with get_connection() as conn:
        rows = conn.execute("SELECT lesson_id FROM lesson_progress WHERE telegram_id = ?", (telegram_id,)).fetchall()
        return {int(row["lesson_id"]) for row in rows}


def get_user_settings(telegram_id: int) -> dict:
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO user_settings (telegram_id) VALUES (?)", (telegram_id,))
        conn.commit()
        row = conn.execute("SELECT * FROM user_settings WHERE telegram_id = ?", (telegram_id,)).fetchone()
        return dict(row)


def set_user_language(telegram_id: int, language: str) -> None:
    if language not in {"uz", "ru", "en"}:
        raise ValueError("Til uz, ru yoki en bo‘lishi kerak.")
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO user_settings (telegram_id) VALUES (?)", (telegram_id,))
        conn.execute("UPDATE user_settings SET language = ? WHERE telegram_id = ?", (language, telegram_id))
        conn.commit()


def set_notifications_enabled(telegram_id: int, enabled: bool) -> None:
    if type(enabled) is not bool:
        raise ValueError("enabled boolean bo‘lishi kerak.")
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO user_settings (telegram_id) VALUES (?)", (telegram_id,))
        conn.execute(
            "UPDATE user_settings SET notifications_enabled = ? WHERE telegram_id = ?",
            (int(enabled), telegram_id),
        )
        conn.commit()


def update_user_last_seen(telegram_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET last_seen_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
            (telegram_id,),
        )
        conn.commit()


def update_user_premium(
    telegram_id: int,
    is_premium: bool,
    expires_at: str | None = None,
    started_at: str | None = None,
    *,
    source: str = "admin_test",
    actor_admin_id: int | None = None,
) -> None:
    if type(telegram_id) is not int or telegram_id <= 0:
        raise ValueError("telegram_id musbat butun son bo‘lishi kerak.")
    if type(is_premium) is not bool:
        raise ValueError("is_premium boolean bo‘lishi kerak.")
    if source not in {"admin_test", "payment"}:
        raise ValueError("Premium manbasi noto‘g‘ri.")
    if actor_admin_id is not None and (type(actor_admin_id) is not int or actor_admin_id <= 0):
        raise ValueError("Admin ID musbat butun son bo‘lishi kerak.")
    with get_connection() as conn:
        current = conn.execute(
            "SELECT is_premium, premium_started_at, premium_expires_at FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if current is None:
            raise LookupError("Foydalanuvchi topilmadi.")
        now = datetime.now(timezone.utc)
        if is_premium:
            old_expiry = _parse_datetime(current["premium_expires_at"])
            if expires_at is None:
                extension_base = old_expiry if current["is_premium"] and old_expiry and old_expiry > now else now
                expires_at = _utc_timestamp(extension_base + timedelta(days=30))
            if started_at is None:
                started_at = current["premium_started_at"] if current["is_premium"] and current["premium_started_at"] else _utc_timestamp(now)
            expires_dt = _parse_datetime(expires_at)
            started_dt = _parse_datetime(started_at)
            if expires_dt is None or started_dt is None:
                raise ValueError("Premium sanalari yaroqsiz.")
            if expires_dt <= now or expires_dt > now + timedelta(days=MAX_PREMIUM_DAYS):
                raise ValueError(f"Premium muddati 1 dan {MAX_PREMIUM_DAYS} kungacha bo‘lishi kerak.")
            if started_dt > now or started_dt >= expires_dt:
                raise ValueError("Premium boshlanish sanasi noto‘g‘ri.")
            conn.execute(
                "UPDATE users SET is_premium = 1, premium_started_at = ?, premium_expires_at = ?, premium_source = ? WHERE telegram_id = ?",
                (_utc_timestamp(started_dt), _utc_timestamp(expires_dt), source, telegram_id),
            )
            action = "premium_extended" if current["is_premium"] and old_expiry and old_expiry > now else "premium_granted"
            metadata = {"source": source, "expires_at": _utc_timestamp(expires_dt)}
        else:
            conn.execute(
                "UPDATE users SET is_premium = 0, premium_started_at = NULL, premium_expires_at = NULL, premium_source = 'none' WHERE telegram_id = ?",
                (telegram_id,),
            )
            action = "premium_revoked"
            metadata = {}
        if actor_admin_id is not None:
            conn.execute(
                "INSERT INTO admin_audit_log (actor_admin_id, target_user_id, action, metadata_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (actor_admin_id, telegram_id, action, json.dumps(metadata, sort_keys=True), _utc_timestamp()),
            )
        conn.commit()


def update_quiz_result(telegram_id: int, score: int) -> None:
    if type(telegram_id) is not int or telegram_id <= 0:
        raise ValueError("telegram_id musbat butun son bo‘lishi kerak.")
    if type(score) is not int or not 0 <= score <= MAX_QUIZ_SCORE:
        raise ValueError(f"Test bali 0 dan {MAX_QUIZ_SCORE} gacha bo‘lishi kerak.")
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if existing is None:
            return
        new_score = max(score, int(existing["test_score"]))
        new_attempts = int(existing["quiz_attempts"]) + 1
        conn.execute(
            "UPDATE users SET test_score = ?, quiz_attempts = ? WHERE telegram_id = ?",
            (new_score, new_attempts, telegram_id),
        )
        conn.commit()


def _quiz_question_from_row(row: sqlite3.Row) -> dict:
    question = dict(row)
    question["options"] = json.loads(question.pop("options_json"))
    question["answer"] = question.pop("correct_index")
    return question


def _load_quiz_questions(conn: sqlite3.Connection, question_ids: list[int]) -> list[dict]:
    if not question_ids:
        return []
    placeholders = ",".join("?" for _ in question_ids)
    rows = conn.execute(
        f"SELECT * FROM quiz_questions WHERE id IN ({placeholders})",
        question_ids,
    ).fetchall()
    by_id = {int(row["id"]): _quiz_question_from_row(row) for row in rows}
    return [by_id[question_id] for question_id in question_ids if question_id in by_id]


def get_or_create_quiz_run(
    telegram_id: int,
    question_count: int = MAX_QUIZ_SCORE,
    *,
    premium_only: bool = False,
) -> dict | None:
    if type(telegram_id) is not int or telegram_id <= 0:
        raise ValueError("telegram_id musbat butun son bo‘lishi kerak.")
    if question_count != MAX_QUIZ_SCORE:
        raise ValueError(f"Har bir testda aynan {MAX_QUIZ_SCORE} ta savol bo‘lishi kerak.")

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if premium_only:
            user_row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user_row is None or not _normalize_user_row(user_row)["is_premium"]:
                if user_row is not None and int(user_row["is_premium"] or 0) == 1:
                    conn.execute(
                        "UPDATE users SET is_premium = 0, premium_source = 'none' WHERE telegram_id = ?",
                        (telegram_id,),
                    )
                    conn.commit()
                raise PermissionError("Faol Premium huquqi talab qilinadi.")
        active = conn.execute(
            "SELECT * FROM quiz_runs WHERE telegram_id = ? AND completed = 0 AND premium_only = ? ORDER BY created_at DESC LIMIT 1",
            (telegram_id, int(premium_only)),
        ).fetchone()
        if active is not None:
            run = dict(active)
            run["question_ids"] = json.loads(run.pop("question_ids_json"))
            run["questions"] = _load_quiz_questions(conn, run["question_ids"])
            run["resumed"] = True
            return run

        question_filter = "difficulty IN ('medium', 'hard')" if premium_only else "1 = 1"
        bounds = conn.execute(
            f"SELECT MIN(id) AS first_id, MAX(id) AS last_id FROM quiz_questions WHERE {question_filter}"
        ).fetchone()
        if bounds["first_id"] is None:
            return None
        first_id, last_id = int(bounds["first_id"]), int(bounds["last_id"])
        pivot = random.randint(first_id, last_id)
        unseen_after = conn.execute(
            f"""
            SELECT q.id FROM quiz_questions q
            WHERE q.id >= ? AND {question_filter} AND NOT EXISTS (
                SELECT 1 FROM quiz_question_history h
                WHERE h.telegram_id = ? AND h.question_id = q.id
            )
            ORDER BY q.id LIMIT ?
            """,
            (pivot, telegram_id, question_count),
        ).fetchall()
        selected_ids = [int(row["id"]) for row in unseen_after]
        if len(selected_ids) < question_count:
            unseen_before = conn.execute(
                f"""
                SELECT q.id FROM quiz_questions q
                WHERE q.id < ? AND {question_filter} AND NOT EXISTS (
                    SELECT 1 FROM quiz_question_history h
                    WHERE h.telegram_id = ? AND h.question_id = q.id
                )
                ORDER BY q.id LIMIT ?
                """,
                (pivot, telegram_id, question_count - len(selected_ids)),
            ).fetchall()
            selected_ids.extend(int(row["id"]) for row in unseen_before)

        unseen_count = len(selected_ids)
        reused_count = 0
        if unseen_count < question_count:
            reused_count = question_count - unseen_count
            reused_after = conn.execute(
                f"""
                SELECT q.id FROM quiz_questions q
                WHERE q.id >= ? AND {question_filter} AND EXISTS (
                    SELECT 1 FROM quiz_question_history h
                    WHERE h.telegram_id = ? AND h.question_id = q.id
                )
                ORDER BY q.id LIMIT ?
                """,
                (pivot, telegram_id, reused_count),
            ).fetchall()
            selected_ids.extend(int(row["id"]) for row in reused_after)
            if len(selected_ids) < question_count:
                reused_before = conn.execute(
                    f"""
                    SELECT q.id FROM quiz_questions q
                    WHERE q.id < ? AND {question_filter} AND EXISTS (
                        SELECT 1 FROM quiz_question_history h
                        WHERE h.telegram_id = ? AND h.question_id = q.id
                    )
                    ORDER BY q.id LIMIT ?
                    """,
                    (pivot, telegram_id, question_count - len(selected_ids)),
                ).fetchall()
                selected_ids.extend(int(row["id"]) for row in reused_before)

        if len(selected_ids) < question_count:
            return None
        random.shuffle(selected_ids)
        run_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO quiz_runs (run_id, telegram_id, question_ids_json, reused_questions, premium_only) VALUES (?, ?, ?, ?, ?)",
            (run_id, telegram_id, json.dumps(selected_ids), reused_count, int(premium_only)),
        )
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.executemany(
            """
            INSERT INTO quiz_question_history (telegram_id, question_id, first_seen_at, last_seen_at, times_seen)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(telegram_id, question_id) DO UPDATE SET
                last_seen_at = excluded.last_seen_at,
                times_seen = quiz_question_history.times_seen + 1
            """,
            [(telegram_id, question_id, now, now) for question_id in selected_ids],
        )
        run = conn.execute("SELECT * FROM quiz_runs WHERE run_id = ?", (run_id,)).fetchone()
        result = dict(run)
        result["question_ids"] = selected_ids
        result["questions"] = _load_quiz_questions(conn, selected_ids)
        result["resumed"] = False
        conn.commit()
        return result


def answer_quiz_question(telegram_id: int, run_id: str, position: int, selected_index: int) -> dict | None:
    if type(telegram_id) is not int or telegram_id <= 0:
        raise ValueError("telegram_id musbat butun son bo‘lishi kerak.")
    if type(position) is not int or not 0 <= position < MAX_QUIZ_SCORE:
        return None
    if type(selected_index) is not int or not 0 <= selected_index < 4:
        return None

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        run_row = conn.execute(
            "SELECT * FROM quiz_runs WHERE run_id = ? AND telegram_id = ? AND completed = 0",
            (run_id, telegram_id),
        ).fetchone()
        if run_row is None or int(run_row["current_index"]) != position:
            return None
        if run_row["premium_only"]:
            user_row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user_row is None or not _normalize_user_row(user_row)["is_premium"]:
                if user_row is not None and int(user_row["is_premium"] or 0) == 1:
                    conn.execute(
                        "UPDATE users SET is_premium = 0, premium_source = 'none' WHERE telegram_id = ?",
                        (telegram_id,),
                    )
                    conn.commit()
                raise PermissionError("Faol Premium huquqi talab qilinadi.")
        question_ids = json.loads(run_row["question_ids_json"])
        if len(question_ids) != MAX_QUIZ_SCORE:
            return None
        question_row = conn.execute("SELECT * FROM quiz_questions WHERE id = ?", (question_ids[position],)).fetchone()
        if question_row is None:
            return None
        question = _quiz_question_from_row(question_row)
        is_correct = selected_index == question["answer"]
        score = int(run_row["score"]) + int(is_correct)
        next_index = position + 1
        completed = next_index == MAX_QUIZ_SCORE
        conn.execute(
            "INSERT INTO quiz_run_answers (run_id, position, question_id, selected_index, is_correct) VALUES (?, ?, ?, ?, ?)",
            (run_id, position, question["id"], selected_index, int(is_correct)),
        )
        conn.execute(
            "UPDATE quiz_runs SET current_index = ?, score = ?, completed = ?, completed_at = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END WHERE run_id = ?",
            (next_index, score, int(completed), int(completed), run_id),
        )
        if completed:
            user_row = conn.execute("SELECT test_score, quiz_attempts FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if user_row is None:
                conn.execute("INSERT INTO users (telegram_id, test_score, quiz_attempts) VALUES (?, ?, 1)", (telegram_id, score))
            else:
                conn.execute(
                    "UPDATE users SET test_score = ?, quiz_attempts = ? WHERE telegram_id = ?",
                    (max(score, int(user_row["test_score"])), int(user_row["quiz_attempts"]) + 1, telegram_id),
                )
        next_question = None
        if not completed:
            next_question = _load_quiz_questions(conn, [int(question_ids[next_index])])[0]
        conn.commit()
        return {
            "question": question,
            "is_correct": is_correct,
            "score": score,
            "position": position,
            "next_index": next_index,
            "completed": completed,
            "next_question": next_question,
        }


# Community features: required-channel membership, referrals and learning streaks.
def get_active_required_channels() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, chat_id, username, invite_link, title FROM required_channels WHERE is_active = 1 ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]

def add_required_channel(chat_id: str, username: str | None = None, invite_link: str | None = None, title: str | None = None) -> None:
    chat_id = str(chat_id).strip()
    if not chat_id or len(chat_id) > 128:
        raise ValueError("Kanal ID yoki username noto‘g‘ri.")
    if invite_link and not invite_link.startswith(("https://t.me/", "https://telegram.me/")):
        raise ValueError("Taklif havolasi Telegram HTTPS havolasi bo‘lishi kerak.")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO required_channels (chat_id, username, invite_link, title, is_active) VALUES (?, ?, ?, ?, 1) "
            "ON CONFLICT(chat_id) DO UPDATE SET username=excluded.username, invite_link=excluded.invite_link, title=excluded.title, is_active=1",
            (chat_id, username, invite_link, title),
        )
        conn.commit()

def remove_required_channel(identifier: str) -> bool:
    value = str(identifier).strip()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM required_channels WHERE chat_id = ? OR username = ?", (value, value.lstrip('@')))
        conn.commit()
        return cur.rowcount > 0

def set_subscription_required(enabled: bool) -> None:
    if type(enabled) is not bool:
        raise ValueError("enabled boolean bo‘lishi kerak.")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO bot_kv(key, value) VALUES('subscription_required', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("1" if enabled else "0",),
        )
        conn.commit()

def is_subscription_required() -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM bot_kv WHERE key='subscription_required'").fetchone()
        return bool(row and row["value"] == "1")

def _make_referral_code() -> str:
    import secrets
    return secrets.token_urlsafe(8).replace('-', '').replace('_', '')[:10].upper()

def ensure_referral_code(telegram_id: int) -> str:
    if type(telegram_id) is not int or telegram_id <= 0:
        raise ValueError("Telegram ID yaroqsiz.")
    with get_connection() as conn:
        row = conn.execute("SELECT referral_code FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        if row is None:
            raise ValueError("Avval foydalanuvchini ro‘yxatdan o‘tkazing.")
        if row["referral_code"]:
            return str(row["referral_code"])
        for _ in range(5):
            code = _make_referral_code()
            try:
                conn.execute("UPDATE users SET referral_code=? WHERE telegram_id=? AND referral_code IS NULL", (code, telegram_id))
                conn.commit()
                return str(conn.execute("SELECT referral_code FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()["referral_code"])
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("Referral kodini yaratib bo‘lmadi.")

def register_referral(invitee_id: int, referral_code: str) -> bool:
    code = str(referral_code).strip().upper()
    if not code or len(code) > 32 or type(invitee_id) is not int or invitee_id <= 0:
        return False
    with get_connection() as conn:
        referrer = conn.execute("SELECT telegram_id FROM users WHERE referral_code=?", (code,)).fetchone()
        if referrer is None or int(referrer["telegram_id"]) == invitee_id:
            return False
        # The invitee can only be attributed once. No unverified bonus is granted here.
        cur = conn.execute(
            "INSERT OR IGNORE INTO referrals(invitee_id, referrer_id, bonus_granted) VALUES(?, ?, 0)",
            (invitee_id, int(referrer["telegram_id"])),
        )
        if cur.rowcount:
            conn.execute("UPDATE users SET referred_by=? WHERE telegram_id=? AND referred_by IS NULL", (int(referrer["telegram_id"]), invitee_id))
            conn.commit()
            return True
        conn.rollback()
        return False

def get_referral_stats(telegram_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM referrals WHERE referrer_id=?",
            (telegram_id,),
        ).fetchone()
        rewards = conn.execute(
            "SELECT COUNT(*) AS milestones, COALESCE(SUM(granted_days), 0) AS days FROM referral_reward_claims WHERE telegram_id=?",
            (telegram_id,),
        ).fetchone()
        return {
            "invited": int(row["total"] or 0),
            "bonuses_granted": int(rewards["milestones"] or 0),
            "reward_days": int(rewards["days"] or 0),
        }

def record_user_activity(telegram_id: int, day: str | None = None) -> dict:
    from datetime import date, timedelta
    active_day = day or datetime.now(timezone.utc).date().isoformat()
    try:
        current = date.fromisoformat(active_day)
    except ValueError as exc:
        raise ValueError("Sana YYYY-MM-DD formatida bo‘lishi kerak.") from exc
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO user_activity(telegram_id) VALUES(?)", (telegram_id,))
        row = conn.execute("SELECT streak, last_active_date, total_active_days FROM user_activity WHERE telegram_id=?", (telegram_id,)).fetchone()
        last = row["last_active_date"]
        if last == active_day:
            conn.commit()
            return {"streak": int(row["streak"]), "total_active_days": int(row["total_active_days"]), "already_counted": True}
        if last:
            try:
                previous = date.fromisoformat(last)
            except ValueError:
                previous = None
        else:
            previous = None
        streak = int(row["streak"] or 0) + 1 if previous and current - previous == timedelta(days=1) else 1
        total = int(row["total_active_days"] or 0) + 1
        conn.execute("UPDATE user_activity SET streak=?, last_active_date=?, total_active_days=? WHERE telegram_id=?", (streak, active_day, total, telegram_id))
        conn.commit()
        return {"streak": streak, "total_active_days": total, "already_counted": False}

def get_user_activity(telegram_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT streak, last_active_date, total_active_days, bonus_points FROM user_activity WHERE telegram_id=?", (telegram_id,)).fetchone()
        return dict(row) if row else {"streak": 0, "last_active_date": None, "total_active_days": 0, "bonus_points": 0}
