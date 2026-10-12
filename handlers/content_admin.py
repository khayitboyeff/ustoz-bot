from __future__ import annotations

import logging
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from config import ADMIN_IDS
from database.db import add_verified_questions, get_connection, record_admin_action

logger = logging.getLogger(__name__)


def _admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in ADMIN_IDS


def content_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Test savoli qo‘shish", callback_data="content_admin:test")],
        [InlineKeyboardButton("📚 Dars qo‘shish", callback_data="content_admin:lesson")],
        [InlineKeyboardButton("🗂 Premium bo‘lim yaratish", callback_data="content_admin:premium_category_add")],
        [InlineKeyboardButton("➕ Premium bo‘limga mavzu qo‘shish", callback_data="content_admin:premium_topic_add")],
        [InlineKeyboardButton("🎥 Video darslik qo‘shish", callback_data="content_admin:video_lesson")],
        [InlineKeyboardButton("🔗 Darsga link ulash", callback_data="content_admin:lesson_link")],
        [InlineKeyboardButton("❓ Savol-javob qo‘shish", callback_data="content_admin:faq")],
        [InlineKeyboardButton("📋 Qo‘shilgan savollar", callback_data="content_admin:list")],
        [InlineKeyboardButton("✏️ Darsni tahrirlash", callback_data="content_admin:edit_list")],
        [InlineKeyboardButton("🗑 Dars/video o‘chirish", callback_data="content_admin:delete_list")],
        [InlineKeyboardButton("⚠️ Barcha qo‘shilgan darslarni o‘chirish", callback_data="content_admin:delete_all_confirm")],
        [InlineKeyboardButton("🏠 Asosiy menyu", callback_data="menu:main")],
    ])


async def admin_content_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if user is None or message is None:
        return
    if not _admin(user.id):
        await message.reply_text("⛔ Bu bo‘lim faqat admin uchun.")
        return
    await message.reply_text(
        "👑 KONTENT BOSHQARUVI\n\n"
        "Bu yerdan test, dars, video darslik va dars havolasi qo‘shishingiz mumkin.\n"
        "Barcha amallar admin Telegram ID bo‘yicha tekshiriladi.\n"
        "/cancel — joriy qo‘shishni bekor qilish.",
        reply_markup=content_admin_keyboard(),
    )


