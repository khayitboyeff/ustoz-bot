from __future__ import annotations

import logging
import uuid
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from telegram import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, PreCheckoutQueryHandler, filters

from config import ADMIN_IDS, BOT_TOKEN, PAYMENT_CARD_BANK, PAYMENT_CARD_HOLDER, PAYMENT_CARD_INSTRUCTIONS, PAYMENT_CARD_NUMBER
from database.db import ensure_user, record_admin_action, get_connection, _parse_datetime, _utc_timestamp
from handlers.rate_limit import rate_limited
from services.manual_payment_service import PLAN_DAYS, PLAN_PRICES_UZS, create_request, get_request, review_request
from services.premium_service import get_premium_status

logger = logging.getLogger(__name__)

STARS_PLANS = {7: 50, 30: 150, 90: 350}
STARS_PLAN_LABELS = {7: "7 kun", 30: "30 kun", 90: "90 kun"}


def _create_stars_payload(days: int, user_id: int, nonce: str | None = None) -> str:
    """Create a bot-secret authenticated invoice payload; never trust client fields alone."""
    if not BOT_TOKEN or days not in STARS_PLANS or type(user_id) is not int or user_id <= 0:
        raise ValueError("Stars invoice konfiguratsiyasi yaroqsiz.")
    nonce = nonce or uuid.uuid4().hex
    if len(nonce) != 32 or any(ch not in "0123456789abcdef" for ch in nonce):
        raise ValueError("Invoice nonce yaroqsiz.")
    body = f"cyberustoz-premium:v1:{days}:{user_id}:{nonce}"
    signature = hmac.new(BOT_TOKEN.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}:{signature}"


def _verify_stars_payload(payload: str, user_id: int) -> int | None:
    if not isinstance(payload, str) or len(payload) > 200 or type(user_id) is not int or not BOT_TOKEN:
        return None
    parts = payload.split(":")
    if len(parts) != 6 or parts[0:2] != ["cyberustoz-premium", "v1"]:
        return None
    try:
        days, owner_id = int(parts[2]), int(parts[3])
    except (TypeError, ValueError):
        return None
    if days not in STARS_PLANS or owner_id != user_id or owner_id <= 0:
        return None
    if len(parts[4]) != 32 or any(ch not in "0123456789abcdef" for ch in parts[4]):
        return None
    expected = _create_stars_payload(days, owner_id, parts[4])
    return days if hmac.compare_digest(expected, payload) else None


def _money(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


def _premium_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⭐ 7 kun · {STARS_PLANS[7]} Stars", callback_data="premium:stars:7")],
        [InlineKeyboardButton(f"⭐ 30 kun · {STARS_PLANS[30]} Stars", callback_data="premium:stars:30")],
        [InlineKeyboardButton(f"⭐ 90 kun · {STARS_PLANS[90]} Stars", callback_data="premium:stars:90")],
        [InlineKeyboardButton(f"💳 1 oy · {_money(PLAN_PRICES_UZS[1])} so‘m", callback_data="premium:plan:1")],
        [InlineKeyboardButton(f"💳 3 oy · {_money(PLAN_PRICES_UZS[3])} so‘m", callback_data="premium:plan:3")],
        [InlineKeyboardButton(f"💳 6 oy · {_money(PLAN_PRICES_UZS[6])} so‘m", callback_data="premium:plan:6")],
        [InlineKeyboardButton(f"💳 12 oy · {_money(PLAN_PRICES_UZS[12])} so‘m", callback_data="premium:plan:12")],
        [InlineKeyboardButton("🧪 Premium quiz", callback_data="premium:quiz"),
         InlineKeyboardButton("🔄 Holat", callback_data="premium:refresh")],
        *([[InlineKeyboardButton("📋 Kartani nusxalash", copy_text=CopyTextButton(text=PAYMENT_CARD_NUMBER))]] if PAYMENT_CARD_NUMBER else []),
        [InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu:main")],
    ])


