from __future__ import annotations

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from config import ADMIN_IDS
from database.db import get_admin_stats, get_all_users, get_user, record_admin_action
from database.features import create_broadcast, confirm_broadcast, mark_broadcast_sent, list_user_ids
from handlers.rate_limit import rate_limited
from services.premium_service import grant_admin_test_premium, revoke_premium
from services.backup_service import create_database_backup, restore_database_backup

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def _audit_admin_read(actor_id: int, action: str, target_id: int = 0) -> None:
    try:
        record_admin_action(actor_id, action, target_id)
    except Exception as exc:
        logger.warning("Admin audit write failed (%s).", type(exc).__name__)


@rate_limited("admin_stats", 5)
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    if not is_admin(user.id):
        await message.reply_text("⚠️ Sizga admin huquqi berilmagan.")
        return
    try:
        stats = get_admin_stats()
    except Exception as exc:
        logger.warning("Admin statistics query failed (%s).", type(exc).__name__)
        await message.reply_text("Statistikani hozir olib bo‘lmadi. Keyinroq urinib ko‘ring.")
        return
    _audit_admin_read(user.id, "stats_view")
    await message.reply_text(
        "👑 Admin statistikasi\n\n"
        f"Umumiy foydalanuvchilar: {stats['total_users']}\n"
        f"Jami tugallangan quizlar: {stats.get('total_quizzes', 0)}\n"
        f"Jami javoblar: {stats.get('total_answers', 0)}\n"
        f"Tugallangan darslar: {stats.get('lessons_completed', 0)}\n"
        f"Premium foydalanuvchilar: {stats['premium_users']}\n"
        f"O‘rtacha test bali: {stats['avg_test_score']:.2f}"
    )

@rate_limited("admin_backup", 10)
async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    if not is_admin(user.id):
        await message.reply_text("⚠️ Sizga admin huquqi berilmagan.")
        return
    try:
        backup = create_database_backup()
        _audit_admin_read(user.id, "database_backup")
    except Exception as exc:
        logger.warning("Database backup failed (%s).", type(exc).__name__)
        await message.reply_text("Backup yaratilmadi. Bazaga yozish uchun disk va papka ruxsatlarini tekshiring.")
        return
    await message.reply_text(f"SQLite backup yaratildi: {backup.name}")

@rate_limited("admin_restore", 10)
async def restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    if not is_admin(user.id):
        await message.reply_text("⚠️ Sizga admin huquqi berilmagan.")
        return
    if len(context.args) != 1:
        await message.reply_text("Format: /admin_restore <backup_fayl_nomi.sqlite3>")
        return
    try:
        result = restore_database_backup(context.args[0])
        _audit_admin_read(user.id, "database_restore", metadata={"backup": result["restored"].name})
    except Exception as exc:
        logger.warning("Database restore failed (%s).", type(exc).__name__)
        await message.reply_text("Backup tiklanmadi. Fayl schema va yaxlitlik tekshiruvlaridan o‘tmadi yoki mavjud emas.")
        return
    await message.reply_text(
        "SQLite backup tiklandi.\n"
        f"Xavfsizlik nusxasi: {result['safety_backup'].name}"
    )