async def content_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, user = update.callback_query, update.effective_user
    if query is None or user is None:
        return
    if not _admin(user.id):
        await query.answer("⛔ Faqat admin.", show_alert=True)
        return
    data = query.data or ""
    await query.answer()
    if data == "admin:content" or data == "content_admin:menu":
        await query.message.reply_text("🛠 Kontent boshqaruvi:", reply_markup=content_admin_keyboard())
        return
    if data == "content_admin:premium_category_add":
        context.user_data["pending_content_admin"] = "premium_category_name"
        context.user_data.pop("content_draft", None)
        await query.message.reply_text("🗂 Yangi Premium bo‘lim nomini yuboring. Masalan: Networking, Bash, CTF, Pentest. /cancel — bekor qilish.")
    elif data == "content_admin:premium_topic_add":
        with get_connection() as conn:
            cats = conn.execute("SELECT id, name FROM premium_categories WHERE is_active=1 ORDER BY name COLLATE NOCASE").fetchall()
        if not cats:
            await query.message.reply_text("Avval 🗂 Premium bo‘lim yarat tugmasi orqali bo‘lim yarating.", reply_markup=content_admin_keyboard())
            return
        buttons = [[InlineKeyboardButton(str(r["name"]), callback_data=f"content_admin:premium_topic_category:{r['id']}")] for r in cats]
        buttons.append([InlineKeyboardButton("⬅️ Admin menyu", callback_data="content_admin:menu")])
        await query.message.reply_text("Mavzu qaysi Premium bo‘limga qo‘shilsin?", reply_markup=InlineKeyboardMarkup(buttons))
    elif data.startswith("content_admin:premium_topic_category:"):
        raw_id = data.rsplit(":", 1)[-1]
        if not raw_id.isdigit():
            await query.message.reply_text("Bo‘lim ID noto‘g‘ri.")
            return
        with get_connection() as conn:
            cat = conn.execute("SELECT id, name FROM premium_categories WHERE id=? AND is_active=1", (int(raw_id),)).fetchone()
        if not cat:
            await query.message.reply_text("Bo‘lim topilmadi.")
            return
        context.user_data["content_draft"] = {"premium_category_id": int(raw_id), "premium_category_name": cat["name"]}
        context.user_data["pending_content_admin"] = "premium_topic_title"
        await query.message.reply_text(f"📘 {cat['name']} bo‘limi uchun mavzu nomini yuboring.")
    elif data == "content_admin:test":
        context.user_data.pop("pending_content_admin", None)
        context.user_data["pending_content_admin"] = "test_topic"
        context.user_data.pop("content_draft", None)
        await query.message.reply_text(
            "📝 Yangi test savoli yaratish.\nAvval mavzu nomini yuboring (masalan: linux, tarmoqlar, phishing).\n"
            "/cancel — bekor qilish."
        )
    elif data == "content_admin:faq":
        context.user_data.pop("pending_content_admin", None)
        context.user_data["pending_content_admin"] = "faq_question"
        context.user_data.pop("content_draft", None)
        await query.message.reply_text("❓ Savol matnini yuboring (10–500 belgi). /cancel — bekor qilish.")
    elif data in {"content_admin:lesson", "content_admin:video_lesson", "content_admin:lesson_link"}:
        context.user_data.pop("pending_content_admin", None)
        context.user_data.pop("content_draft", None)
        context.user_data["content_draft"] = {"lesson_kind": {"content_admin:lesson": "text", "content_admin:video_lesson": "video", "content_admin:lesson_link": "link"}[data]}
        context.user_data["pending_content_admin"] = "lesson_title"
        await query.message.reply_text("📚 Dars nomini yuboring (3–120 belgi). /cancel — bekor qilish.")
    elif data == "content_admin:lesson_body_done":
        draft = context.user_data.get("content_draft", {})
        body = "\n\n".join(draft.get("body_parts", [])).strip()
        if len(body) < 20:
            await query.message.reply_text("Dars matni kamida 20 belgi bo‘lsin. Matn yuboring yoki .txt fayl biriktiring.")
            return
        draft["body"] = body
        kind = draft.get("lesson_kind", "text")
        if kind == "text":
            await _save_lesson(query.message, context, user.id, draft, None, None)
        elif kind == "link":
            context.user_data["pending_content_admin"] = "lesson_url"
            await query.message.reply_text("🔗 Endi dars/video havolasini yuboring (http:// yoki https:// bilan). /cancel — bekor qilish.")
        else:
            context.user_data["pending_content_admin"] = "lesson_video_file"
            await query.message.reply_text("🎥 Endi Telegram orqali videoni yuboring. Video yoki video formatidagi hujjat qabul qilinadi. /cancel — bekor qilish.")
    elif data == "content_admin:edit_list":
        with get_connection() as conn:
            rows = conn.execute("SELECT id, title FROM custom_lessons WHERE is_active=1 ORDER BY id DESC LIMIT 50").fetchall()
        if not rows:
            await query.message.reply_text("Tahrirlash uchun faol dars topilmadi.", reply_markup=content_admin_keyboard())
            return
        buttons = [[InlineKeyboardButton(f"✏️ #{r['id']} {str(r['title'])[:40]}", callback_data=f"content_admin:edit_choose:{r['id']}")] for r in rows]
        buttons.append([InlineKeyboardButton("⬅️ Admin menyu", callback_data="content_admin:menu")])
        await query.message.reply_text("Tahrirlanadigan darsni tanlang:", reply_markup=InlineKeyboardMarkup(buttons))
    elif data.startswith("content_admin:edit_choose:"):
        raw_id = data.rsplit(":", 1)[-1]
        if not raw_id.isdigit():
            await query.message.reply_text("Dars ID noto‘g‘ri.")
            return
        with get_connection() as conn:
            row = conn.execute("SELECT id, title, body FROM custom_lessons WHERE id=? AND is_active=1", (int(raw_id),)).fetchone()
        if not row:
            await query.message.reply_text("Dars topilmadi.", reply_markup=content_admin_keyboard())
            return
        context.user_data["content_edit_id"] = int(raw_id)
        await query.message.reply_text(
            f"✏️ #{row['id']} — {row['title']}\nNimani o‘zgartiramiz?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Nomini", callback_data="content_admin:edit_field:title")],
                [InlineKeyboardButton("📚 Matnini", callback_data="content_admin:edit_field:body")],
                [InlineKeyboardButton("❌ Bekor", callback_data="content_admin:menu")],
            ]),
        )
    elif data.startswith("content_admin:edit_field:"):
        field = data.rsplit(":", 1)[-1]
        lesson_id = context.user_data.get("content_edit_id")
        if field not in {"title", "body"} or not isinstance(lesson_id, int):
            await query.message.reply_text("Avval darsni tanlang.")
            return
        context.user_data["pending_content_admin"] = "edit_lesson_" + field
        await query.message.reply_text("Yangi dars nomini yuboring (3–120 belgi)." if field == "title" else "Yangi dars matnini yuboring (20–4 000 belgi) yoki UTF-8 .txt fayl biriktiring (1 MB gacha). /cancel — bekor qilish.")
    elif data == "content_admin:delete_all_confirm":
        with get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM custom_lessons WHERE is_active=1").fetchone()[0]
        if not count:
            await query.message.reply_text("Faol qo‘shilgan dars/video yo‘q.", reply_markup=content_admin_keyboard())
            return
        await query.message.reply_text(
            f"⚠️ DIQQAT! {count} ta faol qo‘shilgan dars/video foydalanuvchilarga ko‘rinmaydigan qilinadi. Davom etasizmi?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Ha, barchasini o‘chir", callback_data="content_admin:delete_all_do")],
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="content_admin:menu")],
            ]),
        )
    elif data == "content_admin:delete_all_do":
        with get_connection() as conn:
            rows = conn.execute("SELECT id, title FROM custom_lessons WHERE is_active=1").fetchall()
            conn.execute("UPDATE custom_lessons SET is_active=0 WHERE is_active=1")
            conn.commit()
        try:
            record_admin_action(user.id, "content_lessons_delete_all", 0, metadata={"count": len(rows)})
        except Exception:
            pass
        await query.message.reply_text(
            f"✅ {len(rows)} ta qo‘shilgan dars/video o‘chirildi (ro‘yxatdan yashirildi). Asosiy, kodga kiritilgan darslar o‘zgarishsiz qoldi.",
            reply_markup=content_admin_keyboard(),
        )
    elif data == "content_admin:delete_list":
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, title, video_url, video_file_id FROM custom_lessons WHERE is_active=1 ORDER BY id DESC LIMIT 50"
            ).fetchall()
        if not rows:
            await query.message.reply_text("🗑 O‘chirish uchun faol dars yoki video topilmadi.", reply_markup=content_admin_keyboard())
            return
        buttons = []
        for row in rows:
            kind = "🎥" if row["video_file_id"] else ("🔗" if row["video_url"] else "📚")
            title = str(row["title"])
            buttons.append([InlineKeyboardButton(f"{kind} #{row['id']} {title[:40]}", callback_data=f"content_admin:delete_confirm:{row['id']}")])
        buttons.append([InlineKeyboardButton("⬅️ Admin menyu", callback_data="content_admin:menu")])
        await query.message.reply_text(
            "🗑 O‘chirmoqchi bo‘lgan dars/video ni tanlang. O‘chirish foydalanuvchilar ro‘yxatidan yashiradi.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    elif data.startswith("content_admin:delete_confirm:"):
        raw_id = data.rsplit(":", 1)[-1]
        if not raw_id.isdigit():
            await query.message.reply_text("❌ Dars ID noto‘g‘ri.")
            return
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, title FROM custom_lessons WHERE id=? AND is_active=1", (int(raw_id),)
            ).fetchone()
        if not row:
            await query.message.reply_text("Bu dars topilmadi yoki avval o‘chirilgan.", reply_markup=content_admin_keyboard())
            return
        await query.message.reply_text(
            f"⚠️ Rostdan ham #{row['id']} — {row['title']} darsini o‘chirasizmi?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Ha, o‘chir", callback_data=f"content_admin:delete_do:{row['id']}")],
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="content_admin:delete_list")],
            ]),
        )
    elif data.startswith("content_admin:delete_do:"):
        raw_id = data.rsplit(":", 1)[-1]
        if not raw_id.isdigit():
            await query.message.reply_text("❌ Dars ID noto‘g‘ri.")
            return
        with get_connection() as conn:
            row = conn.execute(
                "SELECT title FROM custom_lessons WHERE id=? AND is_active=1", (int(raw_id),)
            ).fetchone()
            if row:
                conn.execute("UPDATE custom_lessons SET is_active=0 WHERE id=?", (int(raw_id),))
                conn.commit()
        if not row:
            await query.message.reply_text("Bu dars allaqachon o‘chirilgan yoki topilmadi.", reply_markup=content_admin_keyboard())
            return
        try:
            record_admin_action(user.id, "content_lesson_delete", 0, metadata={"lesson_id": int(raw_id), "title": row["title"]})
        except Exception:
            pass
        await query.message.reply_text(f"✅ #{raw_id} — {row['title']} dars foydalanuvchilar ro‘yxatidan o‘chirildi.", reply_markup=content_admin_keyboard())
    elif data == "content_admin:list":
        with get_connection() as conn:
            faq = conn.execute(
                "SELECT id, question FROM custom_faq_questions WHERE is_active=1 ORDER BY id DESC LIMIT 10"
            ).fetchall()
            tests = conn.execute(
                "SELECT id, question, topic, difficulty FROM quiz_questions WHERE semantic_key LIKE 'admin:%' ORDER BY id DESC LIMIT 10"
            ).fetchall()
        lines = ["📋 OXIRGI QO‘SHILGANLAR"]
        lines.append("\n❓ Savol-javoblar:")
        lines.extend([f"• #{r['id']} {r['question'][:100]}" for r in faq] or ["• Hozircha yo‘q"])
        lines.append("\n📝 Test savollari:")
        lines.extend([f"• #{r['id']} [{r['topic']}/{r['difficulty']}] {r['question'][:100]}" for r in tests] or ["• Hozircha yo‘q"])
        await query.message.reply_text("\n".join(lines), reply_markup=content_admin_keyboard())


