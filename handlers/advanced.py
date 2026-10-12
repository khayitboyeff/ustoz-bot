from __future__ import annotations

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from database.db import ensure_user
from database.features import complete_daily_task, get_activity, grant_achievement, list_achievements
from handlers.rate_limit import rate_limited
from services.certificate_service import build_certificate_pdf
from services.ctf_service import challenges, hint as ctf_hint, progress as ctf_progress, submit
from services.phishing_service import analyze_message
from services.premium_service import has_active_premium

logger = logging.getLogger(__name__)


def _ensure(update: Update) -> int | None:
    user = update.effective_user
    if user is None:
        return None
    ensure_user(user.id, user.username, user.first_name, user.last_name)
    return user.id


@rate_limited("phishing_analyze", 1.0)
async def phishing_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _ensure(update) is None or update.effective_message is None:
        return
    text = " ".join(context.args or []).strip()
    if not text:
        context.user_data["pending_advanced"] = "phishing"
        await update.effective_message.reply_text("Shubhali xabar yoki URL matnini yuboring. Havola ochilmaydi. /cancel — bekor qilish.")
        return
    await _send_phishing_result(update, text)


async def _send_phishing_result(update: Update, text: str) -> None:
    message = update.effective_message
    if message is None:
        return
    try:
        result = analyze_message(text)
    except ValueError as exc:
        await message.reply_text(str(exc))
        return
    indicators = "\n".join(f"• {item}" for item in result["indicators"]) or "• Aniq xavf indikatori topilmadi"
    advice = "\n".join(f"• {item}" for item in result["advice"])
    await message.reply_text(f"🛡 Phishing tahlili\nTaxminiy xavf: {result['level']}\n\nBelgilar:\n{indicators}\n\nTavsiya:\n{advice}\n\nBu qoidaviy taxmin, 100% kafolat emas. URL ochilmadi.")


@rate_limited("ctf", 1.0)
async def ctf_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _ensure(update) is None or update.effective_message is None:
        return
    try:
        items = challenges()
        user_id = update.effective_user.id
        premium = has_active_premium(user_id)
    except Exception as exc:
        logger.warning("CTF list failed (%s).", type(exc).__name__)
        await update.effective_message.reply_text("CTF topshiriqlarini hozir olib bo‘lmadi.")
        return
    if not items:
        await update.effective_message.reply_text("Hozircha CTF topshiriqlari yo‘q.")
        return
    rows = []
    for item in items[:30]:
        locked = bool(item.get("is_premium")) and not premium
        label = f"🔒 " if locked else "🧩 "
        rows.append([InlineKeyboardButton(f"{label}{item['title']} · {item['points']} ball", callback_data=f"ctf:open:{int(item['id'])}")])
    rows.append([InlineKeyboardButton("📊 Progress", callback_data="ctf:progress")])
    rows.append([InlineKeyboardButton("💎 Premium", callback_data="menu:premium"), InlineKeyboardButton("🏠 Menyu", callback_data="menu:main")])
    await update.effective_message.reply_text("🧩 OFFLINE CTF LAB\nTopshiriqlar lokal tekshiriladi; real tizimga so‘rov yuborilmaydi. 🔒 — Premium talab qiladi.", reply_markup=InlineKeyboardMarkup(rows))