@rate_limited("premium")
async def show_premium(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if user is None:
        return
    try:
        ensure_user(user.id, user.username, user.first_name, user.last_name)
        status = get_premium_status(user.id)
        status_text = (
            f"✅ Premium faol. Tugash sanasi: {status['expires_at']} (UTC)."
            if status["is_active"] else "ℹ️ Hozir bepul tarifdasiz."
        )
    except Exception as exc:
        logger.warning("Premium status failed (%s).", type(exc).__name__)
        status_text = "Premium holatini hozir tekshirib bo‘lmadi."
    text = (
        "💎 CYBERUSTOZ PRO\n\n"
        "🧩 Premium CTF va maxsus topshiriqlar\n"
        "🧪 Premium quizlar\n"
        "📚 Qo‘shimcha o‘quv imkoniyatlari\n\n"
        "⭐ TELEGRAM STARS TARIFLARI\n"
        f"• 7 kun — {STARS_PLANS[7]} Stars\n"
        f"• 30 kun — {STARS_PLANS[30]} Stars\n"
        f"• 90 kun — {STARS_PLANS[90]} Stars\n\n"
        "💳 Karta orqali admin tasdiqlaydigan tariflar ham mavjud:\n"
        f"• 1 oy — {_money(PLAN_PRICES_UZS[1])}\n"
        f"• 3 oy — {_money(PLAN_PRICES_UZS[3])}\n"
        f"• 6 oy — {_money(PLAN_PRICES_UZS[6])}\n"
        f"• 12 oy — {_money(PLAN_PRICES_UZS[12])}\n\n"
        f"{status_text}\n\n"
        + (f"💳 TO‘LOV KARTASI\n🏦 Bank: {PAYMENT_CARD_BANK or 'ko‘rsatilmagan'}\n"
           f"💳 Karta raqami: {PAYMENT_CARD_NUMBER}\n"
           f"👤 Karta egasi: {PAYMENT_CARD_HOLDER or 'ko‘rsatilmagan'}\n\n"
           if PAYMENT_CARD_NUMBER else "⚠️ Karta raqami sozlanmagan. Bot papkasidagi .env faylida PAYMENT_CARD_NUMBER ni to‘ldiring.\n\n")
        + "Tarifni tanlang, to‘lovni amalga oshiring va chekni yuboring. Admin tekshirib, obunani faollashtiradi. "
        "Chek tasdiqlanmaguncha Premium berilmaydi."
    )
    if query:
        await query.answer()
        await query.edit_message_text(text, reply_markup=_premium_keyboard())
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=_premium_keyboard())


@rate_limited("premium_status")
async def premium_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if user is None or message is None:
        return
    status = get_premium_status(user.id)
    if status["is_active"]:
        await message.reply_text(
            f"💎 Premium faol\n🗓 Boshlangan: {status['started_at']}\n⏳ Tugaydi: {status['expires_at']} (UTC)\n"
            f"🔐 Manba: {status['source']}"
        )
    else:
        await message.reply_text("ℹ️ Premium faol emas. Tariflar uchun /premium ni bosing.")


async def choose_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if query is None or user is None:
        return
    try:
        months = int((query.data or "").rsplit(":", 1)[1])
    except (ValueError, IndexError):
        await query.answer("Tarif noto‘g‘ri.", show_alert=True)
        return
    if months not in PLAN_PRICES_UZS:
        await query.answer("Bunday tarif mavjud emas.", show_alert=True)
        return
    if not PAYMENT_CARD_NUMBER or not ADMIN_IDS:
        await query.answer("To‘lov sozlamasi yoki admin ro‘yxati hali tayyor emas.", show_alert=True)
        await query.message.reply_text("⚠️ To‘lov vaqtincha mavjud emas. Admin .env faylida PAYMENT_CARD_NUMBER va ADMIN_IDS ni sozlashi kerak.")
        return
    context.user_data["pending_payment_plan"] = months
    text = (
        f"💳 TO‘LOV — {months} OYLIK PRO\n\n"
        f"💰 Summa: {_money(PLAN_PRICES_UZS[months])} so‘m\n"
        f"🏦 Bank: {PAYMENT_CARD_BANK or 'ko‘rsatilmagan'}\n"
        f"💳 Karta: {PAYMENT_CARD_NUMBER}\n"
        f"👤 Karta egasi: {PAYMENT_CARD_HOLDER or 'ko‘rsatilmagan'}\n\n"
        f"📌 {PAYMENT_CARD_INSTRUCTIONS}\n\n"
        "To‘lovdan keyin chekni shu chatga rasm (photo) yoki hujjat (PDF/JPG/PNG) ko‘rinishida yuboring. "
        "Admin tekshirgandan keyingina obuna faollashadi.\n\n/cancel — bekor qilish"
    )
    # Telegram Bot API copy_text button copies the configured card number with one tap.
    # The actual card details remain in .env and are never hard-coded into the project.
    payment_buttons = []
    if PAYMENT_CARD_NUMBER:
        payment_buttons.append([
            InlineKeyboardButton(
                "📋 Kartani nusxalash",
                copy_text=CopyTextButton(text=PAYMENT_CARD_NUMBER),
            )
        ])
    payment_buttons.extend([
        [InlineKeyboardButton("✅ To‘lov qilindi", callback_data="premium:paid")],
        [InlineKeyboardButton("🧾 Chek yuborish tartibi", callback_data="premium:receipt_help")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="premium:cancel")],
        [InlineKeyboardButton("⬅️ Tariflarga qaytish", callback_data="premium:refresh")],
    ])
    await query.answer()
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(payment_buttons))


