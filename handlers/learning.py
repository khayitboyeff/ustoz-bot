from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes
from config import ADMIN_IDS
from handlers.rate_limit import rate_limited
from database.db import get_completed_lessons, mark_lesson_completed, get_connection

LESSONS = [
    {
        "id": 1,
        "title": "Kiberxavfsizlikka kirish",
        "text": (
            "Kiberxavfsizlik — axborot tizimlarining maxfiyligini, yaxlitligini va mavjudligini himoya qilishdir. "
            "Bu soha himoyalanish, aniqlash va javob qaytarish jarayonlarini o‘z ichiga oladi.\n\n"
            "Asosiy maqsad: foydalanuvchilar, tashkilotlar va tarmoqlar himoyasi. "
            "Bunday himoya uchun parollarni boshqarish, dasturlarni yangilash, antivirus va himoya siyosati muhim."
        ),
    },
    {
        "id": 2,
        "title": "IP manzil nima?",
        "text": (
            "IP manzil (Internet Protocol address) — kompyuter yoki qurilma internetdagi o‘ziga xos identifikatoridir. "
            "IPv4 ko‘pincha 4 ta sonli blokdan iborat bo‘ladi, masalan 8.8.8.8.\n\n"
            "IP ma’lumotlari tarmoq trafikini yo‘naltirish va qurilmalarning aniqligini aniqlash uchun ishlatiladi. "
            "Public IP internetga ochiq bo‘ladi, private IP esa ichki tarmoqlar uchun ishlatiladi."
        ),
    },
    {
        "id": 3,
        "title": "DNS qanday ishlaydi?",
        "text": (
            "DNS (Domain Name System) — domen nomlarini IP manzillariga aylantiruvchi tizimdir. "
            "Masalan, example.com so‘zi serverga mos keluvchi IP manzilga tarjima qilinadi.\n\n"
            "DNS ishlash prinsipi: foydalanuvchi domen yozadi, resolver so‘rov yuboradi, server javob qaytaradi. "
            "A, AAAA, MX, NS yozuvlari bu jarayonda muhim ahamiyatga ega."
        ),
    },
    {
        "id": 4,
        "title": "Kuchli parol va ikki bosqichli himoya",
        "text": (
            "Kuchli parol uzun, tasodifiy va ma’lum so‘zlardan iborat bo‘lmasligi kerak. "
            "Uzoq va o‘ziga xos belgilar, raqamlar va katta-kichik harflar foydali.\n\n"
            "Ikki bosqichli himoya (2FA) parol bilan birga qo‘shimcha tasdiqdan o‘tishni talab qiladi. "
            "Bu himoya darajasini sezilarli darajada oshiradi va hisobga ruxsatsiz kirishni qiyinlashtiradi."
        ),
    },
    {
        "id": 5,
        "title": "Phishing va zararli havolalarni aniqlash",
        "text": (
            "Fishing — foydalanuvchini aldashga qaratilgan xakerlik usuli bo‘lib, odatda noto‘g‘ri link, e-pochta yoki xabar orqali amalga oshiriladi.\n\n"
            "Zararli havolalarni aniqlash uchun: URL manzilini tekshirish, ishonchli domenlarni taqqoslash, qaroqchi saytlardan ehtiyot bo‘lish, "
            "va har doim to‘g‘ri rasm, manba va xavfsizlik belgilarini ko‘rib chiqish kerak."
        ),
    },
    {
        "id": 6,
        "title": "Internet va tarmoqlar",
        "text": (
            "Tarmoq qurilmalari ma’lumotni protokollar orqali almashadi. Router tarmoqlar orasida paketlarni yo‘naltiradi, "
            "switch esa lokal tarmoq ichidagi qurilmalarni bog‘laydi. TCP yetkazilish va tartibni nazorat qiladi; UDP esa kamroq "
            "kechikish evaziga yetkazilishni kafolatlamaydi.\n\n"
            "Himoya uchun router va access point dasturini yangilang, standart administrator parolini almashtiring, "
            "WPA2-AES yoki WPA3 ishlating va mehmonlar uchun alohida Wi-Fi yarating."
        ),
    },
    {
        "id": 7,
        "title": "HTTP va HTTPS",
        "text": (
            "HTTP brauzer va server o‘rtasida so‘rov-javob almashadi. HTTPS shu aloqani TLS bilan himoyalab, "
            "uzatilayotgan ma’lumotning maxfiyligi va yaxlitligini ta’minlashga yordam beradi. Qulf belgisi sayt egasi halol ekanini "
            "o‘zi bilan kafolatlamaydi.\n\n"
            "Shaxsiy ma’lumot yuborishdan oldin domenni tekshiring, brauzer ogohlantirishlarini chetlab o‘tmang va umumiy Wi-Fi’da "
            "sezgir ishlarni faqat ishonchli, HTTPS ulanishda bajaring."
        ),
    },
    {
        "id": 8,
        "title": "Windows va Linux xavfsizligi",
        "text": (
            "Operatsion tizim va dasturlarni yangilab turish ma’lum zaifliklarni yopadi. Kundalik ish uchun administrator/root "
            "hisobidan foydalanmaslik zararli dastur ta’sirini cheklaydi.\n\n"
            "Noma’lum manbadan fayl o‘rnatmang, firewall’ni yoqilgan saqlang, keraksiz xizmatlarni o‘chiring va muhim fayllarning "
            "alohida zaxira nusxasini oling. Linux’da `sudo`ni faqat ishonchli buyruqlarga qo‘llang."
        ),
    },
    {
        "id": 9,
        "title": "Python xavfsizlik asoslari",
        "text": (
            "Foydalanuvchi kiritgan qiymatga ishonmang: format va uzunlikni tekshiring, SQL uchun parametrli so‘rov ishlating, "
            "HTML’da ko‘rsatishda kontekstga mos escaping qiling. Maxfiy tokenlarni source code yoki logga yozmang.\n\n"
            "Kutubxonalarni minimal saqlang, versiyalarni tekshiring va xatolarni qayta ishlaganda credential yoki shaxsiy ma’lumotni "
            "chiqarmang."
        ),
    },
    {
        "id": 10,
        "title": "Veb xavfsizlik",
        "text": (
            "SQL injection, XSS va CSRF veb-ilovalardagi keng tarqalgan xavflardir. SQL’ni string birlashtirish bilan qurmaslik, "
            "foydalanuvchi matnini HTML’da xavfsiz chiqarish va holat o‘zgartiruvchi so‘rovlarni serverda tekshirish muhim.\n\n"
            "Himoya qatlamlari: input validation, parametrli query, output encoding, autentifikatsiya, minimal ruxsatlar va "
            "xavfsizlik yangilanishlari. Sinovlarni faqat o‘zingizga tegishli yoki ruxsat berilgan tizimda bajaring."
        ),
    },
    {
        "id": 11,
        "title": "OSINT va maxfiylik etikasi",
        "text": (
            "OSINT — ochiq manbalardagi ma’lumotni qonuniy va maqsadga mutanosib tahlil qilish. Ochiq ma’lumot ham shaxsiy bo‘lishi "
            "mumkin; uni yig‘ish yoki tarqatishdan oldin zarurat, rozilik va mahalliy qonunlarni hisobga oling.\n\n"
            "Ruxsatsiz akkauntga kirmang, login himoyasini chetlab o‘tmang va tasdiqlanmagan ma’lumotni fakt sifatida tarqatmang. "
            "Keraksiz shaxsiy ma’lumotni qayd etmaslik — muhim himoya chorasi."
        ),
    },
    {
        "id": 12,
        "title": "Xavfsiz laboratoriya va hodisaga javob",
        "text": (
            "Amaliy mashqlarni lokal virtual mashina yoki maxsus o‘quv laboratoriyasida bajaring; begona tizimlarni skanerlamang. "
            "Sinov oldidan scope va ruxsatni yozma aniqlang.\n\n"
            "Hodisa gumon qilinsa, qurilmani tarmoqdan ajrating, dalillarni o‘chirmang, tashkilotning hodisaga javob berish tartibiga "
            "xabar bering va toza zaxiradan tiklashni mutaxassis bilan rejalashtiring."
        ),
    },
]