async def ctf_open_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = _ensure(update)
    if query is None or user_id is None:
        return
    try:
        challenge_id = int((query.data or "").rsplit(":", 1)[1])
        item = next((x for x in challenges() if int(x["id"]) == challenge_id), None)
    except (ValueError, IndexError, TypeError) as exc:
        logger.warning("CTF callback invalid (%s).", type(exc).__name__)
        await query.answer("Topshiriqni ochib bo‘lmadi.", show_alert=True)
        return
    except Exception as exc:
        logger.warning("CTF lookup failed (%s).", type(exc).__name__)
        await query.answer("Topshiriqni hozir ochib bo‘lmadi.", show_alert=True)
        return
    if item is None:
        await query.answer("Topshiriq topilmadi.", show_alert=True)
        return
    if item.get("is_premium") and not has_active_premium(user_id):
        await query.answer("Bu CTF topshirig‘i Premium uchun. /premium orqali tarifni ko‘ring.", show_alert=True)
        return
    context.user_data["pending_advanced"] = "ctf"
    context.user_data["pending_ctf_id"] = challenge_id
    await query.answer()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💡 Maslahat", callback_data=f"ctf:hint:{challenge_id}")],
        [InlineKeyboardButton("📊 Progress", callback_data="ctf:progress"), InlineKeyboardButton("📚 Topshiriqlar", callback_data="ctf:list")],
        [InlineKeyboardButton("🏠 Menyu", callback_data="menu:main")],
    ])
    await query.edit_message_text(f"🧩 {item['title']}\nQiyinlik: {item['difficulty']} · Ball: {item['points']}\n\n{item['prompt']}\n\nKontekst: {item.get('context_text') or '—'}\n\nJavobni xabar sifatida yuboring. Maslahatni alohida tugmadan oling. /cancel — bekor qilish.", reply_markup=keyboard)


async def ctf_hint_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = _ensure(update)
    if query is None or user_id is None:
        return
    try:
        challenge_id = int((query.data or "").rsplit(":", 1)[1])
        result = await asyncio.to_thread(ctf_hint, user_id, challenge_id)
    except (ValueError, IndexError, TypeError):
        await query.answer("Maslahat so‘rovi yaroqsiz.", show_alert=True)
        return
    except Exception as exc:
        logger.warning("CTF hint failed (%s).", type(exc).__name__)
        await query.answer("Maslahatni hozir olib bo‘lmadi.", show_alert=True)
        return
    if result is None:
        await query.answer("Topshiriq topilmadi.", show_alert=True)
    elif result.get("locked"):
        await query.answer("Maslahat Premium uchun.", show_alert=True)
    else:
        await query.answer("Maslahat ochildi.")
        await query.message.reply_text(f"💡 Maslahat: {result['hint']}")


async def ctf_progress_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = _ensure(update)
    if query is None or user_id is None:
        return
    try:
        stats = await asyncio.to_thread(ctf_progress, user_id)
    except Exception as exc:
        logger.warning("CTF progress failed (%s).", type(exc).__name__)
        await query.answer("Progressni olib bo‘lmadi.", show_alert=True)
        return
    await query.answer()
    await query.message.reply_text(f"📊 CTF progress\nBajarilgan: {stats['solved']}\nYig‘ilgan ball: {stats['points']}\nYangi topshiriqlar uchun /ctf ni bosing.")


@rate_limited("ctf_progress", 1.0)
async def ctf_progress_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _ensure(update)
    message = update.effective_message
    if user_id is None or message is None:
        return
    try:
        stats = await asyncio.to_thread(ctf_progress, user_id)
        await message.reply_text(f"📊 CTF progress\nBajarilgan: {stats['solved']}\nYig‘ilgan ball: {stats['points']}")
    except Exception as exc:
        logger.warning("CTF progress command failed (%s).", type(exc).__name__)
        await message.reply_text("CTF progressni hozir olib bo‘lmadi.")


@rate_limited("certificate", 1.0)
async def certificate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _ensure(update)
    message = update.effective_message
    if user_id is None or message is None:
        return
    name = " ".join(context.args or []).strip()
    if not name:
        context.user_data["pending_advanced"] = "certificate"
        await message.reply_text("Sertifikatda ko‘rsatiladigan ismingizni yuboring. Sertifikat faqat talablar bajarilganda yaratiladi. /cancel — bekor qilish.")
        return
    await _issue_certificate(update, user_id, name)