async def receipt_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    await query.message.reply_text(
        "🧾 Chek yuborish tartibi\n\n"
        "1️⃣ Kartani nusxalab bank ilovangizda to‘lov qiling.\n"
        "2️⃣ To‘lov muvaffaqiyatli bo‘lganidan keyin chek yoki kvitansiyani oling.\n"
        "3️⃣ Shu chatga chekni rasm (📷) yoki PDF/JPG/PNG hujjat sifatida yuboring.\n"
        "4️⃣ Bot so‘rovni adminga yuboradi. Admin tekshirganidan keyin Premium faollashadi.\n\n"
        "⚠️ Soxta yoki boshqa to‘lovga tegishli chek yubormang."
    )


async def payment_paid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if query is None or user is None:
        return
    months = context.user_data.get("pending_payment_plan")
    if months not in PLAN_PRICES_UZS:
        await query.answer("Avval Premium tarifini tanlang.", show_alert=True)
        return
    await query.answer()
    await query.message.reply_text(
        f"🧾 CHEKNI YUBORING\n\n"
        f"Tarif: {months} oy · {_money(PLAN_PRICES_UZS[int(months)])} so‘m\n"
        "Endi to‘lov kvitansiyasini shu chatga rasm (📷) yoki PDF/JPG/PNG hujjat sifatida yuboring.\n"
        "Chek adminga avtomatik yuboriladi. Admin tekshirib tasdiqlagach Premium faollashadi.\n\n"
        "Bekor qilish: /cancel"
    )


async def cancel_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        context.user_data.pop("pending_payment_plan", None)
        await query.answer("To‘lov bekor qilindi.")
        await query.edit_message_text("To‘lov bekor qilindi. Tariflarni ko‘rish uchun /premium ni bosing.")


async def receipt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, user = update.effective_message, update.effective_user
    if message is None or user is None:
        return
    months = context.user_data.get("pending_payment_plan")
    if months not in PLAN_PRICES_UZS:
        return
    file_id, kind = None, None
    if message.photo:
        file_id, kind = message.photo[-1].file_id, "photo"
    elif message.document:
        document = message.document
        mime = (document.mime_type or "").lower()
        filename = (document.file_name or "").lower()
        allowed_extension = filename.endswith((".pdf", ".jpg", ".jpeg", ".png", ".webp"))
        allowed_mime = mime.startswith("image/") or mime == "application/pdf"
        if not (allowed_mime or (not mime and allowed_extension)):
            await message.reply_text("Chek faqat JPG, PNG, WEBP yoki PDF bo‘lishi mumkin.")
            return
        if document.file_size and document.file_size > 10 * 1024 * 1024:
            await message.reply_text("Chek fayli 10 MB dan kichik bo‘lishi kerak.")
            return
        file_id, kind = document.file_id, "document"
    if not file_id:
        return
    try:
        ensure_user(user.id, user.username, user.first_name, user.last_name)
        request_id = create_request(user.id, int(months), PLAN_PRICES_UZS[int(months)], file_id, kind)
    except ValueError as exc:
        await message.reply_text(str(exc))
        return
    except Exception as exc:
        logger.warning("Manual payment request create failed (%s).", type(exc).__name__)
        await message.reply_text("Chek so‘rovini saqlab bo‘lmadi. Keyinroq urinib ko‘ring yoki admin bilan bog‘laning.")
        return
    context.user_data.pop("pending_payment_plan", None)
    await message.reply_text(f"🧾 Chek adminga yuborildi. So‘rov raqami: #{request_id}. Tekshiruvdan so‘ng natija sizga yuboriladi.")
    review_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tasdiqlash · 1 oy", callback_data=f"payment_review:approve:{request_id}:1"),
         InlineKeyboardButton("✅ 3 oy", callback_data=f"payment_review:approve:{request_id}:3")],
        [InlineKeyboardButton("✅ 6 oy", callback_data=f"payment_review:approve:{request_id}:6"),
         InlineKeyboardButton("✅ 12 oy", callback_data=f"payment_review:approve:{request_id}:12")],
        [InlineKeyboardButton("❌ Rad etish", callback_data=f"payment_review:reject:{request_id}:0")],
    ])
    username = f"@{user.username}" if user.username else "username yo‘q"
    admin_text = (
        f"🧾 TO‘LOV CHEKI · SO‘ROV #{request_id}\n\n"
        f"👤 User ID: {user.id}\n"
        f"🔗 Username: {username}\n"
        f"📦 So‘ralgan tarif: {months} oy\n"
        f"💰 Kutilgan summa: {_money(PLAN_PRICES_UZS[int(months)])} so‘m\n"
        "Chekni tekshiring. Tasdiqlash tugmasida faqat haqiqiy to‘lovga mos muddatni tanlang."
    )
    delivered = False
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_text, reply_markup=review_keyboard)
            await context.bot.copy_message(chat_id=admin_id, from_chat_id=message.chat_id, message_id=message.message_id)
            delivered = True
        except Exception as exc:
            logger.warning("Receipt notification failed for admin (%s).", type(exc).__name__)
    if not delivered:
        logger.error("Payment request #%s created but no admin notification delivered.", request_id)
        await message.reply_text("⚠️ So‘rov saqlandi, ammo adminga xabar yetkazilmadi. Admin bilan bevosita bog‘laning.")


