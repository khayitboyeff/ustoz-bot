# CyberUstozBot — Ubuntu VPS deploy qo'llanmasi

## Tavsiya

Doimiy ishlash va SQLite faylini saqlash uchun Ubuntu 22.04/24.04 VM (masalan, Oracle Cloud Always Free shartlariga mos Compute VM) ishlating. Bepul resurslar, ro'yxatdan o'tish talablari va mavjudligi provayderga bog'liq; bu 24/7 ishlash kafolati emas. VM hisobiga kirishda yosh/identifikatsiya talablari bo'lishi mumkin — ularni chetlab o'tmang, zarur bo'lsa ota-ona/vasiy yordamidan foydalaning.

Telegram bot `getUpdates` polling ishlatadi, shuning uchun odatda kiruvchi port ochish yoki domen talab qilinmaydi. Serverdan Telegram API'ga chiqish (HTTPS/443) ishlashi kerak.

## 1. Serverda loyiha fayllarini joylashtirish

1. ZIP faylni o'zingizning Ubuntu VM'ingizga xavfsiz usulda yuklang.
2. Arxivni ochib, ichidagi `CyberUstozBot` papkasini `/opt/cyberustozbot/app` joyiga joylashtiring.
3. Loyiha papkasida `.env.example` faylidan `.env` nusxa oling:

```bash
cd /opt/cyberustozbot/app
cp .env.example .env
nano .env
```

`BOT_TOKEN` o'rniga BotFather bergan haqiqiy tokenni va `ADMIN_IDS` o'rniga o'zingizning Telegram numeric ID'ingizni kiriting. Tokenni hech kimga yubormang. `DATABASE_PATH` qiymatini o'zgartirmang — u SQLite bazasini doimiy loyiha papkasida saqlaydi.

## 2. O'rnatish va xizmatni ishga tushirish

```bash
sudo bash deploy-ubuntu.sh
```

Skript Python virtual muhitini yaratadi, `requirements.txt` ni o'rnatadi va `systemd` xizmatini yoqadi. Server qayta yuklansa bot avtomatik ishga tushadi.

## 3. Tekshirish

```bash
sudo systemctl status cyberustozbot
sudo journalctl -u cyberustozbot -n 100 --no-pager
sudo journalctl -u cyberustozbot -f
```

Telegram'da botga `/start`, `/premium` yuboring. Haqiqiy Stars to'lovini tekshirishda faqat o'zingiz nazorat qiladigan bot va Telegram test tartibidan foydalaning; real to'lov tasdiqlanmagan bo'lsa, Premium faollashgan deb hisoblamang.

## SQLite va backup

- SQLite: `/opt/cyberustozbot/app/database/cyberlearn.db`
- Backup papkasi: `/opt/cyberustozbot/app/backups/`
- Bot ishga tushgach kunlik backup rejalashtiriladi (`job-queue` dependency talab qilinadi).
- Backup'ni faqat shu VM'da saqlash server yo'qolishi holatidan himoya qilmaydi. Muntazam ravishda shifrlangan nusxani alohida, ishonchli joyga yuklab oling va tiklashni sinang.
- `.env`, `.db`, chek rasmlari yoki backup'larni ommaviy repository'ga joylamang.

## Yangilash

Avval xizmatni to'xtating va backup oling. Yangi kodni joylashtirgach, `.env` va `database/` papkasini ustidan yozmang. Keyin:

```bash
sudo systemctl stop cyberustozbot
sudo -u cyberbot /opt/cyberustozbot/app/.venv/bin/pip install -r /opt/cyberustozbot/app/requirements.txt
sudo systemctl start cyberustozbot
sudo journalctl -u cyberustozbot -n 100 --no-pager
```

## Muammolarni hal qilish

- `BOT_TOKEN topilmadi`: `.env` fayl nomi aynan `.env` ekanini tekshiring.
- `Conflict: terminated by other getUpdates request`: shu token bilan boshqa joyda bot ishlamayotganini tekshiring; bitta polling nusxasi ishlasin.
- `Permission denied`: `sudo chown -R cyberbot:cyberbot /opt/cyberustozbot/app` va `.env` uchun `chmod 600` qiling.
- `No module named telegram`: `requirements.txt` ni virtual muhitga qayta o'rnating.
- SQLite fayli yo'qolmasligi uchun botni ephemeral filesystem hostingga ko'chirmang.

## Xavfsizlik eslatmasi

Bu paket server yaratmaydi va Oracle hisobini ochmaydi; u serverga joylashga tayyorlaydi. Bepul VM mavjudligi va akkaunt tasdiqlanishi provayder shartlariga bog'liq. Bot kodining barcha to'lov oqimlari real Telegram to'lovi bilan sinovdan o'tkazilmaguncha ommaviy foydalanishga tayyor deb hisoblanmasin.