async def handle_content_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    mode = context.user_data.get("pending_content_admin")
    message, user = update.effective_message, update.effective_user
    if not mode or message is None or user is None:
        return False
    if not _admin(user.id):
        context.user_data.pop("pending_content_admin", None)
        context.user_data.pop("content_draft", None)
        await message.reply_text("⛔ Admin ruxsati bekor qilindi.")
        return True
    text = (message.text or "").strip()
    if text.lower() == "/cancel":
        context.user_data.pop("pending_content_admin", None)
        context.user_data.pop("content_draft", None)
        await message.reply_text("Amal bekor qilindi.", reply_markup=content_admin_keyboard())
        return True
    draft = context.user_data.setdefault("content_draft", {})

    if mode == "premium_category_name":
        if not 2 <= len(text) <= 60:
            await message.reply_text("Bo‘lim nomi 2–60 belgi bo‘lishi kerak.")
            return True
        try:
            with get_connection() as conn:
                cur = conn.execute("INSERT INTO premium_categories(name, created_by) VALUES (?, ?)", (text, user.id))
                conn.commit()
                category_id = cur.lastrowid
        except Exception:
            await message.reply_text("Bu nomdagi bo‘lim mavjud yoki saqlashda xatolik bo‘ldi. Boshqa nom kiriting.")
            return True
        context.user_data.pop("pending_content_admin", None)
        try: record_admin_action(user.id, "premium_category_add", 0, metadata={"category_id": category_id, "name": text})
        except Exception: pass
        await message.reply_text(f"✅ Premium bo‘lim yaratildi: {text}\nEndi ‘Premium bo‘limga mavzu qo‘shish’ tugmasi orqali ichiga darslar kiriting.", reply_markup=content_admin_keyboard())
        return True
    if mode == "premium_topic_title":
        if not 2 <= len(text) <= 120:
            await message.reply_text("Mavzu nomi 2–120 belgi bo‘lishi kerak.")
            return True
        draft["premium_topic_title"] = text
        context.user_data["pending_content_admin"] = "premium_topic_body"
        await message.reply_text("✍️ Endi mavzu matnini yuboring (20–100 000 belgi; ko‘p xabar yuborib TAMOM deb yakunlang). /cancel — bekor qilish.")
        return True
    if mode == "premium_topic_body":
        if text.casefold() == "tamom":
            body = "\n\n".join(draft.get("premium_body_parts", [])).strip()
            if len(body) < 20:
                await message.reply_text("Mavzu matni kamida 20 belgi bo‘lsin. Matn yuboring.")
                return True
            with get_connection() as conn:
                cur = conn.execute("INSERT INTO premium_category_topics(category_id,title,body,created_by) VALUES(?,?,?,?)", (draft["premium_category_id"], draft["premium_topic_title"], body, user.id))
                conn.commit(); topic_id = cur.lastrowid
            cat_name = draft.get("premium_category_name", "Premium bo‘lim")
            context.user_data.pop("pending_content_admin", None); context.user_data.pop("content_draft", None)
            try: record_admin_action(user.id, "premium_topic_add", 0, metadata={"topic_id": topic_id, "category_id": draft["premium_category_id"]})
            except Exception: pass
            await message.reply_text(f"✅ ‘{draft.get('premium_topic_title')}’ mavzusi {cat_name} bo‘limiga saqlandi.", reply_markup=content_admin_keyboard())
            return True
        if len(text) + sum(len(x) for x in draft.get("premium_body_parts", [])) > 100_000:
            await message.reply_text("Mavzu 100 000 belgidan oshmasin.")
            return True
        draft.setdefault("premium_body_parts", []).append(text)
        await message.reply_text(f"Matn qabul qilindi ({sum(len(x) for x in draft['premium_body_parts'])} belgi). Davom eting yoki /done yuboring.")
        return True
    if mode == "lesson_title":
        if not 3 <= len(text) <= 120:
            await message.reply_text("Dars nomi 3–120 belgi bo‘lishi kerak.")
            return True
        draft["title"] = text
        draft["body_parts"] = []
        draft["body_chars"] = 0
        kind = draft.get("lesson_kind", "text")
        if kind == "video":
            draft["body"] = "Ushbu dars video shaklida. Videoni tomosha qiling."
            context.user_data["pending_content_admin"] = "lesson_video_file"
            await message.reply_text("🎥 Endi Telegram orqali videoni yuboring. Video yoki video formatidagi hujjat qabul qilinadi.\n/cancel — bekor qilish.")
        elif kind == "link":
            draft["body"] = "Ushbu dars tashqi havola orqali ochiladi. Havolani bosing."
            context.user_data["pending_content_admin"] = "lesson_url"
            await message.reply_text("🔗 Endi dars yoki video havolasini yuboring (http:// yoki https:// bilan).\n/cancel — bekor qilish.")
        else:
            context.user_data["pending_content_admin"] = "lesson_body"
            await message.reply_text(
                "✍️ Dars matnini yuboring. Uzun matnni bir nechta xabar qilib yuborishingiz yoki .txt fayl biriktirishingiz mumkin.\n"
                "Matnni tugatish uchun quyidagi tugmani bosing. Umumiy limit: 100 000 belgi.\n/cancel — bekor qilish.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💾 Matnni tugatish", callback_data="content_admin:lesson_body_done")]]),
            )
        return True
    if mode == "lesson_body":
        if not text:
            await message.reply_text("Matn bo‘sh bo‘lmasin. Matn yuboring yoki .txt fayl biriktiring.")
            return True
        current = int(draft.get("body_chars", 0))
        if current + len(text) + (2 if draft.get("body_parts") else 0) > 100_000:
            await message.reply_text("Matn 100 000 belgidan oshdi. Qisqartiring yoki /cancel bilan bekor qiling.")
            return True
        draft.setdefault("body_parts", []).append(text)
        draft["body_chars"] = current + len(text) + (2 if len(draft["body_parts"]) > 1 else 0)
        await message.reply_text(
            f"✅ Matn qabul qilindi. Hozir: taxminan {draft['body_chars']:,} belgi. Yana matn yuboring yoki tugatish tugmasini bosing.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💾 Matnni tugatish", callback_data="content_admin:lesson_body_done")]]),
        )
        return True
    if mode == "lesson_url":
        if not text.startswith(("https://", "http://")) or len(text) > 500:
            await message.reply_text("Havola http:// yoki https:// bilan boshlansin (500 belgigacha).")
            return True
        draft.setdefault("body", "Ushbu dars tashqi havola orqali ochiladi. Havolani bosing.")
        await _save_lesson(message, context, user.id, draft, text, None)
        return True
    if mode in {"edit_lesson_title", "edit_lesson_body"}:
        lesson_id = context.user_data.get("content_edit_id")
        field = "title" if mode.endswith("title") else "body"
        valid = (3 <= len(text) <= 120) if field == "title" else (20 <= len(text) <= 4_000)
        if not valid:
            await message.reply_text("Nom 3–120 belgi bo‘lsin." if field == "title" else "Matn 20–4 000 belgi bo‘lsin; uzun matn uchun .txt fayl yuboring.")
            return True
        with get_connection() as conn:
            cur = conn.execute(f"UPDATE custom_lessons SET {field}=? WHERE id=? AND is_active=1", (text, lesson_id))
            conn.commit()
        context.user_data.pop("pending_content_admin", None)
        context.user_data.pop("content_edit_id", None)
        if cur.rowcount:
            try:
                record_admin_action(user.id, "content_lesson_edit", 0, metadata={"lesson_id": lesson_id, "field": field})
            except Exception:
                pass
            await message.reply_text("✅ Dars yangilandi.", reply_markup=content_admin_keyboard())
        else:
            await message.reply_text("Dars topilmadi yoki o‘chirilgan.", reply_markup=content_admin_keyboard())
        return True

    if mode == "faq_question":
        if not 10 <= len(text) <= 500:
            await message.reply_text("Savol 10–500 belgi bo‘lishi kerak.")
            return True
        draft["question"] = text
        context.user_data["pending_content_admin"] = "faq_answer"
        await message.reply_text("✍️ Endi javobini yuboring (10–3000 belgi).")
        return True
    if mode == "faq_answer":
        if not 10 <= len(text) <= 3000:
            await message.reply_text("Javob 10–3000 belgi bo‘lishi kerak.")
            return True
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO custom_faq_questions(question, answer, created_by) VALUES (?, ?, ?)",
                (draft["question"], text, user.id),
            )
            conn.commit()
            item_id = int(cur.lastrowid)
        context.user_data.pop("pending_content_admin", None)
        context.user_data.pop("content_draft", None)
        try:
            record_admin_action(user.id, "content_faq_add", 0, metadata={"faq_id": item_id})
        except Exception:
            pass
        await message.reply_text(
            f"✅ Savol-javob saqlandi. ID: {item_id}\nFoydalanuvchilar /questions buyrug‘i orqali ko‘ra oladi.",
            reply_markup=content_admin_keyboard(),
        )
        return True

    if mode == "test_topic":
        if not 2 <= len(text) <= 80:
            await message.reply_text("Mavzu 2–80 belgi bo‘lishi kerak.")
            return True
        draft["topic"] = text.lower().replace(" ", "_")
        context.user_data["pending_content_admin"] = "test_question"
        await message.reply_text("📝 Test savolini yuboring (10–500 belgi).")
        return True
    if mode == "test_question":
        if not 10 <= len(text) <= 500:
            await message.reply_text("Savol 10–500 belgi bo‘lishi kerak.")
            return True
        draft["question"] = text
        draft["options"] = []
        context.user_data["pending_content_admin"] = "test_option_0"
        await message.reply_text("1️⃣ Javob variantini yuboring.")
        return True
    if mode.startswith("test_option_"):
        idx = int(mode.rsplit("_", 1)[1])
        if not 1 <= len(text) <= 250:
            await message.reply_text("Javob varianti 1–250 belgi bo‘lsin.")
            return True
        if text.casefold() in {o.casefold() for o in draft["options"]}:
            await message.reply_text("Variantlar bir xil bo‘lmasligi kerak. Boshqa variant kiriting.")
            return True
        draft["options"].append(text)
        if idx < 3:
            context.user_data["pending_content_admin"] = f"test_option_{idx + 1}"
            await message.reply_text(f"{idx + 2}️⃣ Javob variantini yuboring.")
        else:
            context.user_data["pending_content_admin"] = "test_correct"
            await message.reply_text("To‘g‘ri javob raqamini yuboring: 1, 2, 3 yoki 4.")
        return True
    if mode == "test_correct":
        if text not in {"1", "2", "3", "4"}:
            await message.reply_text("Faqat 1, 2, 3 yoki 4 yuboring.")
            return True
        draft["answer"] = int(text) - 1
        context.user_data["pending_content_admin"] = "test_difficulty"
        await message.reply_text("Qiyinlik darajasini yuboring: easy, medium yoki hard.")
        return True
    if mode == "test_difficulty":
        difficulty = text.lower()
        if difficulty not in {"easy", "medium", "hard"}:
            await message.reply_text("Faqat easy, medium yoki hard tanlang.")
            return True
        token = uuid.uuid4().hex
        question = {
            "public_id": f"admin-{token}",
            "semantic_key": f"admin:{token}",
            "topic": draft["topic"][:80],
            "difficulty": difficulty,
            "question_type": "single_choice",
            "question": draft["question"],
            "options": draft["options"],
            "answer": draft["answer"],
        }
        try:
            added = add_verified_questions([question])
        except Exception as exc:
            logger.warning("Admin test question save failed (%s).", type(exc).__name__)
            await message.reply_text("❌ Test savolini saqlab bo‘lmadi. Savol matni takrorlanmaganini tekshiring.")
            return True
        context.user_data.pop("pending_content_admin", None)
        context.user_data.pop("content_draft", None)
        try:
            record_admin_action(user.id, "content_test_question_add", 0, metadata={"topic": question["topic"]})
        except Exception:
            pass
        await message.reply_text(
            "✅ Test savoli saqlandi va umumiy testlar bankiga qo‘shildi."
            if added else "⚠️ Bu savol bazada avvaldan bor, dublikat sifatida qo‘shilmadi.",
            reply_markup=content_admin_keyboard(),
        )
        return True
    return False


