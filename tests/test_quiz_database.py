from __future__ import annotations

import pytest

import database.db as db
from services.backup_service import create_database_backup, restore_database_backup
import services.payment_service as payments
import services.premium_service as premium
from services.question_bank import generate_verified_questions


def _prepare_db(monkeypatch, tmp_path, questions=None) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "quiz.sqlite3")
    if questions is not None:
        monkeypatch.setattr(db, "generate_verified_questions", lambda: questions)
    db.init_db()


def _complete_run(telegram_id: int, run: dict) -> int:
    score = 0
    for position, question in enumerate(run["questions"]):
        result = db.answer_quiz_question(telegram_id, run["run_id"], position, question["answer"])
        assert result is not None
        score = result["score"]
    return score


def test_quiz_run_has_exactly_ten_unique_questions_and_resumes_after_init(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path)
    db.ensure_user(81001, "first", "First", "User")

    run = db.get_or_create_quiz_run(81001)
    assert run is not None
    assert len(run["questions"]) == 10
    assert len(set(run["question_ids"])) == 10
    assert len({question["semantic_key"] for question in run["questions"]}) == 10

    db.init_db()
    resumed = db.get_or_create_quiz_run(81001)
    assert resumed is not None
    assert resumed["run_id"] == run["run_id"]
    assert resumed["question_ids"] == run["question_ids"]
    assert resumed["resumed"] is True


def test_user_history_is_separate_and_seen_questions_are_not_reused_until_exhausted(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path)
    db.ensure_user(81002, "alpha", "Alpha", "User")
    db.ensure_user(81003, "beta", "Beta", "User")

    first_run = db.get_or_create_quiz_run(81002)
    assert first_run is not None
    first_ids = set(first_run["question_ids"])
    _complete_run(81002, first_run)

    with db.get_connection() as conn:
        beta_history = conn.execute(
            "SELECT COUNT(*) FROM quiz_question_history WHERE telegram_id = ?",
            (81003,),
        ).fetchone()[0]
    assert beta_history == 0

    second_run = db.get_or_create_quiz_run(81002)
    beta_run = db.get_or_create_quiz_run(81003)
    assert second_run is not None and beta_run is not None
    assert first_ids.isdisjoint(second_run["question_ids"])
    assert len(set(beta_run["question_ids"])) == 10
    assert beta_run["reused_questions"] == 0


def test_exhausted_history_reuses_old_questions_without_duplicates_in_one_quiz(monkeypatch, tmp_path) -> None:
    questions = generate_verified_questions()[:10]
    _prepare_db(monkeypatch, tmp_path, questions)
    db.ensure_user(81004, "repeat", "Repeat", "User")

    initial = db.get_or_create_quiz_run(81004)
    assert initial is not None
    _complete_run(81004, initial)
    repeated = db.get_or_create_quiz_run(81004)

    assert repeated is not None
    assert repeated["reused_questions"] == 10
    assert len(repeated["question_ids"]) == 10
    assert len(set(repeated["question_ids"])) == 10


def test_question_bank_with_fewer_than_ten_questions_fails_gracefully(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path, generate_verified_questions()[:9])

    assert db.get_or_create_quiz_run(81005) is None


def test_question_import_batches_and_rejects_normalized_duplicates(monkeypatch, tmp_path) -> None:
    questions = generate_verified_questions()
    python_input = next(question for question in questions if question["semantic_key"] == "python.input")
    _prepare_db(monkeypatch, tmp_path, [python_input])
    duplicate = dict(python_input)
    duplicate["public_id"] = "different-public-id"
    duplicate["semantic_key"] = "different-semantic-key"
    duplicate["question"] = duplicate["question"].replace("Python 3", "Python 4")

    assert db.add_verified_questions([duplicate], batch_size=1) == 0
    assert db.add_verified_questions(questions[1:4], batch_size=2) == 3
    assert db.add_verified_questions(questions[1:4], batch_size=2) == 0


def test_parameterized_facts_generate_typed_unique_questions() -> None:
    questions = generate_verified_questions()

    assert len(questions) >= 49
    assert any("TCP 22-porti" in question["question"] for question in questions)
    assert any(question["question"] == "IPv6 manzillar uchun belgilangan DNS yozuvi qaysi?" for question in questions)
    assert all(question["question_type"] == "single_choice" for question in questions)
    assert len({question["semantic_key"] for question in questions}) == len(questions)
    assert len({question["normalized_question"] for question in questions}) == len(questions)


