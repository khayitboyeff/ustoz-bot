from __future__ import annotations

import sqlite3


def _add_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def apply_extended_schema(conn: sqlite3.Connection) -> None:

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_faq_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_faq_active ON custom_faq_questions(is_active, id)")
    _add_column(conn, "users", "referral_code", "TEXT")
    _add_column(conn, "users", "referred_by", "INTEGER")
    _add_column(conn, "users", "display_name", "TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code) WHERE referral_code IS NOT NULL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_kv (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS required_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL UNIQUE,
            username TEXT,
            invite_link TEXT,
            title TEXT,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS referrals (
            invitee_id INTEGER PRIMARY KEY,
            referrer_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            bonus_granted INTEGER NOT NULL DEFAULT 0 CHECK (bonus_granted IN (0, 1)),
            CHECK (invitee_id != referrer_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_activity (
            telegram_id INTEGER PRIMARY KEY,
            streak INTEGER NOT NULL DEFAULT 0,
            last_active_date TEXT,
            total_active_days INTEGER NOT NULL DEFAULT 0,
            bonus_points INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_task_completions (
            telegram_id INTEGER NOT NULL,
            task_key TEXT NOT NULL,
            day TEXT NOT NULL,
            PRIMARY KEY (telegram_id, task_key, day)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_achievements (
            telegram_id INTEGER NOT NULL,
            achievement_key TEXT NOT NULL,
            granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (telegram_id, achievement_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_usage (
            telegram_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            requests INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (telegram_id, day)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ctf_challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            difficulty TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')),
            title TEXT NOT NULL,
            prompt TEXT NOT NULL,
            context_text TEXT NOT NULL,
            hint TEXT NOT NULL,
            answer_hash TEXT NOT NULL,
            points INTEGER NOT NULL CHECK (points > 0),
            is_premium INTEGER NOT NULL DEFAULT 0 CHECK (is_premium IN (0, 1))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ctf_solves (
            telegram_id INTEGER NOT NULL,
            challenge_id INTEGER NOT NULL REFERENCES ctf_challenges(id),
            solved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            hints_used INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (telegram_id, challenge_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ctf_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            challenge_id INTEGER NOT NULL REFERENCES ctf_challenges(id),
            is_correct INTEGER NOT NULL CHECK (is_correct IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ctf_attempts_user ON ctf_attempts(telegram_id, challenge_id, created_at)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ctf_hint_usage (
            telegram_id INTEGER NOT NULL,
            challenge_id INTEGER NOT NULL REFERENCES ctf_challenges(id),
            hints_used INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (telegram_id, challenge_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS certificates (
            id TEXT PRIMARY KEY,
            telegram_id INTEGER NOT NULL,
            course_key TEXT NOT NULL,
            display_name TEXT NOT NULL,
            issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (telegram_id, course_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolios (
            telegram_id INTEGER PRIMARY KEY,
            display_name TEXT NOT NULL,
            is_public INTEGER NOT NULL DEFAULT 0 CHECK (is_public IN (0, 1)),
            public_token TEXT NOT NULL UNIQUE,
            contact_email TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            technologies TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner_id INTEGER NOT NULL,
            invite_code TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS team_members (
            team_id INTEGER NOT NULL REFERENCES teams(id),
            telegram_id INTEGER NOT NULL,
            joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (team_id, telegram_id)
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_team_members_user ON team_members(telegram_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS competitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'ended', 'cancelled')),
            created_by INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS competition_scores (
            competition_id INTEGER NOT NULL REFERENCES competitions(id),
            telegram_id INTEGER NOT NULL,
            team_id INTEGER,
            score INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (competition_id, telegram_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            provider_event_id TEXT PRIMARY KEY,
            telegram_id INTEGER NOT NULL,
            amount_minor INTEGER NOT NULL,
            currency TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'successful', 'failed', 'refunded')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS broadcast_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'sent', 'cancelled')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            confirmed_at TEXT
        )
        """
    )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS manual_payment_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            plan_months INTEGER NOT NULL CHECK (plan_months IN (1, 3, 6, 12)),
            amount_uzs INTEGER NOT NULL CHECK (amount_uzs > 0),
            receipt_file_id TEXT NOT NULL,
            receipt_kind TEXT NOT NULL CHECK (receipt_kind IN ('photo', 'document')),
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
            reviewed_by INTEGER,
            granted_days INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_manual_payment_pending ON manual_payment_requests(status, created_at)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_one_pending_manual_payment_per_user ON manual_payment_requests(telegram_id) WHERE status = 'pending'")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            video_url TEXT,
            video_file_id TEXT,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS referral_reward_claims (
            telegram_id INTEGER NOT NULL,
            milestone INTEGER NOT NULL CHECK (milestone IN (15, 30)),
            granted_days INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (telegram_id, milestone)
        )
    """)
    conn.execute("INSERT OR IGNORE INTO bot_kv (key, value) VALUES ('subscription_required', '0')")
    conn.execute("INSERT OR IGNORE INTO bot_kv (key, value) VALUES ('referral_bonus_points', '5')")