async def payment_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if query is None or user is None:
        return
    if user.id not in ADMIN_IDS:
        await query.answer("Faqat admin tasdiqlashi mumkin.", show_alert=True)
        return
    parts = (query.data or "").split(":")
    if len(parts) != 4:
        await query.answer("So‘rov formati noto‘g‘ri.", show_alert=True)
        return
    _, action, request_text, months_text = parts
    try:
        request_id, months = int(request_text), int(months_text)
        if action not in {"approve", "reject"}:
            raise ValueError
        result = review_request(request_id, user.id, approve=action == "approve", months=months if action == "approve" else None)
    except (ValueError, TypeError) as exc:
        await query.answer("So‘rov noto‘g‘ri.", show_alert=True)
        return
    except Exception as exc:
        logger.exception("Payment review failed (%s).", type(exc).__name__)
        await query.answer("To‘lovni ko‘rib chiqishda xato.", show_alert=True)
        return
    if not result.get("ok"):
        if result.get("reason") == "amount_mismatch":
            await query.answer("Tanlangan oylar narxi chek summasiga mos emas. To‘g‘ri tarifni tanlang.", show_alert=True)
        else:
            await query.answer("Bu chek topilmadi yoki oldin ko‘rib chiqilgan.", show_alert=True)
        return
    target_id = int(result["telegram_id"])
    if action == "approve":
        await query.answer("Premium berildi.")
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"✅ #{request_id} tasdiqlandi. {target_id} foydalanuvchiga {months} oylik ({result['days']} kun) Pro berildi.")
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎉 To‘lovingiz admin tomonidan tasdiqlandi! 💎 Pro obuna {months} oyga faollashtirildi.\n⏳ Tugash sanasi: {result['expires_at']} (UTC).\n/premium_status",
            )
        except Exception as exc:
            logger.warning("Premium approval user notification failed (%s).", type(exc).__name__)
    else:
        await query.answer("Chek rad etildi.")
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"❌ #{request_id} chek rad etildi.")
        try:
            await context.bot.send_message(chat_id=target_id, text=f"❌ To‘lov cheki #{request_id} tasdiqlanmadi. Chek/summa ma’lumotlarini tekshirib, /premium orqali qayta yuboring.")
        except Exception as exc:
            logger.warning("Payment rejection user notification failed (%s).", type(exc).__name__)
    try:
        record_admin_action(user.id, f"manual_payment_{action}", target_id, metadata={"request_id": request_id, "months": months})
    except Exception as exc:
        logger.debug("Payment review audit skipped (%s).", type(exc).__name__)



@rate_limited("stars_invoice", cooldown=5.0)
async def stars_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if query is None or user is None:
        return
    try:
        days = int((query.data or "").rsplit(":", 1)[1])
    except (ValueError, IndexError):
        await query.answer("Tarif noto‘g‘ri.", show_alert=True)
        return
    if days not in STARS_PLANS:
        await query.answer("Bunday tarif mavjud emas.", show_alert=True)
        return
    ensure_user(user.id, user.username, user.first_name, user.last_name)
    try:
        payload = _create_stars_payload(days, user.id)
    except ValueError:
        logger.error("Stars invoice cannot be created: bot token/configuration invalid.")
        await query.answer("To‘lov vaqtincha mavjud emas. Keyinroq urinib ko‘ring.", show_alert=True)
        return
    await query.answer()
    await context.bot.send_invoice(
        chat_id=user.id, title=f"CyberUstozBot Premium — {STARS_PLAN_LABELS[days]}",
        description=f"Premium kurslarga {days} kunlik kirish.", payload=payload,
        provider_token="", currency="XTR",
        prices=[LabeledPrice(label=f"Premium {STARS_PLAN_LABELS[days]}", amount=STARS_PLANS[days])],
        need_name=False, need_phone_number=False, need_email=False, need_shipping_address=False,
        is_flexible=False,
    )


