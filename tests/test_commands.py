from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from telegram.ext import Application, CommandHandler, MessageHandler

import handlers.admin as admin
import handlers.learning as learning
import handlers.premium as premium
import handlers.quiz as quiz
import handlers.start as start
import handlers.tools as tools
from bot import BOT_COMMANDS, set_bot_commands
from handlers import (
    register_advanced_handlers,
    register_admin_handlers,
    register_learning_handlers,
    register_premium_handlers,
    register_quiz_handlers,
    register_start_handlers,
    register_tools_handlers,
)
from handlers.start import settings_command
from handlers.community import register_community_handlers


def _application() -> Application:
    return Application.builder().token("123456:TEST_TOKEN").build()


def _message_update(user_id: int = 44):
    message = SimpleNamespace(reply_text=AsyncMock())
    user = SimpleNamespace(id=user_id, username="testuser", first_name="Test", last_name="User")
    return SimpleNamespace(
        callback_query=None,
        message=message,
        effective_message=message,
        effective_user=user,
    ), message


def test_all_requested_commands_are_registered() -> None:
    application = _application()
    for register in (
        register_start_handlers,
        register_learning_handlers,
        register_quiz_handlers,
        register_tools_handlers,
        register_premium_handlers,
        register_admin_handlers,
        register_advanced_handlers,
        register_community_handlers,
    ):
        register(application)

    registered = {
        command
        for group_handlers in application.handlers.values()
        for handler in group_handlers
        if isinstance(handler, CommandHandler)
        for command in handler.commands
    }
    expected = {
        "start", "help", "lessons",
        "quiz", "premium_quiz", "profile", "ip", "dns", "osint", "premium", "premium_status",
        "stats", "leaderboard", "settings", "phishing", "ctf",
        "ctf_progress", "certificate", "cancel", "referral", "streak", "daily", "broadcast", "admin",
    }
    assert expected <= registered
    assert {command.command for command in BOT_COMMANDS} == expected
    assert not ({"ai", "ai_reset", "ai_lang", "lesson_add", "lesson_video", "admin_lessons"} & registered)
    callback_patterns = [
        handler.pattern.pattern
        for group_handlers in application.handlers.values()
        for handler in group_handlers
        if hasattr(handler, "pattern") and handler.pattern is not None
    ]
    assert "^premium:quiz$" in callback_patterns


def test_lookup_message_handlers_precede_generic_text_router() -> None:
    application = _application()
    register_tools_handlers(application)
    register_start_handlers(application)

    message_handlers = [
        handler
        for handler in application.handlers[0]
        if isinstance(handler, MessageHandler)
    ]
    assert message_handlers[0].callback is tools.handle_ip_lookup_message
    assert message_handlers[1].callback is tools.handle_dns_lookup_message
    assert message_handlers[-1].callback is start.handle_unknown_text


def test_stats_requires_admin(monkeypatch) -> None:
    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=44),
        effective_message=SimpleNamespace(reply_text=reply_text),
    )
    monkeypatch.setattr(admin, "ADMIN_IDS", [99])
    monkeypatch.setattr(admin, "get_admin_stats", lambda: (_ for _ in ()).throw(AssertionError("called")))

    asyncio.run(admin.stats_command(update, SimpleNamespace()))

    reply_text.assert_awaited_once()
    assert "admin huquqi" in reply_text.await_args.args[0]


def test_stats_returns_database_stats_to_admin(monkeypatch) -> None:
    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=99),
        effective_message=SimpleNamespace(reply_text=reply_text),
    )
    monkeypatch.setattr(admin, "ADMIN_IDS", [99])
    monkeypatch.setattr(
        admin,
        "get_admin_stats",
        lambda: {
            "total_users": 7, "premium_users": 2, "avg_test_score": 4.5,
            "total_quizzes": 11, "total_answers": 110, "lessons_completed": 12,
        },
    )

    asyncio.run(admin.stats_command(update, SimpleNamespace()))

    assert "Umumiy foydalanuvchilar: 7" in reply_text.await_args.args[0]
    assert "Jami tugallangan quizlar: 11" in reply_text.await_args.args[0]