def all_lessons() -> list[dict]:
    """Built-in darslar va admin qo‘shgan darslarni birlashtiradi."""
    try:
        from services.lesson_service import list_custom_lessons
        return LESSONS + list_custom_lessons()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Custom lessons unavailable (%s).", type(exc).__name__)
        return LESSONS


def _is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in ADMIN_IDS


def build_lessons_menu(completed_ids: set[int] | None = None, lessons_override: list[dict] | None = None) -> InlineKeyboardMarkup:
    completed_ids = completed_ids or set()
    lessons = lessons_override if lessons_override is not None else all_lessons()
    buttons = []
    for lesson in lessons:
        marker = "✅ " if lesson["id"] in completed_ids else ""
        buttons.append([
            InlineKeyboardButton(f"{marker}{lesson['id']}. {lesson['title']}", callback_data=f"lesson:{lesson['id']}")
        ])
    buttons.append([InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def _premium_category_buttons(user_id: int | None) -> list[list[InlineKeyboardButton]]:
    try:
        with get_connection() as conn:
            rows = conn.execute("SELECT id, name FROM premium_categories WHERE is_active=1 ORDER BY name COLLATE NOCASE").fetchall()
        from services.premium_service import has_active_premium
        active = bool(user_id and has_active_premium(user_id))
        return [[InlineKeyboardButton(("💎 " if active else "🔒 ") + str(row["name"]), callback_data=f"premiumcat:{row['id']}" if active else "premiumcat:locked")] for row in rows]
    except Exception:
        return []


@rate_limited("lessons")
async def show_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE, search_override: str | None = None) -> None:
    query = update.callback_query
    if query is not None:
        await query.answer()
    user = update.effective_user
    completed_ids = set()
    if user is not None:
        try:
            completed_ids = get_completed_lessons(user.id)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Lesson progress read failed (%s).", type(exc).__name__)
    lessons = all_lessons()
    raw_search = search_override if search_override is not None else (" ".join(context.args or []).strip() if context.args else "")
    search_term = raw_search.casefold().strip()
    if search_term:
        lessons = [item for item in lessons if search_term in item["title"].casefold() or search_term in item.get("text", "").casefold()]
    text = f"📚 Kiberxavfsizlik darslari ({len(completed_ids)}/{len(all_lessons())} tugallangan):\n"
    if search_term:
        text += f"🔎 Qidiruv: {search_term} ({len(lessons)} ta natija)\n"
    text += "\nTanlang yoki /lesson_search mavzu deb qidiring.\nKategoriyalar: tarmoq, parol, web, python, phishing, linux, osint."
    markup = build_lessons_menu(completed_ids, lessons)
    category_rows = _premium_category_buttons(user.id if user else None)
    if category_rows:
        buttons = list(markup.inline_keyboard[:-1]) + category_rows + [list(markup.inline_keyboard[-1])]
        markup = InlineKeyboardMarkup(buttons)
    if query is not None:
        await query.edit_message_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)


