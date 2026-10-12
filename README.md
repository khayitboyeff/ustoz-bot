# CyberUstozBot

Saytsiz, Telegram ichida ishlaydigan kiberxavfsizlik ta’lim boti. Barcha boshqaruv bot buyruqlari va inline tugmalar orqali bajariladi.

## Imkoniyatlar
- 💎 Premium: Telegram Stars (XTR) orqali 7/30/90 kunlik tariflar; qo‘shimcha ravishda 1/3/6/12 oylik karta to‘lovi va admin tasdig‘i.
- 🎁 Referral: 15 ta taklifda 30 kun, 30 ta taklifda jami 90 kunlik bepul Pro mukofoti; har bir bosqich bir marta beriladi.
- 📚 O‘rnatilgan darslar va admin qo‘shadigan uzun matnli, video yoki havolali darslar.
- 🧩 Offline CTF, 🧪 quiz, 🛡 phishing matn tahlili, 🔎 OSINT, DNS/IP vositalari, profil, kunlik vazifalar va sertifikat.
- 🔐 Admin buyruqlari, audit jurnali, backup/restore va rate-limit himoyasi.

## Windows’da o‘rnatish

```powershell
cd C:\CyberUstozBot
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt
Copy-Item .env.example .env
```

`.env` ichida kamida `BOT_TOKEN` va `ADMIN_IDS` ni sozlang. `ADMIN_IDS` — vergul bilan ajratilgan Telegram ID’lar. Karta ma’lumotlarini `PAYMENT_CARD_NUMBER`, `PAYMENT_CARD_HOLDER`, `PAYMENT_CARD_BANK` qiymatlariga kiriting. So‘ng:

```powershell
python -m compileall -q .
pytest -q
python bot.py
```

## Premium to‘lov jarayoni

### Telegram Stars (XTR)
1. Foydalanuvchi `/premium` dan 7, 30 yoki 90 kunlik Stars tarifini tanlaydi.
2. Bot XTR invoice yuboradi; Stars uchun `provider_token` bo‘sh qoldiriladi.
3. Pre-checkout bosqichida foydalanuvchi ID, tarif, valyuta va aniq summa tekshiriladi.
4. Premium faqat Telegram `successful_payment` yangilanishidan keyin faollashadi.
5. Telegram charge ID bazada noyob kalit sifatida saqlanadi; takroriy update Premium muddatini qayta bermaydi.

### Karta orqali qo‘lda tekshiriladigan to‘lov
1. Foydalanuvchi `/premium` orqali karta tarifini tanlaydi.
2. Bot karta ma’lumotlarini ko‘rsatadi, foydalanuvchi chekni yuboradi.
3. Admin bank ilovasi orqali haqiqiy to‘lovni tekshirib tasdiqlaydi yoki rad etadi.
4. Admin tasdig‘i takroran bosilsa, Premium ikkinchi marta berilmaydi.

Telegram Stars va bank to‘lovi ikki alohida yo‘l. Bank cheki Telegram Stars to‘lovi sifatida hisoblanmaydi.

Tariflar: 1 oy — 15 000 so‘m; 3 oy — 40 000 so‘m; 6 oy — 70 000 so‘m; 12 oy — 100 000 so‘m. Bot avtomatik ravishda bank to‘lovini tekshirmaydi; admin chekning haqiqiyligini tekshirishi shart.

## OSINT va xavfsizlik
OSINT natijalari Telegram → Instagram → GitHub tartibida ko‘rsatiladi. Telegram va Instagram uchun havolalar beriladi; GitHub public API javobi “topilmadi”ni aniqlashi mumkin, API cheklovi esa noaniq natija sifatida ko‘rsatiladi. Bu akkaunt egasining shaxsini tasdiqlamaydi. Faqat ochiq ma’lumotdan qonuniy va mas’uliyatli foydalaning.

`.env`, database, loglar, backup’lar va foydalanuvchi cheklarini umumiy ZIP yoki repository’ga kiritmang. Agar bot tokeni tarqalgan bo‘lsa, BotFather orqali darhol yangilang.


### Karta orqali Premium to‘lovi

`.env` ichida `PAYMENT_CARD_NUMBER`, `PAYMENT_CARD_HOLDER`, `PAYMENT_CARD_BANK` va `PAYMENT_CARD_INSTRUCTIONS` qiymatlarini kiriting. Foydalanuvchi `/premium` orqali tarif tanlaganda karta ma’lumotlari va **📋 Kartani nusxalash** tugmasi chiqadi. To‘lovdan keyin foydalanuvchi chekni rasm yoki PDF/JPG/PNG hujjat sifatida shu chatga yuboradi. Bot chek so‘rovini adminlarga yuboradi; admin haqiqiy to‘lovni tekshirib tasdiqlagandan keyingina obuna faollashadi. Karta raqamini kodga yozmang va `.env` faylini hech kimga yubormang.


