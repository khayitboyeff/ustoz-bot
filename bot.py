from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.ext import Application, TypeHandler

from config import BOT_TOKEN
from database.db import init_db
from handlers import register_admin_handlers, register_advanced_handlers, register_learning_handlers, register_premium_handlers, register_quiz_handlers, register_start_handlers, register_tools_handlers
from handlers.content_admin import register_content_admin_handlers
from handlers.new_features import register_new_feature_handlers
from handlers.community import register_community_handlers, subscription_gate

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start", "Botni boshlash"),
    BotCommand("help", "Yordam"),
    BotCommand("lessons", "Kiberxavfsizlik darslari"),
    BotCommand("learning_path", "Shaxsiy o‘quv yo‘li"),
    BotCommand("xp", "XP va daraja"),
    BotCommand("daily", "Kunlik vazifalar"),
    BotCommand("cyberlab", "Xavfsiz Cyber Lab"),
    BotCommand("lesson_search", "Darslarni mavzu bo‘yicha qidirish"),
    BotCommand("quiz", "Bilim testini boshlash"),
    BotCommand("premium_quiz", "Premium qiyinlikdagi test"),
    BotCommand("profile", "Profil va test ballari"),
    BotCommand("ip", "IP manzilni tekshirish"),
    BotCommand("dns", "Domen DNS yozuvlarini tekshirish"),
    BotCommand("osint", "Ochiq OSINT bo‘limi"),
    BotCommand("premium", "💎 Pro tariflar va to‘lov"),
    BotCommand("premium_status", "Pro obuna muddati"),
    BotCommand("stats", "Admin statistikasi"),
    BotCommand("leaderboard", "Test natijalari reytingi"),
    BotCommand("settings", "Sozlamalar holati"),
    BotCommand("phishing", "Shubhali xabarni tahlil qilish"),
    BotCommand("ctf", "Xavfsiz CTF topshiriqlari"),
    BotCommand("ctf_progress", "CTF natijalari"),
    BotCommand("certificate", "Kurs sertifikati"),
    BotCommand("cancel", "Joriy amalni bekor qilish"),
    BotCommand("referral", "Taklif havolasi va statistikasi"),
    BotCommand("streak", "Kunlik o‘rganish davomiyligi"),
    BotCommand("daily", "Bugungi vazifalar"),
    BotCommand("broadcast", "Admin: xabar tarqatish"),
    BotCommand("admin", "Admin paneli"),
]


async def automatic_backup_job(context) -> None:
    """Create a daily database backup; failures are logged without stopping polling."""
    from services.backup_service import create_database_backup
    try:
        path = create_database_backup()
        logger.info("Automatic database backup created: %s", path.name)
    except Exception as exc:
        logger.warning("Automatic database backup failed (%s).", type(exc).__name__)


async def set_bot_commands(application: Application) -> None:
    try:
        await application.bot.set_my_commands(BOT_COMMANDS)
    except Exception as exc:
        logger.warning("Telegram command menu setup failed (%s); bot will continue.", type(exc).__name__)
    if application.job_queue is not None:
        application.job_queue.run_repeating(automatic_backup_job, interval=86400, first=86400, name="daily_database_backup")
    else:
        logger.warning("Automatic backup scheduler unavailable; install python-telegram-bot[job-queue].")


async def handle_update_error(update, context) -> None:
    error = context.error
    logger.error("Unhandled Telegram update error (%s).", type(error).__name__)


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("Xatolik: BOT_TOKEN topilmadi. .env faylini yaratib, Telegram tokenini kiriting.")

    init_db()
    app = Application.builder().token(BOT_TOKEN).post_init(set_bot_commands).build()

    # Global subscription gate must run before normal commands and callbacks.
    app.add_handler(TypeHandler(Update, subscription_gate), group=-1)
    register_community_handlers(app)
    register_tools_handlers(app)
    register_start_handlers(app)
    register_advanced_handlers(app)
    register_learning_handlers(app)
    register_quiz_handlers(app)
    register_premium_handlers(app)
    register_admin_handlers(app)
    register_content_admin_handlers(app)
    register_new_feature_handlers(app)
    app.add_error_handler(handle_update_error)

    print("CyberUstozBot ishga tushirildi. Telegram polling boshlandi...")
    app.run_polling()


if __name__ == "__main__":
    main()
