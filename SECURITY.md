# Xavfsizlik siyosati

## Maxfiy konfiguratsiya
- `BOT_TOKEN`, AI/API kalitlari va payment tokenlarini faqat `.env` yoki server environment variables orqali kiriting.
- `.env` hech qachon Git yoki ulashiladigan ZIP ichiga kiritilmasin.
- Agar token arxiv, chat, screenshot yoki repozitoriyga tushib qolgan bo‘lsa, uni BotFather/provider orqali darhol almashtiring.
- Loglarda token, parol, to‘lov rekvizitlari yoki foydalanuvchi yuborgan maxfiy URL query parametrlarini yozmang.

## Administrator
- `ADMIN_IDS` ichida faqat o‘zingiz tasdiqlagan Telegram ID’larini kiriting.
- Ro‘yxat bo‘sh bo‘lsa, admin amallari ishlamasligi kerak.
- Ishlab chiqarish muhitida admin ID’larini davriy tekshiring va audit loglarini himoyalang.

## Database va backup
- Database va backup fayllarini ommaviy web katalogiga joylamang.
- Restore oldidan backup yarating va faqat ishonchli backup faylidan foydalaning.
- Production ma’lumotlari bor database’ni demo ZIP yoki test muhitiga qo‘shmang.
- Ma’lumotlarni o‘chirish talabi kelganda, qonuniy saqlash talablarini hisobga olib, foydalanuvchi yozuvlari va tegishli backup siyosatini ko‘rib chiqing.

## AI va phishing tahlili
- AI javoblari kafolatlangan fakt emas; kodni avtomatik serverda bajarmang.
- AI provider’ga yuborishdan oldin maxfiy ma’lumotlarni olib tashlang.
- Phishing tahlili mahalliy indikatorlarga asoslanadi; URL avtomatik ochilmaydi va natija 100% aniqlikni kafolatlamaydi.

## To‘lovlar
- Ushbu versiyada real checkout va provider webhook handler ulanmagan. `apply_verified_payment` faqat ishonchli provider tekshiruvidan keyin chaqirilishi kerak.
- Provider imzosi, event ID, summa, valyuta, foydalanuvchi va takroriy event tekshirilmasdan Premium bermang.

## Xavfsizlik zaifligi haqida xabar berish
Haqiqiy aloqa manzili loyiha egasi tomonidan kiritilishi kerak: `[SECURITY_CONTACT_EMAIL]`. Maxfiy zaifliklarni ommaviy issue’da token yoki foydalanuvchi ma’lumotlari bilan yubormang.

## Security hardening update (2026-10-10)

- Telegram Stars invoice payloads now include a 128-bit random nonce and an HMAC-SHA256 signature keyed by the bot token. Pre-checkout and successful-payment handlers verify the signature, user ID, plan, XTR currency, and exact amount.
- Stars invoice creation is rate-limited per Telegram user (5-second cooldown).
- Successful Stars payments remain idempotent through the unique provider event/charge ID check and a single SQLite transaction that records the payment and extends Premium.
- Manual receipt uploads accept only image/PDF-like types and enforce the existing 10 MiB document size ceiling; admins must still verify card transfers against their bank statement.
- `.env`, databases, logs, backups, and private keys are excluded by `.gitignore`; never share a real bot token or `.env` file.

### Remaining operational cautions

- The in-memory rate limiter resets when the bot restarts and is not shared across multiple bot processes. Use a persistent/shared limiter if deploying multiple workers or needing limits that survive restarts.
- Do not treat a receipt image as proof of payment; manually reconcile it with the actual bank transaction.
- Keep the bot token private. If exposed, revoke it through BotFather and update the deployment secret.
- Run the full test suite in an environment with `requirements.txt` and `requirements-dev.txt` installed, then conduct a small real Telegram Stars test before public launch.
