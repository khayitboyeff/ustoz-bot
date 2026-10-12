from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from database.db import ensure_user, get_connection, get_user_settings, get_completed_lessons
from handlers.rate_limit import rate_limited
from services.i18n import normalize_language

logger = logging.getLogger(__name__)

PATHS = {
    "basics": {"title": "Kiberxavfsizlik asoslari", "lessons": [1, 4, 5, 6, 12], "description": "Asosiy tushunchalar, akkaunt himoyasi, phishing va xavfsiz amaliyot."},
    "python": {"title": "Python xavfsizligi", "lessons": [1, 9, 8, 12], "description": "Python asoslari, tizim xavfsizligi va xavfsiz laboratoriya."},
    "network": {"title": "Tarmoq xavfsizligi", "lessons": [1, 2, 3, 6, 7, 12], "description": "IP, DNS, tarmoqlar, HTTPS va hodisaga javob."},
    "web": {"title": "Web xavfsizligi", "lessons": [1, 7, 10, 5, 12], "description": "HTTP/HTTPS, web xavfsizligi, phishingni aniqlash."},
    "privacy": {"title": "OSINT va maxfiylik", "lessons": [1, 4, 5, 11, 12], "description": "Ochiq manbalar, maxfiylik va etik qoidalar."},
}


def _ensure_user(update: Update) -> int | None:
    user = update.effective_user
    if user is None:
        return None
    ensure_user(user.id, user.username, user.first_name, user.last_name)
    return user.id


def xp_for_user(telegram_id: int) -> int:
    """XP is derived from existing records, so no extra migration is required."""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT
                (SELECT COALESCE(SUM(score), 0) FROM quiz_runs WHERE telegram_id=? AND completed=1) AS quiz_score,
                (SELECT COUNT(*) FROM lesson_progress WHERE telegram_id=?) AS lessons,
                (SELECT COALESCE(SUM(c.points), 0) FROM ctf_solves s JOIN ctf_challenges c ON c.id=s.challenge_id WHERE s.telegram_id=?) AS ctf_points,
                (SELECT COALESCE(bonus_points, 0) FROM user_activity WHERE telegram_id=?) AS bonus
            """,
            (telegram_id, telegram_id, telegram_id, telegram_id),
        ).fetchone()
    quiz_xp = int(row["quiz_score"] or 0) * 10
    lesson_xp = int(row["lessons"] or 0) * 20
    ctf_xp = int(row["ctf_points"] or 0)
    bonus = int(row["bonus"] or 0)
    return quiz_xp + lesson_xp + ctf_xp + bonus


def xp_leaderboard(limit: int = 10) -> list[dict]:
    limit = max(1, min(int(limit), 50))
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT u.telegram_id, u.username, u.first_name,
                (SELECT COALESCE(SUM(q.score),0) FROM quiz_runs q WHERE q.telegram_id=u.telegram_id AND q.completed=1)*10
                + (SELECT COUNT(*) FROM lesson_progress lp WHERE lp.telegram_id=u.telegram_id)*20
                + (SELECT COALESCE(SUM(c.points),0) FROM ctf_solves s JOIN ctf_challenges c ON c.id=s.challenge_id WHERE s.telegram_id=u.telegram_id)
                + COALESCE((SELECT a.bonus_points FROM user_activity a WHERE a.telegram_id=u.telegram_id),0) AS xp
                FROM users u ORDER BY xp DESC, u.telegram_id ASC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


@rate_limited("xp", 1.0)
async def xp_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _ensure_user(update)
    message = update.effective_message
    if user_id is None or message is None:
        return
    try:
        xp = xp_for_user(user_id)
        level = 1 + xp // 100
        next_level = level * 100
        rows = xp_leaderboard(50)
        rank = next((i for i, row in enumerate(rows, 1) if row["telegram_id"] == user_id), None)
        await message.reply_text(
            f"⭐ XP profilingiz\n\nXP: {xp}\nDaraja: {level}\nKeyingi darajagacha: {max(0, next_level - xp)} XP\nReytingdagi o‘rin: {rank or 'hali aniqlanmagan'}\n\n"
            "XP hisoblanishi: quiz ballari × 10, tugallangan dars × 20, CTF ballari va kunlik bonuslar.\n"
            "Buyruqlar: /leaderboard — TOP reyting, /daily — kunlik vazifalar."
        )
    except Exception as exc:
        logger.warning("XP profile failed (%s).", type(exc).__name__)
        await message.reply_text("XP ma’lumotini hozir olib bo‘lmadi. Keyinroq urinib ko‘ring.")


@rate_limited("learning_path", 1.0)
async def learning_path_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _ensure_user(update)
    message = update.effective_message
    if user_id is None or message is None:
        return
    rows = [
        [InlineKeyboardButton("🧭 Asoslar", callback_data="path:basics"), InlineKeyboardButton("🐍 Python", callback_data="path:python")],
        [InlineKeyboardButton("🌐 Tarmoq", callback_data="path:network"), InlineKeyboardButton("🕸 Web xavfsizligi", callback_data="path:web")],
        [InlineKeyboardButton("🔐 OSINT va maxfiylik", callback_data="path:privacy")],
        [InlineKeyboardButton("📚 Barcha darslar", callback_data="menu:lessons")],
    ]
    await message.reply_text("🗺 SHAXSIY O‘QUV YO‘LI\n\nYo‘nalishni tanlang. Bot darslarni tavsiya qiladi va tugallangan darslaringizni hisobga oladi.", reply_markup=InlineKeyboardMarkup(rows))


async def learning_path_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = _ensure_user(update)
    if query is None or user_id is None:
        return
    key = (query.data or "").split(":", 1)[-1]
    path = PATHS.get(key)
    if path is None:
        await query.answer("Yo‘nalish topilmadi.", show_alert=True)
        return
    try:
        from handlers.learning import all_lessons
        completed = get_completed_lessons(user_id)
        lessons_by_id = {int(item["id"]): item for item in all_lessons()}
        available = [lessons_by_id[i] for i in path["lessons"] if i in lessons_by_id]
        done = sum(1 for item in available if int(item["id"]) in completed)
        buttons = []
        for item in available:
            marker = "✅" if int(item["id"]) in completed else "📘"
            buttons.append([InlineKeyboardButton(f"{marker} {item['title']}", callback_data=f"lesson:{item['id']}")])
        buttons.append([InlineKeyboardButton("🗺 Boshqa yo‘nalishlar", callback_data="path:menu")])
        await query.answer()
        await query.edit_message_text(f"🗺 {path['title']}\n\n{path['description']}\n\nProgress: {done}/{len(available)} dars", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as exc:
        logger.warning("Learning path failed (%s).", type(exc).__name__)
        await query.answer("O‘quv yo‘lini ochib bo‘lmadi.", show_alert=True)


def register_new_feature_handlers(app) -> None:
    app.add_handler(CommandHandler("learning_path", learning_path_command))
    app.add_handler(CommandHandler("xp", xp_command))
    app.add_handler(CommandHandler("cyberlab", lambda update, context: _cyberlab(update, context)))
    app.add_handler(CallbackQueryHandler(learning_path_menu_callback, pattern=r"^path:menu$"))
    app.add_handler(CallbackQueryHandler(learning_path_callback, pattern=r"^path:(basics|python|network|web|privacy)$"))


async def learning_path_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()
        await learning_path_command(update, context)


async def _cyberlab(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from handlers.advanced import ctf_command
    await ctf_command(update, context)