@rate_limited("admin", 2)
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None:
        return
    if message is None:
        return
    if not is_admin(user.id):
        await message.reply_text("⚠️ Sizga admin huquqi berilmagan.")
        return

    message_text = message.text or ""
    command_name = message_text.split(maxsplit=1)[0].split("@", 1)[0].lstrip("/").lower()
    shortcut_commands = {
        "admin_stats": "stats",
        "admin_users": "users",
        "admin_user": "user",
        "admin_premium": "premium",
    }
    args = context.args
    if command_name in shortcut_commands:
        args = [shortcut_commands[command_name], *args]
    if not args:
        await message.reply_text(
            "👑 CYBERUSTOZ ADMIN PANEL\n\n"
            "📊 /admin stats — statistika\n"
            "👥 /admin_users — foydalanuvchilar\n"
            "👤 /admin_user <user_id> — foydalanuvchi\n"
            "💎 /admin_premium <user_id> true|false [days] — test obuna\n"
            "🧾 To‘lov cheklarini tasdiqlash uchun chek xabaridagi tugmalardan foydalaning.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛠 Test va savol-javob qo‘shish", callback_data="admin:content")],
                [InlineKeyboardButton("📊 Statistika", callback_data="admin:stats")],
                [InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu:main")],
            ])
        )
        return

    command = args[0].lower()
    if command in {"stats", "stat", "statistics"}:
        try:
            stats = get_admin_stats()
        except Exception as exc:
            logger.warning("Admin statistics query failed (%s).", type(exc).__name__)
            await message.reply_text("Statistikani hozir olib bo‘lmadi. Keyinroq urinib ko‘ring.")
            return
        _audit_admin_read(user.id, "stats_view")
        await message.reply_text(
            "👑 Admin statistikasi\n\n"
            f"Umumiy foydalanuvchilar: {stats['total_users']}\n"
            f"Jami tugallangan quizlar: {stats.get('total_quizzes', 0)}\n"
            f"Jami javoblar: {stats.get('total_answers', 0)}\n"
            f"Tugallangan darslar: {stats.get('lessons_completed', 0)}\n"
            f"Faol admin darslari: {stats.get('active_custom_lessons', 0)}\n"
            f"Berilgan sertifikatlar: {stats.get('certificates_issued', 0)}\n"
            f"Premium foydalanuvchilar: {stats['premium_users']}\n"
            f"Muvaffaqiyatli to‘lovlar: {stats.get('successful_payments', 0)}\n"
            f"Telegram Stars tushumi: {stats.get('stars_received', 0)} ⭐ ({stats.get('stars_payments_count', 0)} ta to‘lov)\n"
            f"Tekshirilishi kutilayotgan chek: {stats.get('pending_manual_payments', 0)}\n"
            f"O‘rtacha test bali: {stats['avg_test_score']:.2f}"
        )
        return

    if command == "users":
        try:
            users = get_all_users()
        except Exception as exc:
            logger.warning("Admin user-list query failed (%s).", type(exc).__name__)
            await message.reply_text("Foydalanuvchilar ro‘yxatini hozir olib bo‘lmadi.")
            return
        _audit_admin_read(user.id, "user_list_view")
        await message.reply_text(f"Foydalanuvchilar soni: {len(users)}")
        return

    if command == "user":
        if len(args) < 2:
            await message.reply_text("Foydalanuvchi ID sini kiriting: /admin_user 123456789")
            return
        try:
            target_id = int(args[1])
        except ValueError:
            await message.reply_text("User ID son bo‘lishi kerak.")
            return
        if target_id <= 0:
            await message.reply_text("User ID musbat bo‘lishi kerak.")
            return
        try:
            row = get_user(target_id)
        except Exception as exc:
            logger.warning("Admin user query failed (%s).", type(exc).__name__)
            await message.reply_text("Foydalanuvchi ma’lumotini hozir olib bo‘lmadi.")
            return
        if not row:
            await message.reply_text("Bu foydalanuvchi topilmadi.")
            return
        _audit_admin_read(user.id, "user_lookup", target_id)
        await message.reply_text(
            f"ID: {row['telegram_id']}\n"
            f"Username: @{row['username'] or 'yo‘q'}\n"
            f"Ism: {row['first_name'] or 'Nomaʼlum'}\n"
            f"Premium: {'Ha' if row['is_premium'] else 'Yo‘q'}\n"
            f"Premium boshlanish: {row.get('premium_started_at') or 'yo‘q'}\n"
            f"Premium tugash: {row.get('premium_expires_at') or 'yo‘q'}\n"
            f"Ball: {row['test_score']}"
        )
        return

    if command == "premium":
        if len(args) < 3:
            await message.reply_text("Format: /admin_premium <user_id> true|false [days]")
            return
        try:
            target_id = int(args[1])
        except ValueError:
            await message.reply_text("User ID son bo‘lishi kerak.")
            return
        if target_id <= 0 or len(args) > 4:
            await message.reply_text("User ID musbat bo‘lsin va buyruqqa ortiqcha qiymat qo‘shmang.")
            return
        normalized_enabled = args[2].lower()
        if normalized_enabled not in {"true", "1", "yes", "on", "false", "0", "no", "off"}:
            await message.reply_text("Premium qiymati true yoki false bo‘lishi kerak.")
            return
        enabled = normalized_enabled in {"true", "1", "yes", "on"}
        if not enabled and len(args) != 3:
            await message.reply_text("Premiumni bekor qilish formati: /admin_premium <user_id> false")
            return
        days = 30
        if enabled:
            if len(args) >= 4:
                try:
                    days = int(args[3])
                except ValueError:
                    await message.reply_text("Kunlar son bo‘lishi kerak.")
                    return
                if not 1 <= days <= 3650:
                    await message.reply_text("Premium muddati 1 dan 3650 kungacha bo‘lishi kerak.")
                    return
        else:
            days = 0
        try:
            target_user = get_user(target_id)
        except Exception as exc:
            logger.warning("Admin premium lookup failed (%s).", type(exc).__name__)
            await message.reply_text("Foydalanuvchi ma’lumotini hozir olib bo‘lmadi.")
            return
        if target_user is None:
            await message.reply_text("Bu foydalanuvchi topilmadi.")
            return
        try:
            if enabled:
                grant_admin_test_premium(target_id, user.id, days)
            else:
                revoke_premium(target_id, user.id)
        except (ValueError, LookupError) as exc:
            await message.reply_text(str(exc))
            return
        except Exception as exc:
            logger.warning("Admin premium update failed (%s).", type(exc).__name__)
            await message.reply_text("Premium holatini hozir o‘zgartirib bo‘lmadi.")
            return
        await message.reply_text(
            f"Foydalanuvchi {target_id} uchun premium holati o‘zgartirildi: {'aktiv' if enabled else 'o‘chirildi'}"
        )
        return

    await message.reply_text("Noma’lum admin buyruqi.")



