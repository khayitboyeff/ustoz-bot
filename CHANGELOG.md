## Premium kategoriyalar yangilanishi
- Admin o‘zi yangi Premium bo‘limlar (masalan Networking, Bash, CTF, Pentest) yaratishi mumkin.
- Har bir bo‘lim ichiga admin mavzu nomi va uzun matn kiritadi.
- Darslar bo‘limida kategoriyalar dinamik tugma bo‘lib ko‘rinadi; kontentga faqat faol Premium obunachilar kira oladi.
- Oldingi funksiyalar saqlab qolindi, AI Ustoz esa olib tashlangan holatda qoldi.

# Changelog

## 2026-10-09 — Telegram-only Premium, referral va admin darslari
- Sayt/Web Admin Dashboard, HTML privacy-policy sahifasi, Web Dashboard BAT va Flask dependency olib tashlandi; loyiha Telegram bot sifatida qoladi.
- Premium tariflari karta orqali manual to‘lovga o‘tkazildi: 1 oy 15 000, 3 oy 40 000, 6 oy 70 000, 12 oy 100 000 so‘m.
- Chek rasm/PDF sifatida adminlarga yuboriladi; admin 1/3/6/12 oy tugmalaridan tanlaydi yoki rad etadi. Chek summasi tarif narxiga mos kelmasa tasdiq bloklanadi; pending chek takroriy so‘rovdan himoyalangan.
- Referral: 15 ta taklifda 30 kun; 30 ta taklifda jami 90 kun. Har bir bosqich bir marta beriladi.
- OSINT natijalari Telegram → Instagram → GitHub tartibida; faqat public profil havolalari va GitHub public API ishlatiladi.
- Himoya: admin-only callback tekshiruvlari, SQLite transaction, chekni bir marta tasdiqlash, tarif summasi tekshiruvi, referral mukofotlarini idempotent berish.
- Testlar: 99 passed; Python compile tekshiruvi muvaffaqiyatli. Jonli Telegram, AI provider va bank ilovasi sinovi foydalanuvchi credentiallari talab qilgani sababli bajarilmagan.

## 2026-10-09 — handler va Premium funksiyalarini chuqurlashtirish
- AI sessiyali chat, `/ai_reset`, `/ai_lang`, tilga mos system prompt va cheklangan conversation context qo‘shildi.
- Premium xaridi uchun Telegram invoice, HMAC bilan bog‘langan invoice payload, pre-checkout validation va successful-payment handler qo‘shildi. Payment event + Premium muddat uzaytirish bitta transaction’da idempotent bajariladi.
- CTF Premium topshiriqlari, server-side Premium guard, alohida hint tugmasi, hint usage va `/ctf_progress` qo‘shildi.
- `/daily` va dars/quiz/CTF yakunlaridan daily reward/achievement trigger’lari ulandi.
- Admin broadcast loyihasi, yuborishdan oldingi tasdiqlash va yuborish natijasi qo‘shildi.
- Profilga daraja, bonus ballari va yutuqlar qo‘shildi.
- Testlar: 91 unit/integration testlar; real Telegram/payment provider sinovi bajarilmagan.

## 2026-10-09 — audit va professional upgrade
- `.env` qiymatlari ustidan OS environment variables ustuvorligi qo‘shildi.
- `DATABASE_PATH` sozlamasi SQLite yo‘lini boshqaradigan qilindi.
- AI ustoz, offline CTF, phishing matn tahlili va kurs sertifikati uchun Telegram buyruqlari/oqimlari ulandi.
- AI va sertifikat PDF yaratish event loop’ni bloklamasligi uchun thread’da bajariladi.
- `fpdf2` dependency qo‘shildi.
- `.env.example` ichidagi namunaviy admin ID’lar olib tashlandi va qo‘shimcha konfiguratsiya hujjatlashtirildi.
- Secret’larni arxivga qo‘shmaslik, testlar va operatsion qo‘llanma bo‘yicha hujjatlar qo‘shildi.
- Web dashboard va to‘liq localization hali yakunlanmagan; Telegram payment handlers mavjud, ammo live provider test bajarilmagan. `AUDIT_REPORT.md` ga qarang.

