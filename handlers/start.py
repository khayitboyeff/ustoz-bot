from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from config import ADMIN_IDS

from database.db import ensure_user, get_completed_lessons, get_leaderboard_with_user, get_user_profile_stats, get_user_settings, set_notifications_enabled
from handlers.rate_limit import rate_limited
from services.ip_service import validate_ip_address
from database.db import ensure_referral_code, register_referral, record_user_activity
from handlers.community import check_membership, show_subscription_gate
from services.i18n import t, normalize_language


_MENU_ITEMS = [
    [("📚 Kiberxavfsizlik darslari", "menu_lessons")],
    [("🧪 Testlar", "menu_quiz")],
    [("🗺 O‘quv yo‘li", "menu_learning_path")],
    [("⭐ XP va reyting", "menu_xp"), ("🎯 Kunlik vazifa", "menu_daily")],
    [("❓ Savol-javoblar", "menu_questions")],
    [("🌐 IP maʼlumoti", "menu_ip")],
    [("🔎 DNS tekshiruvi", "menu_dns")],
    [("🕵️ OSINT asoslari", "menu_osint")],
    [("🧩 CTF", "menu_ctf")],
    [("🛡 Phishing tahlili", "menu_phishing")],
    [("📜 Sertifikat", "menu_certificate")],
    [("👥 Referral", "menu_referral"), ("🔥 Streak", "menu_streak")],
    [("💎 Premium", "menu_premium")],
    [("⚙️ Sozlamalar", "menu_settings")],
    [("🆘 Yordam", "menu_help")],
]


def build_main_menu(language: str = "uz", user_id: int | None = None) -> InlineKeyboardMarkup:
    language = normalize_language(language)
    rows = []
    for row in _MENU_ITEMS:
        translated = []
        for fallback, key in row:
            label = t(language, key)
            translated.append(InlineKeyboardButton(label if label != key else fallback, callback_data=key.replace("menu_", "menu:")))
        rows.append(translated)
    profile_row = [InlineKeyboardButton("👤 Profil", callback_data="menu:profile")]
    if user_id in ADMIN_IDS:
        profile_row.append(InlineKeyboardButton("👑 Admin", callback_data="menu:admin"))
    else:
        profile_row.append(InlineKeyboardButton("👤 User", callback_data="menu:user"))
    rows.append(profile_row)
    return InlineKeyboardMarkup(rows)


def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu:main")]])


async def _send_or_edit(update: Update, text: str, reply_markup=None) -> None:
    query = update.callback_query
    if query is not None:
        await query.answer()
        await query.edit_message_text(text, reply_markup=reply_markup)
        return
    message = update.effective_message
    if message is not None:
        await message.reply_text(text, reply_markup=reply_markup)


@rate_limited("start")
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    context.user_data.pop("pending_lookup", None)
    ensure_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )
    try:
        ensure_referral_code(user.id)
        record_user_activity(user.id)
        if context.args and context.args[0].startswith("ref_"):
            created = register_referral(user.id, context.args[0][4:])
            if created:
                from services.referral_rewards import grant_available_referral_rewards
                # The inviter receives a milestone reward only once; invitee identity is attributed once.
                from database.db import get_connection
                with get_connection() as conn:
                    ref_row = conn.execute("SELECT referrer_id FROM referrals WHERE invitee_id=?", (user.id,)).fetchone()
                if ref_row:
                    referrer_id = int(ref_row["referrer_id"])
                    rewards = grant_available_referral_rewards(referrer_id)
                    for reward in rewards:
                        try:
                            await context.bot.send_message(
                                chat_id=referrer_id,
                                text=(
                                    f"🎉 Referral mukofoti! {reward['milestone']} ta taklif bosqichiga yetdingiz. "
                                    f"Bu bosqichda {reward['days']} kun qo‘shildi; referral mukofotining umumiy qiymati "
                                    f"{reward['total_days']} kun. /premium_status"
                                ),
                            )
                        except Exception:
                            pass
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Community onboarding step failed (%s).", type(exc).__name__)

    from database.db import is_subscription_required
    if is_subscription_required():
        passed, missing, error = await check_membership(context.bot, user.id)
        if not passed:
            await show_subscription_gate(update, context, missing, error)
            return

    try:
        language = normalize_language(get_user_settings(user.id).get("language"))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Language preference unavailable (%s); using Uzbek.", type(exc).__name__)
        language = "uz"
    text = f"{t(language, 'start_greeting')}\n\n{t(language, 'start_body')}"
    await _send_or_edit(update, text, reply_markup=build_main_menu(language, user.id))


@rate_limited("help")
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    language = "uz"
    if user:
        try:
            language = normalize_language(get_user_settings(user.id).get("language"))
        except Exception:
            pass
    text = f"{t(language, 'help_title')}\n\n{t(language, 'help_body')}"
    await _send_or_edit(update, text)