def test_premium_quiz_command_blocks_free_user(monkeypatch) -> None:
    update, message = _message_update(user_id=44003)
    monkeypatch.setattr(quiz, "has_active_premium", lambda user_id: False)

    asyncio.run(quiz.premium_quiz_command(update, SimpleNamespace(user_data={})))

    assert "Premium uchun" in message.reply_text.await_args.args[0]


def test_premium_quiz_inline_callback_rejects_free_user(monkeypatch) -> None:
    query = SimpleNamespace(
        data="premium:quiz",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        from_user=SimpleNamespace(id=44004),
    )
    update = SimpleNamespace(callback_query=query, effective_user=query.from_user)
    monkeypatch.setattr(quiz, "has_active_premium", lambda user_id: False)

    asyncio.run(quiz.premium_quiz_callback(update, SimpleNamespace(user_data={})))

    query.answer.assert_awaited_once()
    assert query.answer.await_args.kwargs["show_alert"] is True
    query.edit_message_text.assert_not_awaited()


def test_admin_premium_shortcut_remains_server_authorized(monkeypatch) -> None:
    update_reply = AsyncMock()
    message = SimpleNamespace(text="/admin_premium 700 true 1", reply_text=update_reply)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=99),
        effective_message=message,
    )
    grant_premium = Mock()
    monkeypatch.setattr(admin, "ADMIN_IDS", [99])
    monkeypatch.setattr(admin, "get_user", lambda user_id: {"telegram_id": user_id})
    monkeypatch.setattr(admin, "grant_admin_test_premium", grant_premium)

    asyncio.run(admin.admin_command(update, SimpleNamespace(args=["700", "true", "1"])))

    grant_premium.assert_called_once_with(700, 99, 1)
    assert "aktiv" in update_reply.await_args.args[0]


def test_ip_command_uses_argument(monkeypatch) -> None:
    reply_text = AsyncMock()
    update = SimpleNamespace(callback_query=None, effective_user=None, effective_message=SimpleNamespace(reply_text=reply_text))
    monkeypatch.setattr(
        tools,
        "get_ip_details",
        lambda value: {
            "status": "ok", "ip": value, "country": "Test", "region": "Region",
            "city": "City", "provider": "ISP", "type": "IPv4",
        },
    )

    asyncio.run(tools.ask_ip_address(update, SimpleNamespace(args=["8.8.8.8"], user_data={})))

    assert "8.8.8.8" in reply_text.await_args.args[0]


def test_dns_command_uses_argument(monkeypatch) -> None:
    reply_text = AsyncMock()
    update = SimpleNamespace(callback_query=None, effective_user=None, effective_message=SimpleNamespace(reply_text=reply_text))

    async def lookup_dns_records_async(domain, timeout):
        assert domain == "example.com"
        assert timeout == 5.0
        return {"A": ["93.184.216.34"], "AAAA": [], "MX": [], "NS": []}

    monkeypatch.setattr(
        tools,
        "lookup_dns_records_async",
        lookup_dns_records_async,
    )

    asyncio.run(tools.ask_dns_domain(update, SimpleNamespace(args=["example.com"], user_data={})))

    assert "93.184.216.34" in reply_text.await_args.args[0]


def test_settings_shows_language_and_notification_state(monkeypatch) -> None:
    reply_text = AsyncMock()
    update = SimpleNamespace(
        callback_query=None,
        effective_user=SimpleNamespace(id=44),
        effective_message=SimpleNamespace(reply_text=reply_text),
    )
    monkeypatch.setattr(start, "get_user_settings", lambda user_id: {"language": "uz", "notifications_enabled": 0})

    asyncio.run(settings_command(update, SimpleNamespace()))

    assert "O‘zbekcha" in reply_text.await_args.args[0]
    assert "Bildirishnoma afzalligi: o‘chirilgan" in reply_text.await_args.args[0]
    assert reply_text.await_args.kwargs["reply_markup"] is not None