## Admin kontent boshqaruvi

Telegram botda `/admin` yoki `/admin_content` buyrug‘ini oching (yoki `/admin` panelidagi kontent tugmasini bosing). Faqat `.env` dagi `ADMIN_IDS` ro‘yxatiga kiritilgan Telegram ID lar:
- **📝 Test savoli qo‘shish** — mavzu, savol, to‘rtta variant, to‘g‘ri javob va qiyinlik. Yangi savol umumiy `/quiz` savollar bankiga saqlanadi.
- **❓ Savol-javob qo‘shish** — matnli savol va javob. Foydalanuvchilar `/questions` orqali ko‘rishi mumkin.
- **📋 Qo‘shilgan savollar** — oxirgi savol-javob va test savollarini ko‘rsatadi.

Joriy qo‘shishni `/cancel` bilan bekor qiling. Admin tekshiruvi tugmalarda ham, matn yuborish bosqichlarida ham server tomonida bajariladi.

Premium qo‘lda to‘lovida tarif tanlangach **✅ To‘lov qilindi** tugmasi chek yuborish oynasini chiqaradi. Foydalanuvchi chekni rasm yoki PDF hujjat sifatida yuboradi; bot uni adminlarga yuboradi va admin tasdiqlagandan keyingina Premium faollashadi.


### Admin orqali uzun dars, video va havola qo‘shish

- `/admin_content` buyrug‘i yoki Admin menyusidan kontent boshqaruvini oching.
- **Dars qo‘shish**, **Video darslik qo‘shish** yoki **Darsga link ulash** tugmasini tanlang.
- Oddiy darsda nomidan keyin matnni bir nechta Telegram xabari qilib yuboring yoki UTF-8 `.txt` fayl yuboring. Jami matn limiti 100 000 belgi; **💾 Matnni tugatish** tugmasi matn kiritishni yakunlaydi.
- Video darsda nom kiritilgach bot darhol Telegram videosini so‘raydi. Havolali darsda esa nomdan keyin `https://` yoki `http://` URL so‘raladi; bu ikki turda uzun matn kiritish shart emas.
- Foydalanuvchilar darsni **📚 Kiberxavfsizlik darslari** bo‘limidan ko‘radi. Uzun matnlar Telegram xabar limiti sabab bir necha sahifaga bo‘linadi.
- Jarayonni bekor qilish: `/cancel`.

## Majburiy kanal obunasi

Admin Telegram’da quyidagi buyruqlarni ishlatadi:

- `/channel_add @kanal_username` — majburiy kanal qo‘shish (yoki `/channel add @kanal_username`).
- `/channel` — kanallar va obuna holatini ko‘rish.
- `/subscription on` — majburiy obunani yoqish.
- `/subscription off` — vaqtincha o‘chirish.
- `/channel_remove @kanal_username` — kanalni ro‘yxatdan chiqarish.

Bot har bir kanalga administrator qilib qo‘shilishi kerak, aks holda Telegram a’zolikni tekshira olmasligi mumkin. Kanal username’siz bo‘lsa, buyruqdagi ID/havola usulini sozlash uchun admin chat ID va taklif havolasidan foydalanishi kerak.

## Dars yoki videoni o‘chirish

Admin panel → **🗑 Dars/video o‘chirish** → darsni tanlash → tasdiqlash. Bu darsni foydalanuvchilar ro‘yxatidan yashiradi (soft delete), ma’lumotlar bazasidan butunlay o‘chirmaydi.


## Qo‘shimcha funksiyalar

- **Darsni tahrirlash:** `/admin_content` → “✏️ Darsni tahrirlash” → darsni tanlang → nomi yoki matnini yangilang.
- **Dars qidiruvi:** `/lesson_search phishing` yoki `/lessons python`. Qidiruv dars nomi va matnidan natija topadi; tarmoq, parol, web, python, phishing, linux va OSINT kabi mavzular bilan qidiring.
- **Kengaytirilgan statistika:** `/admin stats` yoki `/stats` — foydalanuvchilar, quizlar, tugallangan darslar, faol admin darslari va sertifikatlar soni.
- **Avtomatik backup:** bot ishlayotganida har 24 soatda SQLite zaxira nusxasi `backups/` papkasiga yaratiladi. `python-telegram-bot[job-queue]` dependency o‘rnatilishi kerak.
- **Kurs va sertifikat:** darslarni tugallang, testda kamida 7 ball oling, so‘ng `/certificate` yuboring. Sertifikat olish uchun kamida 12 ta darsni tugatish va test talabi bajarilishi kerak; bu ta’limiy sertifikat, davlat diplomi emas.