@rate_limited("profile")
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    try:
        stats = get_user_profile_stats(user.id)
        if stats["user"] is None:
            ensure_user(user.id, user.username, user.first_name, user.last_name)
            stats = get_user_profile_stats(user.id)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Profile query failed (%s).", type(exc).__name__)
        await _send_or_edit(update, "Profil ma’lumotlarini hozir olib bo‘lmadi. Keyinroq urinib ko‘ring.")
        return
    db_user = stats["user"]
    if db_user is None:
        ensure_user(user.id, user.username, user.first_name, user.last_name)
        stats = get_user_profile_stats(user.id)
        db_user = stats["user"]
    premium_text = "Faol" if db_user["is_premium"] else "Faol emas"
    from database.db import get_referral_stats, get_user_activity
    from database.features import list_achievements, get_activity
    activity = get_user_activity(user.id)
    try:
        bonus_activity = get_activity(user.id)
        achievements = list_achievements(user.id)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Profile reward data unavailable (%s).", type(exc).__name__)
        bonus_activity = {"bonus_points": 0}
        achievements = []
    achievement_names = {
        "first_lesson": "Birinchi dars", "course_12_lessons": "12 dars tugallandi",
        "first_quiz": "Birinchi quiz", "perfect_quiz": "Mukammal quiz", "first_ctf": "Birinchi CTF",
    }
    achievement_text = ", ".join(achievement_names.get(key, key) for key in achievements) if achievements else "hali yo‘q"
    referrals = get_referral_stats(user.id)
    real_points = int(stats.get("total_score", 0)) + int(bonus_activity.get("bonus_points", 0))
    level = 1 + real_points // 100
    text = (
        "👤 Mening profilim\n\n"
        f"🆔 Telegram ID: {db_user['telegram_id']}\n"
        f"👤 Ism: {db_user['first_name'] or 'Nomaʼlum'} {db_user.get('last_name') or ''}\n"
        f"🔗 Username: @{db_user['username'] or 'yo‘q'}\n"
        f"🗓 Ro‘yxatdan o‘tgan vaqti: {db_user['created_at']}\n"
        f"🧪 Tugallangan quizlar: {stats['quiz_count']}\n"
        f"✅ To‘g‘ri javoblar: {stats['total_correct']}/{stats['total_answers']}\n"
        f"🎯 Aniqlik: {stats['accuracy']:.1f}%\n"
        f"⭐ Jami ball: {stats['total_score']}\n"
        f"🎁 Bonus ballari: {bonus_activity.get('bonus_points', 0)}\n"
        f"🏅 Daraja: {level}\n"
        f"📚 O‘tilgan darslar: {stats['lessons_completed']}\n"
        f"🏆 Yutuqlar: {achievement_text}\n"
        f"🔥 Ketma-ket faol kunlar: {activity['streak']}\n"
        f"👥 Taklif qilgan foydalanuvchilar: {referrals['invited']}\n"
        f"💎 Premium: {premium_text}\n"
        f"⏳ Premium muddati: {db_user['premium_expires_at'] or 'yo‘q'}\n"
    )
    await _send_or_edit(update, text)


@rate_limited("leaderboard")
async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        from handlers.new_features import xp_leaderboard, xp_for_user
        rows = xp_leaderboard(10)
        if not rows:
            await _send_or_edit(update, "Hozircha reyting ma’lumotlari yo‘q.")
            return
        lines = ["🏆 CyberUstoz XP reytingi", ""]
        for place, row in enumerate(rows, 1):
            name = row.get("first_name") or (f"@{row['username']}" if row.get("username") else f"ID {row['telegram_id']}")
            lines.append(f"{place}. {name} — {row['xp']} XP · {1 + int(row['xp']) // 100}-daraja")
        user = update.effective_user
        if user and not any(int(row["telegram_id"]) == user.id for row in rows):
            own_xp = xp_for_user(user.id)
            with __import__('database.db', fromlist=['get_connection']).get_connection() as conn:
                rank_row = conn.execute("SELECT COUNT(*)+1 AS rank FROM users u WHERE ((SELECT COALESCE(SUM(q.score),0) FROM quiz_runs q WHERE q.telegram_id=u.telegram_id AND q.completed=1)*10 + (SELECT COUNT(*) FROM lesson_progress lp WHERE lp.telegram_id=u.telegram_id)*20 + (SELECT COALESCE(SUM(c.points),0) FROM ctf_solves s JOIN ctf_challenges c ON c.id=s.challenge_id WHERE s.telegram_id=u.telegram_id) + COALESCE((SELECT a.bonus_points FROM user_activity a WHERE a.telegram_id=u.telegram_id),0)) > ?", (own_xp,)).fetchone()
            lines.extend(["", f"Sizning o‘rningiz: {rank_row['rank']} · {own_xp} XP"])
        await _send_or_edit(update, "\n".join(lines))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("XP leaderboard failed (%s).", type(exc).__name__)
        await _send_or_edit(update, "Reytingni hozir olib bo‘lmadi. Keyinroq urinib ko‘ring.")


