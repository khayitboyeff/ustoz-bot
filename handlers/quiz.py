from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from database.db import answer_quiz_question, ensure_user, get_or_create_quiz_run
from handlers.rate_limit import rate_limited
from services.question_bank import generate_verified_questions
from services.premium_service import has_active_premium

logger = logging.getLogger(__name__)
QUIZ_QUESTIONS = generate_verified_questions()


def build_question_markup(run_id: str, position: int, question: dict) -> InlineKeyboardMarkup:
    buttons = []
    for idx, option in enumerate(question["options"]):
        buttons.append([
            InlineKeyboardButton(option, callback_data=f"quiz:answer:{run_id}:{position}:{idx}")
        ])
    return InlineKeyboardMarkup(buttons)


def build_question_text(question: dict, position: int, reused_questions: int = 0) -> str:
    note = "\n\nSavollar banki yangilanmagani uchun ayrim oldingi savollar qayta ishlatilmoqda." if reused_questions else ""
    return (
        f"🧪 Savol {position + 1}/10 · {question['topic']} · {question['difficulty']}\n\n"
        f"{question['question']}\n\n"
        f"Javob variantini tanlang:{note}"
    )


@rate_limited("quiz_start", 3)
async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _start_quiz(update, context, premium_only=False)


@rate_limited("premium_quiz_start", 3)
async def premium_quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    query = update.callback_query
    if user is None or query is None:
        return
    try:
        if not has_active_premium(user.id):
            await query.answer("Premium quiz uchun faol Premium huquqi kerak.", show_alert=True)
            return
    except Exception as exc:
        logger.warning("Premium quiz callback authorization failed (%s).", type(exc).__name__)
        await query.answer("Premium holatini hozir tekshirib bo‘lmadi.", show_alert=True)
        return
    await _start_quiz(update, context, premium_only=True)


@rate_limited("premium_quiz_start", 3)
async def premium_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    try:
        if not has_active_premium(user.id):
            await message.reply_text("Bu test Premium uchun. Faollashtirish tartibini /premium buyrug‘idan ko‘ring.")
            return
    except Exception as exc:
        logger.warning("Premium quiz authorization failed (%s).", type(exc).__name__)
        await message.reply_text("Premium holatini tekshirib bo‘lmadi. Keyinroq qayta urinib ko‘ring.")
        return
    await _start_quiz(update, context, premium_only=True)


async def _start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE, *, premium_only: bool) -> None:
    query = update.callback_query
    user = update.effective_user
    message = update.effective_message
    if user is None:
        return
    ensure_user(user.id, user.username, user.first_name, user.last_name)
    context.user_data.pop("pending_lookup", None)
    try:
        run = get_or_create_quiz_run(user.id, premium_only=premium_only)
    except PermissionError:
        text = "Faol Premium huquqi talab qilinadi. /premium buyrug‘idan ma’lumot oling."
        if query is not None:
            await query.answer()
            await query.edit_message_text(text)
        elif message is not None:
            await message.reply_text(text)
        return
    except Exception as exc:
        logger.warning("Quiz run creation failed (%s).", type(exc).__name__)
        text = "Testni hozir boshlab bo‘lmadi. Birozdan so‘ng qayta urinib ko‘ring."
        if query is not None:
            await query.answer()
            await query.edit_message_text(text)
        elif message is not None:
            await message.reply_text(text)
        return
    if run is None or not run["questions"]:
        text = "Hozircha test uchun yetarli tasdiqlangan savollar yo‘q. Savollar bankiga yangi savollar qo‘shilishi kerak."
        if query is not None:
            await query.answer()
            await query.edit_message_text(text)
        elif message is not None:
            await message.reply_text(text)
        return

    run_id = run["run_id"]
    position = int(run["current_index"])
    question = run["questions"][position]
    context.user_data["quiz_run_id"] = run_id
    context.user_data["quiz_index"] = position
    context.user_data["quiz_score"] = int(run["score"])
    context.user_data["quiz_completed"] = False
    text = build_question_text(question, position, int(run["reused_questions"]))
    markup = build_question_markup(run_id, position, question)

    if query is not None:
        await query.answer()
        await query.edit_message_text(text, reply_markup=markup)
    elif message is not None:
        await message.reply_text(text, reply_markup=markup)


@rate_limited("quiz_answer", 0.5)
async def handle_quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    data = (query.data or "").strip()
    if not data.startswith("quiz:answer:"):
        return

    try:
        _, _, run_id, position_str, answer_index_str = data.split(":")
        position = int(position_str)
        answer_index = int(answer_index_str)
    except (ValueError, TypeError):
        await query.answer("Javob formati xato.")
        return

    if position < 0 or position >= 10 or answer_index < 0 or answer_index >= 4:
        await query.answer("Javob varianti noto‘g‘ri.")
        return

    await query.answer()
    user = query.from_user
    if user is None:
        return
    try:
        result = answer_quiz_question(user.id, run_id, position, answer_index)
    except Exception as exc:
        logger.warning("Quiz answer persistence failed (%s).", type(exc).__name__)
        await query.edit_message_text("Javobni saqlab bo‘lmadi. Iltimos, /quiz orqali test holatini tekshiring.")
        return
    if result is None:
        await query.edit_message_text("Bu test savoli eskirgan yoki allaqachon javoblangan. Davom etish uchun /quiz ni bosing.")
        return

    context.user_data["quiz_run_id"] = run_id
    context.user_data["quiz_index"] = result["next_index"]
    context.user_data["quiz_score"] = result["score"]
    context.user_data["quiz_completed"] = result["completed"]
    question = result["question"]
    status = "✅ To‘g‘ri!" if result["is_correct"] else "❌ Noto‘g‘ri."
    correct_answer = question["options"][question["answer"]]
    feedback = f"{status}\nTo‘g‘ri javob: {correct_answer}\nJoriy ball: {result['score']}/{10}"

    if result["completed"]:
        percentage = result["score"] * 10
        try:
            from database.features import complete_daily_task, grant_achievement
            complete_daily_task(user.id, "quiz")
            grant_achievement(user.id, "first_quiz")
            if result["score"] == 10:
                grant_achievement(user.id, "perfect_quiz")
        except Exception as exc:
            logger.debug("Quiz achievement update skipped (%s).", type(exc).__name__)
        await query.edit_message_text(
            f"{feedback}\n\n🏁 Test yakunlandi!\nYakuniy natija: {result['score']}/10 ({percentage}%).\n"
            "Kunlik vazifa va yutuqlar profilingizda saqlanadi."
        )
        return

    next_question = result["next_question"]
    run = get_or_create_quiz_run(user.id)
    reused = int(run["reused_questions"]) if run else 0
    next_text = build_question_text(next_question, result["next_index"], reused)
    await query.edit_message_text(
        f"{feedback}\n\n{next_text}",
        reply_markup=build_question_markup(run_id, result["next_index"], next_question),
    )


def register_quiz_handlers(app) -> None:
    app.add_handler(CommandHandler("quiz", start_quiz))
    app.add_handler(CommandHandler("premium_quiz", premium_quiz_command))
    app.add_handler(CallbackQueryHandler(handle_quiz_callback, pattern=r"^quiz:answer:"))
    app.add_handler(CallbackQueryHandler(premium_quiz_callback, pattern=r"^premium:quiz$"))