def test_premium_utc_status_admin_audit_and_expiry(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path)
    db.ensure_user(81007, "premium", "Premium", "User")
    monkeypatch.setattr(premium, "ADMIN_IDS", [70001])
    db.update_user_premium(81007, True, source="admin_test", actor_admin_id=70001)

    status = premium.get_premium_status(81007)
    assert status["is_active"] is True
    assert status["source"] == "admin_test"
    assert status["started_at"].endswith("Z")
    assert status["expires_at"].endswith("Z")
    with db.get_connection() as conn:
        audit = conn.execute("SELECT actor_admin_id, target_user_id, action FROM admin_audit_log").fetchone()
    assert tuple(audit) == (70001, 81007, "premium_granted")

    with db.get_connection() as conn:
        conn.execute(
            "UPDATE users SET premium_expires_at = '2000-01-01T00:00:00Z' WHERE telegram_id = ?",
            (81007,),
        )
        conn.commit()
    expired = premium.get_premium_status(81007)
    assert expired["is_active"] is False
    assert db.get_user(81007)["premium_source"] == "none"


def test_payment_readiness_never_claims_unconfigured_purchase(monkeypatch) -> None:
    monkeypatch.setattr(payments, "PAYMENT_PROVIDER", "none")
    monkeypatch.setattr(payments, "PAYMENT_PROVIDER_TOKEN", "")

    readiness = payments.get_payment_readiness()

    assert readiness.configured is False
    assert "sozlanmagan" in readiness.message


def test_premium_mutation_service_requires_configured_admin(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path)
    db.ensure_user(81012, "target", "Target", "User")
    monkeypatch.setattr(premium, "ADMIN_IDS", [70002])

    with pytest.raises(PermissionError):
        premium.grant_admin_test_premium(81012, actor_admin_id=70003, days=30)


def test_admin_premium_grant_extends_and_revoke_clears_status(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path)
    db.ensure_user(81013, "grant", "Grant", "User")
    monkeypatch.setattr(premium, "ADMIN_IDS", [70004])

    premium.grant_admin_test_premium(81013, actor_admin_id=70004, days=30)
    first_expiry = premium.get_premium_status(81013)["expires_at"]
    premium.grant_admin_test_premium(81013, actor_admin_id=70004, days=30)
    second_expiry = premium.get_premium_status(81013)["expires_at"]
    assert second_expiry > first_expiry

    premium.revoke_premium(81013, actor_admin_id=70004)
    status = premium.get_premium_status(81013)
    assert status["is_active"] is False
    assert status["source"] == "none"
    with db.get_connection() as conn:
        actions = [row["action"] for row in conn.execute("SELECT action FROM admin_audit_log ORDER BY id")]
    assert actions == ["premium_granted", "premium_extended", "premium_revoked"]

def test_free_user_cannot_create_premium_quiz_run(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path)
    db.ensure_user(81008, "free_user", "Free", "User")

    with pytest.raises(PermissionError):
        db.get_or_create_quiz_run(81008, premium_only=True)


def test_active_premium_user_receives_medium_hard_questions(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path)
    db.ensure_user(81009, "premium_user", "Premium", "User")
    db.update_user_premium(81009, True)

    run = db.get_or_create_quiz_run(81009, premium_only=True)
    assert run is not None
    assert all(question["difficulty"] in {"medium", "hard"} for question in run["questions"])


def test_premium_access_is_rechecked_when_answering(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path)
    db.ensure_user(81010, "premium_user", "Premium", "User")
    db.update_user_premium(81010, True)

    run = db.get_or_create_quiz_run(81010, premium_only=True)
    assert run is not None
    db.update_user_premium(81010, False)

    with pytest.raises(PermissionError):
        db.answer_quiz_question(81010, run["run_id"], 0, run["questions"][0]["answer"])

