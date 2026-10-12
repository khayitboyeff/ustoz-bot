from __future__ import annotations

SUPPORTED_LANGUAGES = ("uz", "ru", "en")
DEFAULT_LANGUAGE = "uz"

_MESSAGES = {
    "uz": {
        "welcome": (
            "CyberUstozBot’ga xush kelibsiz!\n\n"
            "Bu yerda kiberxavfsizlikni noldan boshlab o‘rganishingiz, bilimlaringizni test orqali "
            "tekshirishingiz va natijalaringizni kuzatishingiz mumkin.\n\n"
            "Boshlash uchun kerakli bo‘limni tanlang."
        ),
        "lang_name": "O‘zbekcha",
        "choose_language": "Tilni tanlang / Choose language / Выберите язык",
        "subscription_needed": "Davom etish uchun quyidagi kanallarga obuna bo‘ling, so‘ng tekshirishni bosing.",
        "subscription_ok": "Obuna tasdiqlandi. Asosiy menyu ochildi.",
        "subscription_fail": "Hali barcha kanallarga obuna emassiz.",
        "subscription_error": "Obunani tekshirib bo‘lmadi. Bot kanalda admin bo‘lishi kerak. Avtomatik ruxsat berilmaydi.",
        "phishing_disclaimer": "Bu natija taxminiy tahlil. U 100% xavfsiz yoki aniq zararli ekanini kafolatlamaydi.",
        "menu_lessons": "📚 Kiberxavfsizlik darslari",
        "menu_quiz": "🧪 Testlar",
        "menu_ip": "🌐 IP maʼlumoti",
        "menu_dns": "🔎 DNS tekshiruvi",
        "menu_osint": "🕵️ OSINT asoslari",
        "menu_ctf": "🧩 CTF",
        "menu_phishing": "🛡 Phishing tahlili",
        "menu_certificate": "📜 Sertifikat",
        "menu_referral": "👥 Referral",
        "menu_streak": "🔥 Streak",
        "menu_premium": "💎 Premium",
        "menu_profile": "👤 Mening profilim",
        "menu_settings": "⚙️ Sozlamalar",
        "menu_help": "🆘 Yordam",
        "menu_main": "🏠 Asosiy menyu",
        "start_greeting": "Salom! 👋",
        "start_body": "CyberUstozBot’ga xush kelibsiz!\n\nBu yerda kiberxavfsizlikni noldan o‘rganing, testlar bilan bilimingizni tekshiring va natijalaringizni kuzating.\n\nBoshlash uchun bo‘limni tanlang:",
        "settings_title": "⚙️ Sozlamalar",
        "settings_language": "Til",
        "settings_notifications": "Bildirishnoma afzalligi",
        "settings_on": "yoqilgan",
        "settings_off": "o‘chirilgan",
        "settings_choose_language": "Interfeys tilini tanlang:",
        "settings_saved": "Til saqlandi.",
        "settings_toggle_on": "Bildirishnomani yoqish",
        "settings_toggle_off": "Bildirishnomani o‘chirish",
        "settings_profile": "👤 Profil",
        "settings_help": "🆘 Yordam",
        "help_title": "🆘 Yordam",
        "help_body": "Asosiy buyruqlar:\n/start — bosh menyu\n/help — yordam\n/profile — profil va statistika\n/leaderboard — natijalar reytingi\n/lessons — darslar\n/quiz — test\n/ip — IP tekshiruvi\n/dns — DNS tekshiruvi\n/osint — OSINT asoslari\n/premium — Premium tarif\n/ctf — CTF topshiriqlari\n/phishing — shubhali matn tahlili\n/certificate — sertifikat\n/settings — til va sozlamalar\n/referral — taklif havolasi\n/daily — kunlik vazifa\n/streak — o‘rganish ketma-ketligi\n/ctf_progress — CTF natijalari\n/cancel — joriy amalni bekor qilish",
        "unknown_command": "Bu buyruq tan olinmadi. /help ni ishlating.",
        "unknown_text": "Bo‘lim tanlash yoki yordam uchun /help buyrug‘idan foydalaning.",
    },
    "ru": {
        "welcome": (
            "Добро пожаловать в CyberUstozBot!\n\n"
            "Здесь можно изучать кибербезопасность с нуля, проверять знания тестами и следить за прогрессом.\n\n"
            "Выберите нужный раздел."
        ),
        "lang_name": "Русский",
        "choose_language": "Tilni tanlang / Choose language / Выберите язык",
        "subscription_needed": "Чтобы продолжить, подпишитесь на каналы и нажмите проверку.",
        "subscription_ok": "Подписка подтверждена. Главное меню открыто.",
        "subscription_fail": "Вы ещё не подписаны на все каналы.",
        "subscription_error": "Не удалось проверить подписку. Бот должен быть админом канала. Доступ автоматически не выдаётся.",
        "phishing_disclaimer": "Это предварительный анализ, а не гарантия безопасности.",
        "menu_lessons": "📚 Уроки кибербезопасности",
        "menu_quiz": "🧪 Тесты",
        "menu_ip": "🌐 Данные IP",
        "menu_dns": "🔎 Проверка DNS",
        "menu_osint": "🕵️ Основы OSINT",
        "menu_ctf": "🧩 CTF",
        "menu_phishing": "🛡 Анализ фишинга",
        "menu_certificate": "📜 Сертификат",
        "menu_referral": "👥 Рефералы",
        "menu_streak": "🔥 Серия дней",
        "menu_premium": "💎 Premium",
        "menu_profile": "👤 Мой профиль",
        "menu_settings": "⚙️ Настройки",
        "menu_help": "🆘 Помощь",
        "menu_main": "🏠 Главное меню",
        "start_greeting": "Здравствуйте! 👋",
        "start_body": "Добро пожаловать в CyberUstozBot!\n\nИзучайте кибербезопасность с нуля, проверяйте знания тестами и следите за прогрессом.\n\nВыберите раздел:",
        "settings_title": "⚙️ Настройки",
        "settings_language": "Язык",
        "settings_notifications": "Уведомления",
        "settings_on": "включены",
        "settings_off": "выключены",
        "settings_choose_language": "Выберите язык интерфейса:",
        "settings_saved": "Язык сохранён.",
        "settings_toggle_on": "Включить уведомления",
        "settings_toggle_off": "Выключить уведомления",
        "settings_profile": "👤 Профиль",
        "settings_help": "🆘 Помощь",
        "help_title": "🆘 Помощь",
        "help_body": "Основные команды:\n/start — главное меню\n/help — помощь\n/profile — профиль и статистика\n/leaderboard — рейтинг результатов\n/lessons — уроки\n/quiz — тест\n/ip — проверка IP\n/dns — проверка DNS\n/osint — основы OSINT\n/premium — тариф Premium\n/ctf — задания CTF\n/phishing — анализ подозрительного текста\n/certificate — сертификат\n/settings — язык и настройки\n/referral — реферальная ссылка\n/daily — ежедневное задание\n/streak — серия обучения\n/ctf_progress — результаты CTF\n/cancel — отменить действие",
        "unknown_command": "Неизвестная команда. Используйте /help.",
        "unknown_text": "Выберите раздел в меню или используйте /help.",
    },
    "en": {
        "welcome": (
            "Welcome to CyberUstozBot!\n\n"
            "Learn cybersecurity from scratch, check your knowledge with quizzes, and track your progress.\n\n"
            "Choose a section to begin."
        ),
        "lang_name": "English",
        "choose_language": "Tilni tanlang / Choose language / Выберите язык",
        "subscription_needed": "Subscribe to the required channels, then tap the check button.",
        "subscription_ok": "Subscription confirmed. Main menu unlocked.",
        "subscription_fail": "You are not subscribed to every required channel yet.",
        "subscription_error": "Subscription could not be verified. The bot must be a channel admin. Access is not granted automatically.",
        "phishing_disclaimer": "This is a heuristic analysis, not a guarantee that a message is safe or malicious.",
        "menu_lessons": "📚 Cybersecurity lessons",
        "menu_quiz": "🧪 Quizzes",
        "menu_ip": "🌐 IP information",
        "menu_dns": "🔎 DNS lookup",
        "menu_osint": "🕵️ OSINT basics",
        "menu_ctf": "🧩 CTF",
        "menu_phishing": "🛡 Phishing analysis",
        "menu_certificate": "📜 Certificate",
        "menu_referral": "👥 Referrals",
        "menu_streak": "🔥 Learning streak",
        "menu_premium": "💎 Premium",
        "menu_profile": "👤 My profile",
        "menu_settings": "⚙️ Settings",
        "menu_help": "🆘 Help",
        "menu_main": "🏠 Main menu",
        "start_greeting": "Hello! 👋",
        "start_body": "Welcome to CyberUstozBot!\n\nLearn cybersecurity from scratch, check your knowledge with quizzes, and track your progress.\n\nChoose a section to begin:",
        "settings_title": "⚙️ Settings",
        "settings_language": "Language",
        "settings_notifications": "Notifications",
        "settings_on": "enabled",
        "settings_off": "disabled",
        "settings_choose_language": "Choose your interface language:",
        "settings_saved": "Language saved.",
        "settings_toggle_on": "Enable notifications",
        "settings_toggle_off": "Disable notifications",
        "settings_profile": "👤 Profile",
        "settings_help": "🆘 Help",
        "help_title": "🆘 Help",
        "help_body": "Main commands:\n/start — main menu\n/help — help\n/profile — profile and stats\n/leaderboard — quiz leaderboard\n/lessons — lessons\n/quiz — quiz\n/ip — IP lookup\n/dns — DNS lookup\n/osint — OSINT basics\n/premium — Premium plan\n/ctf — CTF challenges\n/phishing — suspicious text analysis\n/certificate — certificate\n/settings — language and settings\n/referral — referral link\n/daily — daily task\n/streak — learning streak\n/ctf_progress — CTF progress\n/cancel — cancel current action",
        "unknown_command": "Unknown command. Use /help.",
        "unknown_text": "Choose a section from the menu or use /help.",
    },
}


def normalize_language(value: str | None) -> str:
    if value in SUPPORTED_LANGUAGES:
        return value
    return DEFAULT_LANGUAGE


def t(language: str | None, key: str) -> str:
    lang = normalize_language(language)
    table = _MESSAGES.get(lang) or _MESSAGES[DEFAULT_LANGUAGE]
    if key in table:
        return table[key]
    return _MESSAGES[DEFAULT_LANGUAGE].get(key, key)