async def _save_lesson(message, context, admin_id: int, draft: dict, video_url: str | None, video_file_id: str | None) -> None:
    from services.lesson_service import create_custom_lesson, attach_video_file
    try:
        lesson_id = create_custom_lesson(draft["title"], draft["body"], video_url, admin_id)
        if video_file_id:
            attach_video_file(lesson_id, video_file_id)
    except Exception as exc:
        logger.warning("Admin lesson save failed (%s).", type(exc).__name__)
        await message.reply_text("❌ Darsni saqlab bo‘lmadi. Ma’lumotlarni tekshirib qayta urinib ko‘ring.", reply_markup=content_admin_keyboard())
        return
    context.user_data.pop("pending_content_admin", None)
    context.user_data.pop("content_draft", None)
    try:
        record_admin_action(admin_id, "content_lesson_add", 0, metadata={"lesson_id": lesson_id})
    except Exception:
        pass
    await message.reply_text(f"✅ Dars saqlandi! ID: {lesson_id}\nFoydalanuvchilar 📚 Kiberxavfsizlik darslari bo‘limidan ko‘rishlari mumkin.", reply_markup=content_admin_keyboard())


async def handle_content_admin_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, user = update.effective_message, update.effective_user
    mode = context.user_data.get("pending_content_admin")
    if message is None or user is None or not mode:
        return
    if not _admin(user.id):
        context.user_data.pop("pending_content_admin", None)
        context.user_data.pop("content_draft", None)
        await message.reply_text("⛔ Bu amal faqat admin uchun.")
        return

    draft = context.user_data.setdefault("content_draft", {})
    if mode in {"lesson_body", "edit_lesson_body"} and message.document:
        document = message.document
        filename = (document.file_name or "").lower()
        mime = (document.mime_type or "").lower()
        if not (filename.endswith(".txt") or mime.startswith("text/plain")):
            await message.reply_text("Dars matni uchun .txt fayl yuboring yoki oddiy matn xabari jo‘nating.")
            return
        if document.file_size and document.file_size > 1_000_000:
            await message.reply_text(".txt fayl 1 MB dan kichik bo‘lishi kerak.")
            return
        try:
            telegram_file = await context.bot.get_file(document.file_id)
            raw = await telegram_file.download_as_bytearray()
            file_text = bytes(raw).decode("utf-8-sig").strip()
        except Exception as exc:
            logger.warning("Lesson text file download failed (%s).", type(exc).__name__)
            await message.reply_text("Faylni o‘qib bo‘lmadi. UTF-8 kodlashdagi .txt fayl yuboring.")
            return
        if not file_text:
            await message.reply_text("Fayl bo‘sh. Matnli .txt fayl yuboring.")
            return
        if mode == "edit_lesson_body":
            if len(file_text) < 20 or len(file_text) > 100_000:
                await message.reply_text("Dars matni 20–100 000 belgi oralig‘ida bo‘lishi kerak.")
                return
            lesson_id = context.user_data.get("content_edit_id")
            with get_connection() as conn:
                cur = conn.execute("UPDATE custom_lessons SET body=? WHERE id=? AND is_active=1", (file_text, lesson_id))
                conn.commit()
            context.user_data.pop("pending_content_admin", None)
            context.user_data.pop("content_edit_id", None)
            if cur.rowcount:
                try:
                    record_admin_action(user.id, "content_lesson_edit", 0, metadata={"lesson_id": lesson_id, "field": "body", "source": "txt"})
                except Exception:
                    pass
                await message.reply_text("✅ Dars matni .txt fayldan yangilandi.", reply_markup=content_admin_keyboard())
            else:
                await message.reply_text("Dars topilmadi yoki o‘chirilgan.", reply_markup=content_admin_keyboard())
            return
        current = int(draft.get("body_chars", 0))
        if current + len(file_text) + (2 if draft.get("body_parts") else 0) > 100_000:
            await message.reply_text("Jami dars matni 100 000 belgidan oshmasligi kerak.")
            return
        draft.setdefault("body_parts", []).append(file_text)
        draft["body_chars"] = current + len(file_text) + (2 if len(draft["body_parts"]) > 1 else 0)
        await message.reply_text(
            f"✅ .txt fayl matni qabul qilindi. Jami: taxminan {draft['body_chars']:,} belgi. Yana matn/fayl yuboring yoki tugatish tugmasini bosing.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💾 Matnni tugatish", callback_data="content_admin:lesson_body_done")]]),
        )
        return

    if mode != "lesson_video_file":
        return
    file_id = message.video.file_id if message.video else None
    if not file_id and message.document and (message.document.mime_type or "").startswith("video/"):
        file_id = message.document.file_id
    if not file_id:
        await message.reply_text("Iltimos, Telegram video yoki video formatidagi hujjat yuboring.")
        return
    if draft.get("body_parts"):
        draft["body"] = "\n\n".join(draft.get("body_parts", [])).strip()
    else:
        draft.setdefault("body", "Ushbu dars video shaklida. Videoni tomosha qiling.")
    await _save_lesson(message, context, user.id, draft, None, file_id)


async def questions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, question, answer FROM custom_faq_questions WHERE is_active=1 ORDER BY id DESC LIMIT 20"
        ).fetchall()
    if not rows:
        await message.reply_text("❓ Hozircha savol-javoblar qo‘shilmagan.")
        return
    for row in rows:
        text = f"❓ {row['question']}\n\n💡 {row['answer']}"
        await message.reply_text(text[:4000])


def register_content_admin_handlers(app) -> None:
    app.add_handler(CommandHandler("admin_content", admin_content_command))
    app.add_handler(CommandHandler("questions", questions_command))
    app.add_handler(CallbackQueryHandler(content_admin_callback, pattern=r"^(content_admin:|admin:content$)"))
    app.add_handler(MessageHandler((filters.VIDEO | filters.Document.ALL), handle_content_admin_media))