@rate_limited("admin_broadcast", 5)
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    if not is_admin(user.id):
        await message.reply_text("⚠️ Sizga admin huquqi berilmagan.")
        return
    body = " ".join(context.args or []).strip()
    if not body:
        await message.reply_text("Format: /broadcast <barcha foydalanuvchilarga yuboriladigan matn>\nXabar yuborishdan oldin alohida tasdiqlash talab qilinadi.")
        return
    try:
        job_id = create_broadcast(user.id, body)
        total = len(list_user_ids())
        record_admin_action(user.id, "broadcast_draft", 0, metadata={"job_id": job_id, "recipients": total})
    except Exception as exc:
        logger.warning("Broadcast draft failed (%s).", type(exc).__name__)
        await message.reply_text("Broadcast loyihasini yaratib bo‘lmadi.")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yuborishni tasdiqlash", callback_data=f"broadcast:confirm:{job_id}"),
         InlineKeyboardButton("❌ Bekor qilish", callback_data=f"broadcast:cancel:{job_id}")]
    ])
    preview = body if len(body) <= 2500 else body[:2500] + "…"
    await message.reply_text(f"📣 BROADCAST KO‘RIB CHIQISH\n\nQabul qiluvchilar: {total}\n\n{preview}\n\nBu xabarni yuborishni tasdiqlaysizmi?", reply_markup=keyboard)


async def broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    if not is_admin(user.id):
        await query.answer("Admin huquqi kerak.", show_alert=True)
        return
    try:
        action, job_id_text = (query.data or "").split(":")[1:]
        job_id = int(job_id_text)
        if action == "cancel":
            # A pending draft is only owned by its creator and can be cancelled by that admin.
            from database.db import get_connection
            with get_connection() as conn:
                cur = conn.execute("UPDATE broadcast_jobs SET status = 'cancelled' WHERE id = ? AND admin_id = ? AND status = 'pending'", (job_id, user.id))
                conn.commit()
                changed = cur.rowcount > 0
            await query.answer("Broadcast bekor qilindi." if changed else "Loyiha topilmadi yoki allaqachon ishlangan.", show_alert=True)
            if changed:
                await query.edit_message_text("❌ Broadcast bekor qilindi.")
            return
        if action != "confirm":
            raise ValueError("unknown action")
        job = confirm_broadcast(user.id, job_id)
        if job is None:
            await query.answer("Bu broadcast allaqachon ishlangan yoki sizga tegishli emas.", show_alert=True)
            return
        await query.answer("Yuborish boshlandi.")
        await query.edit_message_text("📣 Broadcast yuborilmoqda…")
        ids = list_user_ids()
        sent = failed = blocked = 0
        for recipient_id in ids:
            try:
                await context.bot.send_message(chat_id=recipient_id, text=job["body"])
                sent += 1
            except Exception as exc:
                name = type(exc).__name__
                failed += 1
                if "Forbidden" in name:
                    blocked += 1
                else:
                    logger.debug("Broadcast delivery failed (%s).", name)
            await asyncio.sleep(0.04)
        mark_broadcast_sent(job_id)
        record_admin_action(user.id, "broadcast_sent", 0, metadata={"job_id": job_id, "sent": sent, "failed": failed, "blocked": blocked})
        await query.message.reply_text(f"✅ Broadcast yakunlandi.\nMuvaffaqiyatli: {sent}\nXato: {failed}\nBot bloklangan/taqiqlangan: {blocked}")
    except (ValueError, IndexError) as exc:
        logger.warning("Broadcast callback invalid (%s).", type(exc).__name__)
        await query.answer("Broadcast so‘rovi yaroqsiz.", show_alert=True)
    except Exception as exc:
        logger.exception("Broadcast execution failed (%s).", type(exc).__name__)
        await query.message.reply_text("Broadcast jarayonida xato yuz berdi. Admin audit jurnalini tekshiring.")


async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    if not is_admin(user.id):
        await query.answer("Admin huquqi kerak.", show_alert=True)
        return
    await query.answer()
    await stats_command(update, context)


def register_admin_handlers(app) -> None:
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CallbackQueryHandler(broadcast_callback, pattern=r"^broadcast:(confirm|cancel):\d+$"))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("admin_stats", stats_command))
    app.add_handler(CommandHandler("admin_users", admin_command))
    app.add_handler(CommandHandler("admin_user", admin_command))
    app.add_handler(CommandHandler("admin_premium", admin_command))
    app.add_handler(CommandHandler("admin_backup", backup_command))
    app.add_handler(CommandHandler("admin_restore", restore_command))
    app.add_handler(CallbackQueryHandler(admin_stats_callback, pattern=r"^admin:stats$"))