async def lesson_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    term = " ".join(context.args or []).strip()
    if not term:
        await update.effective_message.reply_text("Qidiruv: /lesson_search phishing yoki /lesson_search tarmoq")
        return
    await show_lessons(update, context, search_override=term)


def _split_lesson_text(text: str, limit: int = 3300) -> list[str]:
    """Split long lesson text into Telegram-safe pages without dropping content."""
    text = text or ""
    if not text:
        return ["Bu dars uchun matn kiritilmagan."]
    pages: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            pages.append(remaining)
            break
        cut = remaining.rfind("\n", 0, limit)
        if cut >= limit // 2:
            cut += 1
        else:
            cut = remaining.rfind(" ", 0, limit)
            if cut >= limit // 2:
                cut += 1
            else:
                cut = limit
        pages.append(remaining[:cut])
        remaining = remaining[cut:]
    return pages


@rate_limited("lesson_callback", 0.5)
async def handle_lesson_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lessons = all_lessons()
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""
    user = update.effective_user
    parts = data.split(":")
    if len(parts) == 3 and parts[1] == "complete":
        try:
            lesson_id = int(parts[2])
            next(item for item in lessons if item["id"] == lesson_id)
            if user is None:
                raise ValueError("User missing")
            mark_lesson_completed(user.id, lesson_id)
        except (IndexError, ValueError, StopIteration):
            await query.answer("Darsni yakunlab bo‘lmadi. Qayta urinib ko‘ring.", show_alert=True)
            return
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Lesson progress write failed (%s).", type(exc).__name__)
            await query.answer("Dars progressini saqlab bo‘lmadi.", show_alert=True)
            return
        try:
            from database.features import complete_daily_task, grant_achievement, get_completed_lessons as get_feature_lessons
            complete_daily_task(user.id, "lesson")
            grant_achievement(user.id, "first_lesson")
            if len(get_feature_lessons(user.id)) >= 12:
                grant_achievement(user.id, "course_12_lessons")
        except Exception as exc:
            import logging
            logging.getLogger(__name__).debug("Lesson reward update skipped (%s).", type(exc).__name__)
        await query.answer("Dars tugallanganlar ro‘yxatiga qo‘shildi.")
        await show_lesson_detail(update, lesson_id, completed=True, page=0, send_video=False)
        return

    if len(parts) == 3 and parts[0] == "lessonpage":
        try:
            lesson_id, page = int(parts[1]), int(parts[2])
        except ValueError:
            await query.answer("Dars sahifasi noto‘g‘ri.", show_alert=True)
            return
        lesson = next((item for item in lessons if item["id"] == lesson_id), None)
        if lesson is None:
            await query.answer("Bu dars topilmadi.", show_alert=True)
            return
        await query.answer()
        try:
            completed_ids = get_completed_lessons(user.id) if user else set()
        except Exception:
            completed_ids = set()
        await show_lesson_detail(update, lesson_id, completed=lesson_id in completed_ids, page=page, send_video=False)
        return

    if len(parts) != 2 or parts[0] != "lesson":
        await query.answer("Dars havolasi yaroqsiz.", show_alert=True)
        return
    try:
        lesson_id = int(parts[1])
    except (IndexError, ValueError):
        await query.answer("Dars tanlanmadi.")
        return
    lesson = next((item for item in lessons if item["id"] == lesson_id), None)
    if lesson is None:
        await query.answer("Bu dars topilmadi.", show_alert=True)
        return
    await query.answer()
    try:
        completed_ids = get_completed_lessons(user.id) if user else set()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Lesson progress read failed (%s).", type(exc).__name__)
        await query.edit_message_text("Dars ochildi, lekin progressni hozir o‘qib bo‘lmadi.")
        return
    await show_lesson_detail(update, lesson_id, completed=lesson_id in completed_ids, page=0, send_video=True)


