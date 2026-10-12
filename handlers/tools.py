from __future__ import annotations

import asyncio
import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from services.dns_service import lookup_dns_records_async, validate_domain_name
from services.ip_service import get_ip_details, validate_ip_address
from services.osint_service import check_public_username, safe_domain_research
from handlers.rate_limit import consume_rate_limit, rate_limited

logger = logging.getLogger(__name__)
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _safe_display(value: object, max_length: int = 120) -> str:
    return CONTROL_CHARS.sub(" ", str(value)).strip()[:max_length]


async def _ip_result_text(value: str) -> str:
    if not value:
        return "IP manzil kiritilmadi."
    if len(value) > 45 or not validate_ip_address(value):
        return "❌ IP manzil noto‘g‘ri. IPv4 yoki IPv6 manzil kiriting."
    try:
        details = await asyncio.to_thread(get_ip_details, value)
    except ValueError:
        return "⚠️ Ushbu IP manzilni tekshirib bo‘lmadi."
    except Exception as exc:
        logger.warning("IP lookup failed (%s).", type(exc).__name__)
        return "⚠️ IP ma’lumotini hozir olib bo‘lmadi. Keyinroq urinib ko‘ring."
    if details.get("status") == "error":
        return details.get("message", "IP ma’lumoti olinmadi.")

    return (
        "📍 IP ma’lumoti\n\n"
        f"IP: {_safe_display(details.get('ip', value), 45)}\n"
        f"Mamlakat: {_safe_display(details.get('country') or 'mavjud emas')}\n"
        f"Viloyat / region: {_safe_display(details.get('region') or 'mavjud emas')}\n"
        f"Shahar: {_safe_display(details.get('city') or 'mavjud emas')}\n"
        f"Provayder: {_safe_display(details.get('provider') or 'mavjud emas')}\n"
        f"Tizim: {_safe_display(details.get('type', 'mavjud emas'))}\n"
    )


async def _dns_result_text(value: str) -> str:
    if not value:
        return "Domen nomi kiritilmadi."
    if len(value) > 254:
        return "❌ Domen nomi juda uzun. 254 belgidan oshmasligi kerak."
    if not validate_domain_name(value):
        return "❌ Noto‘g‘ri domen formati. Masalan: example.com"
    try:
        result = await lookup_dns_records_async(value, timeout=5.0)
    except Exception as exc:
        logger.warning("DNS lookup failed (%s).", type(exc).__name__)
        return "⚠️ DNS tekshiruvini hozir bajarib bo‘lmadi. Keyinroq urinib ko‘ring."

    lines = [f"🔎 DNS natijalari: {_safe_display(value, 253)}"]
    for field in ("A", "AAAA", "MX", "NS"):
        values = result.get(field, [])
        safe_values = [_safe_display(item, 100) for item in values[:4]]
        lines.append(f"{field}: {', '.join(safe_values) if safe_values else 'topilmadi'}")
    if result.get("_errors"):
        lines.append("Ayrim DNS yozuvlarini tekshirib bo‘lmadi; yuqoridagi mavjud natijalar ko‘rsatildi.")
    return "\n".join(lines)


@rate_limited("ip_command")
async def ask_ip_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    value = " ".join(getattr(context, "args", None) or []).strip()
    message = update.effective_message
    if value and message is not None:
        context.user_data.pop("pending_lookup", None)
        if update.effective_user and consume_rate_limit(update.effective_user.id, "lookup_ip", 8):
            await message.reply_text("IP tekshiruvi limiti: biroz kutib qayta urinib ko‘ring.")
            return
        await message.reply_text(await _ip_result_text(value))
        return
    context.user_data["pending_lookup"] = "ip"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="menu:main")],
        [InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu:main")],
    ])
    if query is not None:
        await query.answer()
        await query.edit_message_text("🌐 IPv4 yoki IPv6 manzilni yuboring. Masalan: 8.8.8.8", reply_markup=keyboard)
    else:
        if message is not None:
            await message.reply_text("🌐 IPv4 yoki IPv6 manzilni yuboring. Masalan: 8.8.8.8", reply_markup=keyboard)


async def handle_ip_lookup_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    if update.effective_user and consume_rate_limit(update.effective_user.id, "lookup_ip", 8):
        await message.reply_text("IP tekshiruvi limiti: biroz kutib qayta urinib ko‘ring.")
        return
    context.user_data.pop("pending_lookup", None)
    await message.reply_text(await _ip_result_text((message.text or "").strip()))


