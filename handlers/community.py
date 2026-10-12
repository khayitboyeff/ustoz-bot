from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, CommandHandler, ContextTypes

from config import ADMIN_IDS
from database.features import get_daily_task_progress, list_achievements, get_activity
from database.db import (
    add_required_channel, ensure_referral_code, get_active_required_channels,
    get_referral_stats, get_user_activity, is_subscription_required,
    record_user_activity, register_referral, remove_required_channel,
    set_subscription_required,
)

logger = logging.getLogger(__name__)


def is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in ADMIN_IDS


async def check_membership(bot, user_id: int) -> tuple[bool, list[dict], bool]:
    """Returns (is_member, missing_channels, check_error). Fails closed on API errors."""
    channels = get_active_required_channels()
    if not is_subscription_required():
        return True, [], False
    if not channels:
        return False, [], True
    missing = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel["chat_id"], user_id=user_id)
            status = getattr(member, "status", "")
            is_member = status in {"member", "administrator", "creator"} or (
                status == "restricted" and bool(getattr(member, "is_member", False))
            )
            if not is_member:
                missing.append(channel)
        except TelegramError as exc:
            logger.warning("Subscription check failed for configured channel (%s).", type(exc).__name__)
            return False, channels, True
    return not missing, missing, False


def subscription_markup(channels: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        link = ch.get("invite_link") or (f"https://t.me/{ch['username'].lstrip('@')}" if ch.get("username") else None)
        if link:
            rows.append([InlineKeyboardButton(f"📢 {ch.get('title') or ch.get('username') or ch['chat_id']}", url=link)])
    rows.append([InlineKeyboardButton("✅ Obunani tekshirish", callback_data="subscription:check")])
    return InlineKeyboardMarkup(rows)


async def show_subscription_gate(update: Update, context: ContextTypes.DEFAULT_TYPE, channels: list[dict] | None = None, error: bool = False) -> None:
    message = update.effective_message
    query = update.callback_query
    channels = channels if channels is not None else get_active_required_channels()
    if error:
        text = ("⚠️ Obunani tekshirishning imkoni bo‘lmadi. Bot kanalga qo‘shilganini va "
                "kanal a’zoligini tekshirish huquqi borligini admin tekshirsin. Hozircha kirish ochilmadi.")
    elif not channels:
        text = "⚠️ Majburiy obuna yoqilgan, lekin kanal sozlanmagan. Administratorga murojaat qiling."
    else:
        text = "🔒 Botdan foydalanish uchun quyidagi kanallarga obuna bo‘ling, so‘ng tekshirish tugmasini bosing."
    markup = subscription_markup(channels)
    if query:
        await query.answer()
        try:
            await query.edit_message_text(text, reply_markup=markup)
        except TelegramError:
            if message:
                await message.reply_text(text, reply_markup=markup)
    elif message:
        await message.reply_text(text, reply_markup=markup)


async def subscription_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or is_admin(user.id) or not is_subscription_required():
        return
    # Keep onboarding, help, cancellation and subscription-check reachable.
    message = update.effective_message
    text = (message.text or "") if message else ""
    command = text.split(maxsplit=1)[0].split("@", 1)[0].lower() if text.startswith("/") else ""
    query = update.callback_query
    callback = query.data if query else ""
    allowed_commands = {"/start", "/help", "/cancel", "/check_subscription"}
    if command in allowed_commands or callback == "subscription:check" or callback.startswith("subscription:"):
        return
    passed, missing, error = await check_membership(context.bot, user.id)
    if not passed:
        await show_subscription_gate(update, context, missing, error)
        raise ApplicationHandlerStop


async def subscription_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    passed, missing, error = await check_membership(context.bot, user.id)
    if not passed:
        await show_subscription_gate(update, context, missing, error)
        return
    await query.answer("Obuna tasdiqlandi.", show_alert=False)
    try:
        await query.edit_message_text(
            "✅ Obuna tasdiqlandi. Endi botdan foydalanishingiz mumkin.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu:main")]]),
        )
    except TelegramError:
        pass


async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    try:
        code = ensure_referral_code(user.id)
        stats = get_referral_stats(user.id)
        me = await context.bot.get_me()
        link = f"https://t.me/{me.username}?start=ref_{code}"
    except Exception as exc:
        logger.warning("Referral info unavailable (%s).", type(exc).__name__)
        await message.reply_text("Referral ma’lumotini hozir olib bo‘lmadi. /start ni qayta bosing.")
        return
    await message.reply_text(
        "👥 REFERRAL DASTURI\n\n"
        f"👤 Taklif qilgan foydalanuvchilar: {stats['invited']}\n"
        f"🎁 Olingan mukofot bosqichlari: {stats['bonuses_granted']}\n"
        f"💎 Referral orqali berilgan kunlar: {stats.get('reward_days', 0)}\n\n"
        "🏅 15 ta taklif = 1 oy bepul Pro\n"
        "🏆 30 ta taklif = jami 3 oy bepul Pro\n"
        "Har bir bosqich faqat bir marta beriladi. Taklif qilingan odam botni /start orqali ochishi kerak.\n\n"
        "🔗 Shaxsiy taklif havolangiz:\n" + link
    )