def test_quiz_answers_are_transactional_and_score_is_exact(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path)
    db.ensure_user(81006, "score", "Score", "User")
    run = db.get_or_create_quiz_run(81006)
    assert run is not None

    first = run["questions"][0]
    wrong_index = (first["answer"] + 1) % 4
    result = db.answer_quiz_question(81006, run["run_id"], 0, wrong_index)
    assert result is not None and result["score"] == 0
    assert db.answer_quiz_question(81006, run["run_id"], 0, first["answer"]) is None

    score = 0
    for position, question in enumerate(run["questions"][1:], start=1):
        result = db.answer_quiz_question(81006, run["run_id"], position, question["answer"])
        assert result is not None
        score = result["score"]

    assert score == 9
    assert result["completed"] is True
    user = db.get_user(81006)
    assert user is not None
    assert user["test_score"] == 9
    assert user["quiz_attempts"] == 1
    profile = db.get_user_profile_stats(81006)
    assert profile["quiz_count"] == 1
    assert profile["total_correct"] == 9
    assert profile["total_answers"] == 10
    assert profile["accuracy"] == 90.0
    assert profile["total_score"] == 9
    with db.get_connection() as conn:
        answer_count = conn.execute(
            "SELECT COUNT(*) FROM quiz_run_answers WHERE run_id = ?",
            (run["run_id"],),
        ).fetchone()[0]
    assert answer_count == 10


def test_leaderboard_has_stable_ties_and_current_user_rank(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path)
    for telegram_id, name in ((81020, "First"), (81021, "Second"), (81022, "Third")):
        db.ensure_user(telegram_id, name.lower(), name)
        db.update_quiz_result(telegram_id, 8)

    result = db.get_leaderboard_with_user(81022, limit=2)

    assert [row["telegram_id"] for row in result["top"]] == [81020, 81021]
    assert result["user"]["rank"] == 3


def test_settings_are_persistent_and_notifications_default_off(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path)
    db.ensure_user(81030, "settings", "Settings", "User")

    initial = db.get_user_settings(81030)
    assert initial["language"] == "uz"
    assert initial["notifications_enabled"] == 0
    db.set_notifications_enabled(81030, True)
    db.init_db()

    assert db.get_user_settings(81030)["notifications_enabled"] == 1


def test_admin_dashboard_counts_real_quiz_answers_lessons_and_premium(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path)
    db.ensure_user(81031, "dashboard", "Dashboard", "User")
    run = db.get_or_create_quiz_run(81031)
    assert run is not None
    _complete_run(81031, run)
    db.mark_lesson_completed(81031, 2)
    db.update_user_premium(81031, True, actor_admin_id=70001)

    stats = db.get_admin_stats()

    assert stats["total_users"] == 1
    assert stats["total_quizzes"] == 1
    assert stats["total_answers"] == 10
    assert stats["lessons_completed"] == 1
    assert stats["premium_users"] == 1


def test_lesson_completion_is_persistent_idempotent_and_counted_in_profile(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path)
    db.ensure_user(81011, "learner", "Learner", "User")

    db.mark_lesson_completed(81011, 1)
    db.mark_lesson_completed(81011, 1)
    db.mark_lesson_completed(81011, 12)

    assert db.get_completed_lessons(81011) == {1, 12}
    assert db.get_user_profile_stats(81011)["lessons_completed"] == 2


def test_learning_path_contains_all_required_topics() -> None:
    from handlers.learning import LESSONS

    assert len(LESSONS) == 12
    titles = " ".join(lesson["title"].casefold() for lesson in LESSONS)
    for topic in ("kiberxavfsizlik", "tarmoqlar", "dns", "http", "parol", "phishing", "linux", "python", "veb", "osint", "laboratoriya", "hodisa"):
        assert topic in titles


def test_sqlite_backup_restore_is_validated_atomic_and_keeps_safety_copy(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path)
    db.ensure_user(81040, "before", "Before", "User")
    backup_dir = tmp_path / "backups"

    snapshot = create_database_backup(backup_dir)
    db.ensure_user(81041, "after", "After", "User")
    restored = restore_database_backup(snapshot.name, backup_dir)

    assert db.get_user(81040) is not None
    assert db.get_user(81041) is None
    assert restored["restored"] == db.DB_PATH.resolve()
    assert restored["safety_backup"].is_file()
    assert snapshot.is_file()


def test_restore_rejects_traversal_and_non_database_files(monkeypatch, tmp_path) -> None:
    _prepare_db(monkeypatch, tmp_path)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    (backup_dir / "broken.sqlite3").write_text("not a database", encoding="utf-8")

    with pytest.raises(ValueError):
        restore_database_backup("..\\outside.sqlite3", backup_dir)
    with pytest.raises(ValueError):
        restore_database_backup("broken.sqlite3", backup_dir)