async def show_lesson_detail(update: Update, lesson_id: int, *, completed: bool, page: int = 0, send_video: bool = False) -> None:
    query = update.callback_query
    lessons = all_lessons()
    lesson_index = next((index for index, lesson in enumerate(lessons) if lesson["id"] == lesson_id), None)
    if query is None or lesson_index is None:
        return
    lesson = lessons[lesson_index]
    pages = _split_lesson_text(lesson.get("text", ""))
    page = max(0, min(page, len(pages) - 1))
    buttons: list[list[InlineKeyboardButton]] = []
    if lesson.get("video_url"):
        buttons.append([InlineKeyboardButton("▶️ Video / dars havolasini ochish", url=lesson["video_url"])])
    if len(pages) > 1:
        page_nav = []
        if page > 0:
            page_nav.append(InlineKeyboardButton("⬅️ Oldingi qism", callback_data=f"lessonpage:{lesson_id}:{page - 1}"))
        page_nav.append(InlineKeyboardButton(f"📄 {page + 1}/{len(pages)}", callback_data=f"lessonpage:{lesson_id}:{page}"))
        if page + 1 < len(pages):
            page_nav.append(InlineKeyboardButton("Keyingi qism ➡️", callback_data=f"lessonpage:{lesson_id}:{page + 1}"))
        buttons.append(page_nav)
    navigation = []
    if lesson_index > 0:
        navigation.append(InlineKeyboardButton("⬅️ Oldingi dars", callback_data=f"lesson:{lessons[lesson_index - 1]['id']}"))
    if lesson_index + 1 < len(lessons):
        navigation.append(InlineKeyboardButton("Keyingi dars ➡️", callback_data=f"lesson:{lessons[lesson_index + 1]['id']}"))
    if navigation:
        buttons.append(navigation)
    buttons.append([InlineKeyboardButton("✅ Darsni tugatdim" if not completed else "✅ Tugallangan", callback_data=f"lesson:complete:{lesson_id}")])
    buttons.append([InlineKeyboardButton("🧪 Quiz", callback_data="menu:quiz"), InlineKeyboardButton("📚 Darslar", callback_data="menu:lessons")])
    buttons.append([InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu:main")])
    lesson_text = f"📘 {lesson['title']} ({lesson_index + 1}/{len(lessons)})"
    if len(pages) > 1:
        lesson_text += f"\n📄 Matn qismi {page + 1}/{len(pages)}"
    lesson_text += f"\n\n{pages[page]}"
    await query.edit_message_text(lesson_text, reply_markup=InlineKeyboardMarkup(buttons))
    if send_video and page == 0 and lesson.get("video_file_id"):
        try:
            await query.message.reply_video(video=lesson["video_file_id"], caption=f"🎥 {lesson['title']}")
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Stored lesson video send failed (%s).", type(exc).__name__)
            await query.message.reply_text("🎥 Video yuborilmadi. Admin video faylni qayta yuklashi kerak.")


async def handle_premium_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None:
        return
    await query.answer()
    if (query.data or "") == "premiumcat:locked":
        await query.message.reply_text("🔒 Bu bo‘limlar faqat faol Premium obunachilar uchun. Tariflar: /premium")
        return
    from services.premium_service import has_active_premium
    if user is None or not has_active_premium(user.id):
        await query.message.reply_text("🔒 Bu bo‘lim faqat faol Premium obunachilar uchun. /premium orqali obunani ko‘ring.")
        return
    raw = (query.data or "").rsplit(":", 1)[-1]
    if not raw.isdigit():
        return
    with get_connection() as conn:
        cat = conn.execute("SELECT id,name FROM premium_categories WHERE id=? AND is_active=1", (int(raw),)).fetchone()
        topics = conn.execute("SELECT id,title FROM premium_category_topics WHERE category_id=? AND is_active=1 ORDER BY id", (int(raw),)).fetchall() if cat else []
    if not cat:
        await query.message.reply_text("Bo‘lim topilmadi yoki o‘chirilgan.")
        return
    buttons = [[InlineKeyboardButton(str(row["title"]), callback_data=f"premiumtopic:{row['id']}")] for row in topics]
    buttons.append([InlineKeyboardButton("⬅️ Darslar", callback_data="menu:lessons")])
    await query.message.reply_text(f"💎 {cat['name']}\n\nMavzuni tanlang:", reply_markup=InlineKeyboardMarkup(buttons))


async def handle_premium_topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None:
        return
    await query.answer()
    from services.premium_service import has_active_premium
    if user is None or not has_active_premium(user.id):
        await query.message.reply_text("🔒 Bu mavzu faqat faol Premium obunachilar uchun. /premium")
        return
    raw = (query.data or "").rsplit(":", 1)[-1]
    if not raw.isdigit():
        return
    with get_connection() as conn:
        row = conn.execute("SELECT t.title,t.body,c.name AS category FROM premium_category_topics t JOIN premium_categories c ON c.id=t.category_id WHERE t.id=? AND t.is_active=1 AND c.is_active=1", (int(raw),)).fetchone()
    if not row:
        await query.message.reply_text("Mavzu topilmadi yoki o‘chirilgan.")
        return
    body = str(row["body"])
    for start in range(0, len(body), 3800):
        await query.message.reply_text(f"💎 {row['category']} · {row['title']}\n\n" + body[start:start+3800])


def register_learning_handlers(app) -> None:
    app.add_handler(CommandHandler("lessons", show_lessons))
    app.add_handler(CommandHandler("lesson_search", lesson_search_command))
    app.add_handler(CallbackQueryHandler(handle_lesson_callback, pattern=r"^(lesson:|lessonpage:)"))
    app.add_handler(CallbackQueryHandler(handle_premium_category_callback, pattern=r"^premiumcat:"))
    app.add_handler(CallbackQueryHandler(handle_premium_topic_callback, pattern=r"^premiumtopic:"))