def test_settings_callback_persists_notification_toggle(monkeypatch) -> None:
    query = SimpleNamespace(
        data="settings:notifications:toggle",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=44500))
    current_settings = {"language": "uz", "notifications_enabled": 0}
    monkeypatch.setattr(start, "get_user_settings", lambda user_id: current_settings)
    set_enabled = Mock()

    def persist_toggle(user_id, enabled):
        current_settings["notifications_enabled"] = int(enabled)

    set_enabled.side_effect = persist_toggle
    monkeypatch.setattr(start, "set_notifications_enabled", set_enabled)

    asyncio.run(start.settings_callback(update, SimpleNamespace(user_data={})))

    set_enabled.assert_called_once_with(44500, True)
    assert "Bildirishnoma afzalligi: yoqilgan" in query.edit_message_text.await_args.args[0]


def test_command_menu_failure_does_not_raise_or_log_secret(caplog) -> None:
    bot = SimpleNamespace(set_my_commands=AsyncMock(side_effect=RuntimeError("BOT_TOKEN=do-not-log")))
    application = SimpleNamespace(bot=bot)

    asyncio.run(set_bot_commands(application))

    bot.set_my_commands.assert_awaited_once_with(BOT_COMMANDS)
    assert "do-not-log" not in caplog.text


def test_start_and_help_commands_reply_with_expected_content(monkeypatch) -> None:
    update, message = _message_update()
    monkeypatch.setattr(start, "ensure_user", lambda *args, **kwargs: None)
    monkeypatch.setattr(start, "ensure_referral_code", lambda *args, **kwargs: "TESTCODE")
    monkeypatch.setattr(start, "register_referral", lambda *args, **kwargs: False)
    monkeypatch.setattr(start, "record_user_activity", lambda *args, **kwargs: {"streak": 1})
    monkeypatch.setattr("database.db.is_subscription_required", lambda: False)

    asyncio.run(start.start_command(update, SimpleNamespace(user_data={}, args=[])))
    assert "xush kelibsiz" in message.reply_text.await_args.args[0]
    message.reply_text.reset_mock()

    asyncio.run(start.help_command(update, SimpleNamespace()))
    assert "/leaderboard" in message.reply_text.await_args.args[0]


def test_profile_command_displays_database_values(monkeypatch) -> None:
    update, message = _message_update()
    monkeypatch.setattr(
        start,
        "get_user_profile_stats",
        lambda user_id: {
            "user": {
                "telegram_id": user_id, "first_name": "Test", "username": "testuser",
                "created_at": "2026-01-01", "test_score": 8, "is_premium": 1,
                "premium_expires_at": "2026-12-01",
            },
            "quiz_count": 2,
            "total_correct": 8,
            "total_answers": 20,
            "accuracy": 40.0,
            "total_score": 15,
            "lessons_completed": 3,
        },
    )
    monkeypatch.setattr("database.db.get_user_activity", lambda user_id: {"streak": 2, "last_active_date": "2026-01-02", "total_active_days": 3, "bonus_points": 0})
    monkeypatch.setattr("database.db.get_referral_stats", lambda user_id: {"invited": 1, "bonuses_granted": 0})

    asyncio.run(start.profile_command(update, SimpleNamespace()))

    text = message.reply_text.await_args.args[0]
    assert "To‘g‘ri javoblar: 8/20" in text
    assert "Jami ball: 15" in text
    assert "Premium: Faol" in text


def test_lessons_command_shows_lesson_keyboard() -> None:
    update, message = _message_update()

    asyncio.run(learning.show_lessons(update, SimpleNamespace()))

    assert "Kiberxavfsizlik darslari" in message.reply_text.await_args.args[0]
    assert message.reply_text.await_args.kwargs["reply_markup"] is not None