@rate_limited("dns_command")
async def ask_dns_domain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    value = " ".join(getattr(context, "args", None) or []).strip()
    message = update.effective_message
    if value and message is not None:
        context.user_data.pop("pending_lookup", None)
        if update.effective_user and consume_rate_limit(update.effective_user.id, "lookup_dns", 8):
            await message.reply_text("DNS tekshiruvi limiti: biroz kutib qayta urinib ko‘ring.")
            return
        await message.reply_text(await _dns_result_text(value))
        return
    context.user_data["pending_lookup"] = "dns"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="menu:main")],
        [InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu:main")],
    ])
    if query is not None:
        await query.answer()
        await query.edit_message_text("🔎 Domen nomini yuboring. Masalan: example.com", reply_markup=keyboard)
    else:
        if message is not None:
            await message.reply_text("🔎 Domen nomini yuboring. Masalan: example.com", reply_markup=keyboard)


async def handle_dns_lookup_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    if update.effective_user and consume_rate_limit(update.effective_user.id, "lookup_dns", 8):
        await message.reply_text("DNS tekshiruvi limiti: biroz kutib qayta urinib ko‘ring.")
        return
    context.user_data.pop("pending_lookup", None)
    await message.reply_text(await _dns_result_text((message.text or "").strip()))


@rate_limited("osint_menu", 2)
async def show_osint_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Domen tekshiruvi", callback_data="osint:domain")],
        [InlineKeyboardButton("👤 Username tekshiruvi", callback_data="osint:user")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="menu:main")],
        [InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu:main")],
    ])
    if query is not None:
        await query.answer()
        await query.edit_message_text("🕵️ OSINT asoslari. Quyidagilardan birini tanlang:", reply_markup=keyboard)
    else:
        await update.message.reply_text("🕵️ OSINT asoslari. Quyidagilardan birini tanlang:", reply_markup=keyboard)


@rate_limited("osint_lookup", 10)
async def handle_osint_lookup_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    value = (message.text or "").strip()
    if not value:
        await message.reply_text("Domen yoki username kiritilmadi.")
        return

    if "." in value and " " not in value:
        if len(value) > 253 or not validate_domain_name(value):
            await message.reply_text("❌ Noto‘g‘ri domen formati. Masalan: example.com")
            return
        domain_info = safe_domain_research(value)
        text = "🌐 Domen bo‘yicha xavfsiz OSINT ko‘rsatmalar:\n\n"
        text += f"Domen: {domain_info['domain']}\n"
        text += f"WHOIS ma’lumoti: {domain_info['whois']}\n"
        text += f"DNS: {domain_info['dns']}\n"
        text += f"Sahifa/tegishli adres: {domain_info['website']}\n"
        text += "\nQonuniy ma’lumotlar uchun rasmiy hujjatlar va domen ro‘yxatlarini tekshiring."
        await message.reply_text(text)
        return

    if value.startswith("@"):
        value = value[1:]
    if len(value) > 50:
        await message.reply_text("Username 50 belgidan oshmasligi kerak.")
        return
    if update.effective_user and consume_rate_limit(update.effective_user.id, "lookup_osint", 10):
        await message.reply_text("OSINT tekshiruvi limiti: biroz kutib qayta urinib ko‘ring.")
        return
    results = await asyncio.to_thread(check_public_username, value)
    if not results:
        await message.reply_text("Username bo‘yicha tekshiruv natijasi topilmadi.")
        return

    lines = [f"👤 Username: {_safe_display(value, 50)}"]
    for item in results[:3]:
        lines.append(f"• {item['platform']}: {item['status']}\n  {item['url']}")
    await message.reply_text("\n".join(lines))


@rate_limited("osint_callback", 0.5)
async def handle_osint_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    data = (query.data or "").strip()
    if data == "osint:domain":
        context.user_data["pending_lookup"] = "osint"
        await query.answer()
        await query.edit_message_text(
            "🌐 Domenni kiriting. Masalan: example.com\n\n"
            "Bu ko‘rsatma faqat ochiq ma’lumotlar va rasmiy domen ma’lumotlarini tekshirishga qaratilgan."
        )
    elif data == "osint:user":
        context.user_data["pending_lookup"] = "osint"
        await query.answer()
        await query.edit_message_text(
            "👤 Username kiriting. Masalan: @githubuser\n\n"
            "Faqat ommaviy, ochiq sahifalar tekshiriladi. Maxfiy yoki login talab qiladigan sahifalar tekshirilmaydi."
        )
    else:
        await query.answer("Bu OSINT bo‘limi tanlanmadi.")


def register_tools_handlers(app) -> None:
    app.add_handler(CommandHandler("ip", ask_ip_address))
    app.add_handler(CommandHandler("dns", ask_dns_domain))
    app.add_handler(CommandHandler("osint", show_osint_menu))
    app.add_handler(CallbackQueryHandler(handle_osint_callback, pattern=r"^osint:"))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^(?:\d{1,3}\.){3}\d{1,3}$|^(?=.*:)[0-9A-Fa-f:.]+$"), handle_ip_lookup_message))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"), handle_dns_lookup_message))