async def _issue_certificate(update: Update, user_id: int, name: str) -> None:
    message = update.effective_message
    if message is None:
        return
    try:
        record, path = await asyncio.to_thread(build_certificate_pdf, user_id, name)
        with path.open("rb") as pdf_file:
            await message.reply_document(document=pdf_file, filename=f"certificate-{record['id']}.pdf", caption=f"Sertifikat ID: {record['id']}\nBu ta’limiy sertifikat.")
    except PermissionError as exc:
        await message.reply_text(str(exc))
    except (ValueError, LookupError) as exc:
        await message.reply_text(str(exc))
    except Exception as exc:
        logger.warning("Certificate generation failed (%s).", type(exc).__name__)
        await message.reply_text("Sertifikat yaratilmadi. Font/PDF kutubxonasi va kurs talablarini tekshiring.")


@rate_limited("cancel", 0.5)
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("pending_advanced", None)
    context.user_data.pop("pending_ctf_id", None)
    context.user_data.pop("pending_content_admin", None)
    context.user_data.pop("content_draft", None)
    context.user_data.pop("pending_payment_plan", None)
    if update.effective_message:
        await update.effective_message.reply_text("Joriy amal bekor qilindi.")


async def handle_advanced_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    mode = context.user_data.get("pending_advanced")
    message = update.effective_message
    user = update.effective_user
    if not mode or message is None or user is None:
        return False
    text = (message.text or "").strip()
    if not text:
        await message.reply_text("Bo‘sh matn yuborildi. Qayta urinib ko‘ring yoki /cancel yozing.")
        return True
    if mode == "phishing":
        context.user_data.pop("pending_advanced", None)
        await _send_phishing_result(update, text)
        return True
    if mode == "ctf":
        challenge_id = context.user_data.get("pending_ctf_id")
        try:
            result = await asyncio.to_thread(submit, user.id, int(challenge_id), text)
        except (ValueError, TypeError) as exc:
            await message.reply_text(str(exc))
            return True
        except Exception as exc:
            logger.warning("CTF answer failed (%s).", type(exc).__name__)
            await message.reply_text("Javobni tekshirib bo‘lmadi. Keyinroq urinib ko‘ring.")
            return True
        if result.get("reason") == "missing":
            await message.reply_text("Topshiriq topilmadi. /ctf orqali qayta tanlang.")
        elif result.get("reason") == "premium":
            await message.reply_text("Bu topshiriq Premium uchun. /premium orqali tarifni ko‘ring.")
            context.user_data.pop("pending_advanced", None)
            context.user_data.pop("pending_ctf_id", None)
        elif result.get("ok"):
            extra = " Bu topshiriq oldin bajarilgan; ball qayta berilmadi." if result.get("already_solved") else f" +{result.get('awarded', 0)} ball!"
            await message.reply_text("✅ To‘g‘ri javob!" + extra)
            try:
                complete_daily_task(user.id, "ctf")
                grant_achievement(user.id, "first_ctf")
            except Exception as exc:
                logger.debug("CTF achievement update skipped (%s).", type(exc).__name__)
            context.user_data.pop("pending_advanced", None)
            context.user_data.pop("pending_ctf_id", None)
        else:
            await message.reply_text("Javob noto‘g‘ri. Maslahat tugmasidan foydalanib qayta urinib ko‘ring yoki /cancel yozing.")
        return True
    if mode == "certificate":
        context.user_data.pop("pending_advanced", None)
        await _issue_certificate(update, user.id, text)
        return True
    return False


async def ctf_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()
    await ctf_command(update, context)


def register_advanced_handlers(app) -> None:
    app.add_handler(CommandHandler("phishing", phishing_command))
    app.add_handler(CommandHandler("ctf", ctf_command))
    app.add_handler(CommandHandler("ctf_progress", ctf_progress_command))
    app.add_handler(CommandHandler("certificate", certificate_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CallbackQueryHandler(ctf_open_callback, pattern=r"^ctf:open:\d+$"))
    app.add_handler(CallbackQueryHandler(ctf_hint_callback, pattern=r"^ctf:hint:\d+$"))
    app.add_handler(CallbackQueryHandler(ctf_progress_callback, pattern=r"^ctf:progress$"))
    app.add_handler(CallbackQueryHandler(ctf_list_callback, pattern=r"^ctf:list$"))