def test_lesson_complete_callback_persists_user_progress(monkeypatch) -> None:
    update, _ = _message_update(user_id=45001)
    query = SimpleNamespace(
        data="lesson:complete:1",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    update.callback_query = query
    mark_completed = Mock()
    monkeypatch.setattr(learning, "mark_lesson_completed", mark_completed)

    asyncio.run(learning.handle_lesson_callback(update, SimpleNamespace(user_data={})))

    mark_completed.assert_called_once_with(45001, 1)
    assert "Tugallangan" in str(query.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard)


def test_quiz_command_starts_and_registers_user(monkeypatch) -> None:
    update, message = _message_update()
    ensure_user = Mock()
    question = quiz.QUIZ_QUESTIONS[0]
    monkeypatch.setattr(quiz, "ensure_user", ensure_user)
    monkeypatch.setattr(quiz, "get_or_create_quiz_run", lambda user_id, **kwargs: {
        "run_id": "a" * 32,
        "current_index": 0,
        "score": 0,
        "reused_questions": 0,
        "questions": [question],
    })
    context = SimpleNamespace(user_data={})

    asyncio.run(quiz.start_quiz(update, context))

    ensure_user.assert_called_once_with(44, "testuser", "Test", "User")
    assert quiz.QUIZ_QUESTIONS[0]["question"] in message.reply_text.await_args.args[0]
    assert len(message.reply_text.await_args.kwargs["reply_markup"].inline_keyboard) == 4
    assert context.user_data["quiz_index"] == 0


def test_quiz_answer_shows_feedback_score_and_only_next_question(monkeypatch) -> None:
    run_id = "b" * 32
    current = quiz.QUIZ_QUESTIONS[0]
    next_question = quiz.QUIZ_QUESTIONS[1]
    quiz_answer = AsyncMock()
    edit_message_text = AsyncMock()
    query = SimpleNamespace(
        data=f"quiz:answer:{run_id}:0:{current['answer']}",
        answer=quiz_answer,
        edit_message_text=edit_message_text,
        from_user=SimpleNamespace(id=44),
    )
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=44))
    monkeypatch.setattr(quiz, "answer_quiz_question", lambda *args: {
        "question": current,
        "is_correct": True,
        "score": 1,
        "position": 0,
        "next_index": 1,
        "completed": False,
        "next_question": next_question,
    })
    monkeypatch.setattr(quiz, "get_or_create_quiz_run", lambda user_id: {"reused_questions": 0})
    context = SimpleNamespace(user_data={
        "quiz_index": 0,
        "quiz_score": 0,
        "quiz_last_question": None,
        "quiz_completed": False,
    })

    asyncio.run(quiz.handle_quiz_callback(update, context))

    text = edit_message_text.await_args.args[0]
    assert "To‘g‘ri" in text
    assert "Joriy ball: 1/10" in text
    assert next_question["question"] in text
    assert current["question"] not in text
    assert context.user_data["quiz_index"] == 1
    assert context.user_data["quiz_score"] == 1
    assert context.user_data["quiz_completed"] is False


