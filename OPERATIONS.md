# Ishlatish va texnik xizmat

## Windows PowerShell
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt
Copy-Item .env.example .env
# .env ichida BOT_TOKEN, ADMIN_IDS va karta rekvizitlarini sozlang
python -m compileall -q .
pytest -q
python bot.py
```

## Premium manual payment
- `PAYMENT_CARD_NUMBER` bo‘sh bo‘lsa xarid boshlanmaydi.
- Faqat rasm yoki PDF chek qabul qilinadi.
- Chek tasdiqlash tugmalari faqat `ADMIN_IDS` dagi adminlarga ishlaydi.
- Admin chekni tashqi bank ilovasida tekshiradi va summaga mos muddatni tanlaydi.
- DB tranzaksiyasi bir chekni faqat bir marta tasdiqlashni ta’minlaydi.
- To‘lov haqiqiyligini bot avtomatik tasdiqlamaydi; bu manual tekshiruv.

## Admin kontent boshqaruvi
AI Ustoz hamda darslik/video/havola qo‘shish funksiyalari olib tashlangan. Admin faqat test va savol-javob qo‘shadi.

## Backup / restore
- Admin buyruqlari orqali mavjud backup funksiyasidan foydalaning.
- Backup fayllarini alohida, kirish huquqi cheklangan joyda saqlang.
- Restore oldidan joriy database backup oling.
- Restore’dan so‘ng `PRAGMA quick_check` natijasi `ok` ekanini tekshiring.

## Nosozlik
- Token yoki admin xatosida `.env` formatini tekshiring; tokenni logga yoki chatga yozmang.
- - Tashqi DNS/IP/GitHub API xatolari vaqtinchalik bo‘lishi mumkin.