@rate_limited("settings")
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        await _send_or_edit(update, "Foydalanuvchi sozlamalarini aniqlab bo‘lmadi.")
        return
    try:
        settings = get_user_settings(user.id)
        language = normalize_language(settings.get("language"))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Settings query failed (%s).", type(exc).__name__)
        await _send_or_edit(update, "Sozlamalarni hozir olib bo‘lmadi. Keyinroq urinib ko‘ring.")
        return
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    status = t(language, "settings_on") if settings["notifications_enabled"] else t(language, "settings_off")
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇺🇿 O‘zbekcha", callback_data="settings:language:uz"),
         InlineKeyboardButton("🇷🇺 Русский", callback_data="settings:language:ru"),
         InlineKeyboardButton("🇬🇧 English", callback_data="settings:language:en")],
        [InlineKeyboardButton(t(language, "settings_toggle_off") if settings["notifications_enabled"] else t(language, "settings_toggle_on"), callback_data="settings:notifications:toggle")],
        [InlineKeyboardButton(t(language, "settings_profile"), callback_data="menu:profile"), InlineKeyboardButton(t(language, "settings_help"), callback_data="menu:help")],
        [InlineKeyboardButton(t(language, "menu_main"), callback_data="menu:main")],
    ])
    text = f"{t(language, 'settings_title')}\n\n{t(language, 'settings_language')}: {t(language, 'lang_name')}\n{t(language, 'settings_notifications')}: {status}\n\n{t(language, 'settings_choose_language')}"
    await _send_or_edit(update, text, reply_markup=markup)


@rate_limited("settings_callback", 0.5)
async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    try:
        if (query.data or "").startswith("settings:language:"):
            language = (query.data or "").rsplit(":", 1)[-1]
            if language not in {"uz", "ru", "en"}:
                await query.answer("Til tanlovi noto‘g‘ri.", show_alert=True)
                return
            from database.db import set_user_language
            set_user_language(user.id, language)
        elif query.data == "settings:notifications:toggle":
            current = get_user_settings(user.id)
            set_notifications_enabled(user.id, not bool(current["notifications_enabled"]))
        settings = get_user_settings(user.id)
        language = normalize_language(settings.get("language"))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Settings update failed (%s).", type(exc).__name__)
        await query.answer("Sozlamani saqlab bo‘lmadi. Keyinroq urinib ko‘ring.", show_alert=True)
        return
    await query.answer(t(language, "settings_saved"))
    await query.edit_message_text(
        f"{t(language, 'settings_title')}\n\n{t(language, 'settings_language')}: {t(language, 'lang_name')}\n"
        f"{t(language, 'settings_notifications')}: {t(language, 'settings_on') if settings['notifications_enabled'] else t(language, 'settings_off')}\n\n"
        f"{t(language, 'settings_choose_language')}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🇺🇿 O‘zbekcha", callback_data="settings:language:uz"),
             InlineKeyboardButton("🇷🇺 Русский", callback_data="settings:language:ru"),
             InlineKeyboardButton("🇬🇧 English", callback_data="settings:language:en")],
            [InlineKeyboardButton(t(language, "settings_toggle_off") if settings["notifications_enabled"] else t(language, "settings_toggle_on"), callback_data="settings:notifications:toggle")],
            [InlineKeyboardButton(t(language, "menu_main"), callback_data="menu:main")],
        ]),
    )