def test_quiz_wrong_answer_and_final_score_are_recorded(monkeypatch) -> None:
    run_id = "c" * 32
    current = quiz.QUIZ_QUESTIONS[0]
    first_result = {
        "question": current,
        "is_correct": False,
        "score": 0,
        "position": 0,
        "next_index": 1,
        "completed": False,
        "next_question": quiz.QUIZ_QUESTIONS[1],
    }
    monkeypatch.setattr(quiz, "answer_quiz_question", lambda *args: first_result)
    monkeypatch.setattr(quiz, "get_or_create_quiz_run", lambda user_id: {"reused_questions": 0})
    wrong_query = SimpleNamespace(
        data=f"quiz:answer:{run_id}:0:{(current['answer'] + 1) % 4}",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        from_user=SimpleNamespace(id=44001),
    )
    wrong_context = SimpleNamespace(user_data={
        "quiz_index": 0, "quiz_score": 0, "quiz_last_question": None, "quiz_completed": False,
    })
    asyncio.run(quiz.handle_quiz_callback(SimpleNamespace(callback_query=wrong_query, effective_user=wrong_query.from_user), wrong_context))
    assert "Noto‘g‘ri" in wrong_query.edit_message_text.await_args.args[0]
    assert "Joriy ball: 0/10" in wrong_query.edit_message_text.await_args.args[0]
    assert wrong_context.user_data["quiz_index"] == 1

    final_result = {
        "question": quiz.QUIZ_QUESTIONS[9],
        "is_correct": True,
        "score": 5,
        "position": 9,
        "next_index": 10,
        "completed": True,
        "next_question": None,
    }
    monkeypatch.setattr(quiz, "answer_quiz_question", lambda *args: final_result)
    final_query = SimpleNamespace(
        data=f"quiz:answer:{run_id}:9:{quiz.QUIZ_QUESTIONS[9]['answer']}",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        from_user=SimpleNamespace(id=44002),
    )
    final_context = SimpleNamespace(user_data={
        "quiz_index": 9, "quiz_score": 4, "quiz_last_question": 8, "quiz_completed": False,
    })
    asyncio.run(quiz.handle_quiz_callback(SimpleNamespace(callback_query=final_query, effective_user=final_query.from_user), final_context))

    final_text = final_query.edit_message_text.await_args.args[0]
    assert "5/10" in final_text
    assert "50%" in final_text
    assert "To‘g‘ri javob:" in final_text
    assert final_context.user_data["quiz_completed"] is True
    assert final_context.user_data["quiz_index"] == 10


def test_ip_and_dns_commands_prompt_without_arguments() -> None:
    update, message = _message_update()

    context = SimpleNamespace(args=[], user_data={})
    asyncio.run(tools.ask_ip_address(update, context))
    assert "IPv4 yoki IPv6 manzilni yuboring" in message.reply_text.await_args.args[0]
    assert context.user_data["pending_lookup"] == "ip"
    message.reply_text.reset_mock()

    asyncio.run(tools.ask_dns_domain(update, context))
    assert "Domen nomini yuboring" in message.reply_text.await_args.args[0]
    assert context.user_data["pending_lookup"] == "dns"


def test_osint_command_opens_safe_options() -> None:
    update, message = _message_update()

    asyncio.run(tools.show_osint_menu(update, SimpleNamespace()))

    assert "OSINT asoslari" in message.reply_text.await_args.args[0]
    assert message.reply_text.await_args.kwargs["reply_markup"] is not None


def test_premium_command_includes_current_user_status(monkeypatch) -> None:
    update, message = _message_update()
    monkeypatch.setattr(premium, "ensure_user", lambda *args: None)
    monkeypatch.setattr(
        premium,
        "get_premium_status",
        lambda user_id: {
            "is_active": True,
            "started_at": "2026-01-01T00:00:00Z",
            "expires_at": "2026-12-01T00:00:00Z",
            "source": "admin_test",
        },
    )

    asyncio.run(premium.show_premium(update, SimpleNamespace()))

    assert "Premium faol" in message.reply_text.await_args.args[0]


def test_leaderboard_command_formats_database_rows(monkeypatch) -> None:
    update, message = _message_update()
    monkeypatch.setattr(
        start,
        "get_leaderboard_with_user",
        lambda user_id: {
            "top": [{"first_name": "Winner", "username": "winner", "telegram_id": 1, "test_score": 9}],
            "user": {"telegram_id": user_id, "first_name": "Test", "username": "testuser", "test_score": 6, "rank": 2},
        },
    )

    asyncio.run(start.leaderboard_command(update, SimpleNamespace()))

    assert "1. Winner — 9 ball" in message.reply_text.await_args.args[0]
    assert "Sizning o‘rningiz: 2." in message.reply_text.await_args.args[0]