async def streak_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    try:
        activity = record_user_activity(user.id, datetime.now(timezone.utc).date().isoformat())
    except Exception as exc:
        logger.warning("Activity tracking failed (%s).", type(exc).__name__)
        await message.reply_text("Faollik statistikasini hozir saqlab bo‘lmadi.")
        return
    await message.reply_text(
        "🔥 O‘rganish davomiyligi\n\n"
        f"Ketma-ket faol kunlar: {activity['streak']}\n"
        f"Jami faol kunlar: {activity['total_active_days']}\n"
        "Kuniga bir marta hisoblanadi."
    )


async def channel_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    if not is_admin(user.id):
        await message.reply_text("⚠️ Sizga admin huquqi berilmagan.")
        return
    args = context.args
    if not args or args[0].lower() == "list":
        channels = get_active_required_channels()
        state = "yoqilgan" if is_subscription_required() else "o‘chirilgan"
        lines = [f"Majburiy obuna: {state}", "Kanallar:"]
        lines.extend(f"• {ch.get('title') or ch.get('username') or ch['chat_id']} ({ch['chat_id']})" for ch in channels)
        lines.append("\nQo‘shish: /channel_add @username https://t.me/+invite (taklif havolasi ixtiyoriy)")
        lines.append("O‘chirish: /channel_remove @username")
        lines.append("Holat: /subscription on yoki /subscription off")
        await message.reply_text("\n".join(lines))
        return
    action = args[0].lower()
    if action == "add":
        if len(args) < 2 or len(args) > 3:
            await message.reply_text("Format: /channel_add @username [https://t.me/invite]")
            return
        identifier = args[1].strip()
        username = identifier.lstrip("@") if identifier.startswith("@") else None
        invite = args[2] if len(args) == 3 else (f"https://t.me/{username}" if username else None)
        try:
            chat = await context.bot.get_chat(identifier)
            add_required_channel(str(chat.id), username or getattr(chat, "username", None), invite, getattr(chat, "title", None))
        except (TelegramError, ValueError) as exc:
            logger.warning("Channel registration failed (%s).", type(exc).__name__)
            await message.reply_text("Kanal qo‘shilmadi. Bot kanalni ko‘ra olishini, ID/username to‘g‘riligini va taklif havolasini tekshiring.")
            return
        await message.reply_text("✅ Kanal ro‘yxatga qo‘shildi. A’zolikni tekshirish uchun botni kanalga administrator qilib qo‘shing.")
        return
    if action == "remove":
        if len(args) != 2:
            await message.reply_text("Format: /channel_remove @username")
            return
        removed = remove_required_channel(args[1])
        await message.reply_text("✅ Kanal o‘chirildi." if removed else "Bunday kanal topilmadi.")
        return
    await message.reply_text("Noma’lum amal. /channel list, /channel add yoki /channel remove ishlating.")


async def subscription_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    if not is_admin(user.id):
        await message.reply_text("⚠️ Sizga admin huquqi berilmagan.")
        return
    if len(context.args) != 1 or context.args[0].lower() not in {"on", "off"}:
        await message.reply_text("Format: /subscription on|off")
        return
    set_subscription_required(context.args[0].lower() == "on")
    await message.reply_text("Majburiy obuna yoqildi." if context.args[0].lower() == "on" else "Majburiy obuna o‘chirildi.")


async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    try:
        progress = get_daily_task_progress(user.id)
        activity = get_activity(user.id)
    except Exception as exc:
        logger.warning("Daily progress unavailable (%s).", type(exc).__name__)
        await message.reply_text("Kunlik vazifalarni hozir olib bo‘lmadi.")
        return
    done = set(progress["done"])
    lines = ["🎯 BUGUNGI VAZIFALAR", ""]
    for key, label in progress["tasks"].items():
        lines.append(f"{'✅' if key in done else '⬜'} {label}")
    lines.extend(["", f"Kunlik bonus ballari: {activity.get('bonus_points', 0)}", f"Streak: {activity.get('streak', 0)} kun", "Vazifa bonusi har tur uchun bir kunda faqat bir marta beriladi."])
    await message.reply_text("\n".join(lines))


def register_community_handlers(app) -> None:
    app.add_handler(CommandHandler("referral", referral_command))
    app.add_handler(CommandHandler("streak", streak_command))
    app.add_handler(CommandHandler("daily", daily_command))
    app.add_handler(CommandHandler("channel", channel_admin_command))
    app.add_handler(CommandHandler("channel_add", lambda u, c: channel_admin_command(u, _AdminContext(c, ["add", *c.args]))))
    app.add_handler(CommandHandler("channel_remove", lambda u, c: channel_admin_command(u, _AdminContext(c, ["remove", *c.args]))))
    app.add_handler(CommandHandler("subscription", subscription_admin_command))
    app.add_handler(CallbackQueryHandler(subscription_check_callback, pattern=r"^subscription:check$"))


class _AdminContext:
    """Minimal argument adapter for legacy command aliases."""
    def __init__(self, context, args):
        self._context = context
        self.args = args
        self.bot = context.bot