@rate_limited("menu", 0.5)
async def handle_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""

    action = data.replace("menu:", "")
    if action not in {"ip", "dns"}:
        context.user_data.pop("pending_lookup", None)
    if action not in {"phishing", "certificate"}:
        context.user_data.pop("pending_advanced", None)
        context.user_data.pop("pending_ctf_id", None)
    if action == "main":
        user = update.effective_user
        language = "uz"
        if user:
            try:
                language = normalize_language(get_user_settings(user.id).get("language"))
            except Exception:
                pass
        text = f"{t(language, 'start_greeting')}\n\n{t(language, 'start_body')}"
        await query.answer()
        await query.edit_message_text(text, reply_markup=build_main_menu(language, user.id if user else None))
        return
    if action == "lessons":
        from handlers.learning import show_lessons
        await show_lessons(update, context)
    elif action == "quiz":
        from handlers.quiz import start_quiz
        await start_quiz(update, context)
    elif action == "questions":
        from handlers.content_admin import questions_command
        await query.answer()
        await questions_command(update, context)
    elif action == "ip":
        from handlers.tools import ask_ip_address
        await ask_ip_address(update, context)
    elif action == "dns":
        from handlers.tools import ask_dns_domain
        await ask_dns_domain(update, context)
    elif action == "osint":
        from handlers.tools import show_osint_menu
        await show_osint_menu(update, context)
    elif action == "premium":
        from handlers.premium import show_premium
        await show_premium(update, context)
    elif action == "profile":
        await profile_command(update, context)
    elif action == "admin":
        from handlers.content_admin import admin_content_command
        user = update.effective_user
        if user is None or user.id not in ADMIN_IDS:
            await query.answer("⛔ Bu tugma faqat admin uchun.", show_alert=True)
            return
        await query.answer()
        await admin_content_command(update, context)
    elif action == "user":
        user_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 Darsliklar", callback_data="menu:lessons"), InlineKeyboardButton("🧪 Testlar", callback_data="menu:quiz")],
            [InlineKeyboardButton("💎 Premium", callback_data="menu:premium"), InlineKeyboardButton("👤 Profil", callback_data="menu:profile")],
            [InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu:main")],
        ])
        await query.answer()
        await query.edit_message_text("👤 Foydalanuvchi bo‘limi\n\nDarsliklarni o‘rganing, test ishlang va natijalaringizni kuzating.", reply_markup=user_markup)
    elif action == "settings":
        await settings_command(update, context)
    elif action == "help":
        await help_command(update, context)
    elif action == "phishing":
        context.user_data["pending_advanced"] = "phishing"
        await query.answer()
        await query.edit_message_text(
            "🛡 Shubhali xabar yoki URL matnini yuboring. Havola ochilmaydi. /cancel — bekor qilish."
        )
    elif action == "ctf":
        from handlers.advanced import ctf_command
        await query.answer()
        await ctf_command(update, context)
    elif action == "certificate":
        context.user_data["pending_advanced"] = "certificate"
        await query.answer()
        await query.edit_message_text(
            "📜 Sertifikat yaratish uchun kurs talablarini bajaring, keyin sertifikatda ko‘rsatiladigan ismingizni yuboring. /cancel — bekor qilish."
        )
    elif action == "referral":
        from handlers.community import referral_command
        await query.answer()
        await referral_command(update, context)
    elif action == "streak":
        from handlers.community import streak_command
        await query.answer()
        await streak_command(update, context)
    elif action == "learning_path":
        from handlers.new_features import learning_path_command
        await query.answer()
        await learning_path_command(update, context)
    elif action == "xp":
        from handlers.new_features import xp_command
        await query.answer()
        await xp_command(update, context)
    elif action == "daily":
        from handlers.community import daily_command
        await query.answer()
        await daily_command(update, context)
    else:
        await query.answer("Noma’lum bo‘lim tanlandi.")

@rate_limited("text_message", 0.5)
async def handle_unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    text = (message.text or "").strip()
    if not text:
        return
    if text.lower().startswith("/"):
        await message.reply_text(t(normalize_language(get_user_settings(update.effective_user.id).get("language")) if update.effective_user else "uz", "unknown_command"))
        return

    from handlers.content_admin import handle_content_admin_text
    if await handle_content_admin_text(update, context):
        return

    from handlers.advanced import handle_advanced_text
    if await handle_advanced_text(update, context):
        return

    pending_lookup = context.user_data.get("pending_lookup")
    if pending_lookup == "osint":
        context.user_data.pop("pending_lookup", None)
        from handlers.tools import handle_osint_lookup_message
        await handle_osint_lookup_message(update, context)
        return
    if pending_lookup == "ip":
        from handlers.tools import handle_ip_lookup_message
        await handle_ip_lookup_message(update, context)
        return
    if pending_lookup == "dns":
        from handlers.tools import handle_dns_lookup_message
        await handle_dns_lookup_message(update, context)
        return

    if ":" in text or validate_ip_address(text) or (text.count(".") >= 3 and all(part.isdigit() for part in text.split("."))):
        from handlers.tools import handle_ip_lookup_message
        await handle_ip_lookup_message(update, context)
        return

    if "." in text and " " not in text:
        from handlers.tools import handle_dns_lookup_message
        await handle_dns_lookup_message(update, context)
        return

    if "/" in text or "@" in text:
        from handlers.tools import handle_osint_lookup_message
        await handle_osint_lookup_message(update, context)
        return

    await message.reply_text(t(normalize_language(get_user_settings(update.effective_user.id).get("language")) if update.effective_user else "uz", "unknown_text"))


def register_start_handlers(app) -> None:
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CallbackQueryHandler(handle_main_menu_callback, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern=r"^settings:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown_text))