## Yangi o‘quv funksiyalari

- `/xp` — XP, daraja va reytingdagi o‘rin. XP quiz natijalari, tugallangan darslar, CTF va kunlik bonuslardan hisoblanadi.
- `/leaderboard` — umumiy XP bo‘yicha TOP-10.
- `/learning_path` — asoslar, Python, tarmoq, web xavfsizligi va OSINT yo‘nalishlari bo‘yicha shaxsiy o‘quv yo‘li.
- `/cyberlab` — xavfsiz, lokal CTF mashqlari (mavjud `/ctf` bilan bir xil).
- `/daily` va `/streak` — kunlik vazifalar va muntazam o‘qish statistikasi.



## Barcha qo‘shilgan darslarni o‘chirish
Admin panel → Kontent boshqaruvi → **⚠️ Barcha qo‘shilgan darslarni o‘chirish** → tasdiqlash. Bu admin qo‘shgan faol dars/video/havolalarni foydalanuvchilar ro‘yxatidan yashiradi; kodga kiritilgan asosiy darslar saqlanadi.


## Premium bo‘limlar (admin yaratadi)

Admin panelidagi **🗂 Premium bo‘lim yaratish** orqali Networking, Bash, CTF, Pentest kabi bo‘limlarni yarating. So‘ng **➕ Premium bo‘limga mavzu qo‘shish** tugmasidan bo‘limni tanlab, mavzu nomi va matnini kiriting. Ko‘p qismli matnni `TAMOM` so‘zi bilan saqlang. Bu bo‘limlar faqat muddati faol Premium obunachilarga ochiladi; oddiy foydalanuvchilar qulf belgisi va Premium taklifini ko‘radi.


## Telegram Stars Premium to‘lovi

`/premium` bo‘limida Telegram Stars (`XTR`) orqali 7, 30 va 90 kunlik Premium tariflari mavjud. Namuna narxlar: 50, 150 va 350 Stars; `handlers/premium.py` ichidagi `STARS_PLANS` orqali o‘zgartiriladi. Stars raqamli xizmatlar to‘lovi uchun ishlatiladi, shu sababli provider token bo‘sh qoldiriladi. Bot `pre_checkout_query` payload, foydalanuvchi ID, valyuta va summani tekshiradi; Premium faqat Telegram yuborgan `successful_payment` update tasdiqlangach beriladi. Telegram charge ID `payments` jadvalida unique event sifatida qayd qilinib, takroriy update’lar qayta Premium bermaydi. Faol obuna qayta sotib olinsa, yangi kunlar amaldagi tugash sanasiga qo‘shiladi. Mavjud karta/chek orqali admin tasdiqlaydigan to‘lov yo‘li ham saqlangan.

Stars to‘lovlari uchun botda `/premium` tugmalaridan foydalaning. To‘lovlarni test qilish uchun Telegram botingizni ishga tushirib, haqiqiy Telegram Stars to‘lovi bilan tekshiring.


## Feature audit (2026-10-10)
- Interaktiv quiz: mavjud (`/quiz`, Premium quiz va admin savol qo‘shish).
- XP, darajalar va XP reytingi: mavjud (`/xp`, `/leaderboard`).
- Cyber Lab: mavjud (`/cyberlab`, offline CTF topshiriqlari).
- Premium: Stars 7/30/90 kun va karta chekini admin tasdiqlashi; muddati tekshiriladi.
- Sertifikat: mavjud (`/certificate`), talablar bajarilganda PDF beradi.
- Admin panel: mavjud; statistikaga muvaffaqiyatli to‘lovlar, Stars tushumi va kutilayotgan chek soni qo‘shildi.
- Kunlik vazifa va streak: mavjud (`/daily`, `/streak`).
- Referral: mavjud (`/referral`), o‘zini taklif qilish bloklanadi va mukofot bosqichlari bir martalik.
- Dars qidiruvi: mavjud (`/lesson_search <kalit_so‘z>`).

Stars tushumi admin panelda `XTR` birliklarida ko‘rsatiladi; bu bank hisobiga yechib olingan pul degani emas. Live Telegram to‘lov sinovi bot tokeni va Telegram muhitini talab qiladi.