## Premium karta nusxalash — 2026-10-09
- Tarif tanlangandan keyin Telegram ichida `📋 Kartani nusxalash` tugmasi chiqadi; u `.env` dagi karta raqamini Telegram CopyTextButton orqali nusxalaydi.
- `🧾 Chek yuborish tartibi` tugmasi qo‘shildi va foydalanuvchiga chek yuborish bosqichlarini tushuntiradi.
- README va `.env.example` ichidagi karta sozlamalari bo‘yicha ko‘rsatmalar aniqroq qilindi.
- Sinov: `PYTHONPATH=_testdeps pytest -q` — 99 test muvaffaqiyatli.


## Admin kontent tugmalari va to‘lov chek oqimi
- Admin paneliga darslik, test savoli, savol-javob va ro‘yxat tugmalari qo‘shildi.
- Test savollari 4 ta variant va to‘g‘ri javob bilan quiz savollar bazasiga yoziladi.
- Savol-javoblar alohida SQLite jadvalida saqlanadi va `/questions` orqali ko‘rsatiladi.
- Premium tarifidan keyin “To‘lov qilindi” tugmasi chek yuborishni so‘raydi; chek adminlarga yuboriladi.

## Foydalanuvchi so‘rovi bo‘yicha
- AI Ustoz menyusi va buyruqlari olib tashlandi.
- Admin panelidan darslik qo‘shish hamda video/havola biriktirish tugmalari va buyruqlari olib tashlandi.
- Admin panelida test savollari va savol-javob qo‘shish saqlandi.

## Admin paneli: dars va video kontent
- Asosiy menyuda Profil yonida adminlar uchun `👑 Admin`, boshqa foydalanuvchilar uchun `👤 User` tugmasi ko‘rsatiladi.
- Admin paneliga test savoli, oddiy dars, Telegram video darsligi va dars havolasi qo‘shish amallari kiritildi.
- Admin qo‘shgan darslar umumiy darslar ro‘yxatida ko‘rinadi; havola tugmasi va Telegram video fayli qo‘llanadi.
- Dars qo‘shish amallari `ADMIN_IDS` bilan tekshiriladi.


## Long lesson and media flow
- Removed the 3,000-character limit for custom lesson bodies; lessons now support up to 100,000 characters.
- Admins can send long lesson text in multiple Telegram messages or upload a UTF-8 `.txt` file, then finish with a button.
- Video lessons explicitly prompt the admin to upload a Telegram video after the text is finished.
- Link lessons explicitly prompt the admin for an HTTP(S) URL.
- Long lessons are paginated in the user-facing lesson view to stay within Telegram message limits.

## Subscription gate and lesson deletion update
- Added admin content-menu action to list active custom lessons/videos/links and soft-delete selected items with confirmation.
- Deactivated lessons are hidden from user-facing lesson listings while remaining in the database for audit/recovery.
- Documented mandatory channel subscription commands and Telegram bot admin-permission requirement.


## 2026-10-10 — O‘quv platformasi yangilanishi
- XP hisoblash va XP bo‘yicha TOP reyting qo‘shildi.
- AI Ustoz uchun `/ai` suhbat buyrug‘i va xavfsiz javob siyosati bilan mavjud AI xizmatiga ulanish qo‘shildi.
- `/learning_path` orqali mavzu bo‘yicha shaxsiy dars yo‘llari qo‘shildi.
- `/cyberlab` mavjud xavfsiz offline CTF laboratoriyasiga qulay alias sifatida qo‘shildi.
- Asosiy menyuga AI, o‘quv yo‘li, XP va kunlik vazifalar tugmalari qo‘shildi.
- Avvalgi majburiy obuna, dars/video/link, darsni o‘chirish/tahrirlash, qidiruv, statistika, backup, sertifikat va boshqa funksiyalar saqlandi.


## Yangilanish: AI Ustoz olib tashlandi
- AI Ustoz menyusi, `/ai` buyrug‘i va unga tegishli xizmat olib tashlandi.
- Admin kontent paneliga barcha admin qo‘shgan faol dars/video/havolalarni tasdiqlab bir yo‘la yashirish tugmasi qo‘shildi.
- Boshqa funksiyalar saqlab qolindi.

## Telegram Stars Premium billing
- Added 7-, 30-, and 90-day Telegram Stars (`XTR`) invoices.
- Added pre-checkout validation and activation only after `successful_payment`.
- Added charge-ID idempotency through the existing payments table; active subscriptions are extended rather than overwritten.
- Kept existing manual card/receipt approval flow intact.