async def stars_precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    if query is None:
        return
    days = _verify_stars_payload(query.invoice_payload or "", query.from_user.id)
    valid = (days is not None and query.currency == "XTR"
             and query.total_amount == STARS_PLANS[days])
    await query.answer(ok=valid, error_message=None if valid else "To‘lov ma’lumotlari noto‘g‘ri. Tarifni qaytadan tanlang.")


async def stars_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    payment = message.successful_payment if message else None
    if user is None or payment is None:
        return
    try:
        days = _verify_stars_payload(payment.invoice_payload or "", user.id)
        if (days is None or payment.currency != "XTR"
                or payment.total_amount != STARS_PLANS[days]):
            raise ValueError("payment payload/signature/amount mismatch")
        charge_id = payment.telegram_payment_charge_id
        if not charge_id:
            raise ValueError("missing Telegram charge id")
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior = conn.execute("SELECT status FROM payments WHERE provider_event_id=?", (f"telegram-stars:{charge_id}",)).fetchone()
            if prior:
                conn.rollback()
                await message.reply_text("Bu to‘lov avval qayd qilingan. Premium holatini /premium_status orqali tekshiring.")
                return
            row = conn.execute("SELECT is_premium, premium_started_at, premium_expires_at FROM users WHERE telegram_id=?", (user.id,)).fetchone()
            if row is None:
                conn.rollback()
                await message.reply_text("Foydalanuvchi topilmadi. /start yuboring va yordamga murojaat qiling.")
                return
            now = datetime.now(timezone.utc)
            old_expiry = _parse_datetime(row["premium_expires_at"])
            active = bool(row["is_premium"]) and old_expiry is not None and old_expiry > now
            base = old_expiry if active else now
            started = row["premium_started_at"] if active and row["premium_started_at"] else _utc_timestamp(now)
            expires = _utc_timestamp(base + timedelta(days=days))
            conn.execute("INSERT INTO payments(provider_event_id, telegram_id, amount_minor, currency, status) VALUES(?, ?, ?, 'XTR', 'successful')", (f"telegram-stars:{charge_id}", user.id, payment.total_amount))
            conn.execute("UPDATE users SET is_premium=1, premium_started_at=?, premium_expires_at=?, premium_source='payment' WHERE telegram_id=?", (started, expires, user.id))
            conn.commit()
        await message.reply_text(f"🎉 To‘lov muvaffaqiyatli! Premium {days} kunga faollashtirildi.\n⏳ Tugash vaqti: {expires} (UTC)\nBarcha Premium kurslar ochildi.")
    except Exception as exc:
        logger.exception("Telegram Stars payment processing failed (%s).", type(exc).__name__)
        await message.reply_text("To‘lov kelib tushdi, ammo Premium holatini yangilashda muammo bo‘ldi. To‘lov ID’sini saqlang va admin bilan bog‘laning.")


def register_premium_handlers(app) -> None:
    app.add_handler(CommandHandler("premium", show_premium))
    app.add_handler(CommandHandler("premium_status", premium_status))
    app.add_handler(CallbackQueryHandler(stars_plan_callback, pattern=r"^premium:stars:(7|30|90)$"))
    app.add_handler(PreCheckoutQueryHandler(stars_precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, stars_successful_payment))
    app.add_handler(CallbackQueryHandler(choose_plan_callback, pattern=r"^premium:plan:(1|3|6|12)$"))
    app.add_handler(CallbackQueryHandler(show_premium, pattern=r"^premium:refresh$"))
    app.add_handler(CallbackQueryHandler(cancel_payment_callback, pattern=r"^premium:cancel$"))
    app.add_handler(CallbackQueryHandler(receipt_help_callback, pattern=r"^premium:receipt_help$"))
    app.add_handler(CallbackQueryHandler(payment_paid_callback, pattern=r"^premium:paid$"))
    app.add_handler(CallbackQueryHandler(payment_review_callback, pattern=r"^payment_review:(approve|reject):\d+:(0|1|3|6|12)$"))
    app.add_handler(MessageHandler((filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, receipt_handler))
