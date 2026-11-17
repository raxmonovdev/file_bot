# PDF Mega Bot

Telegram bot: PDF, Word va rasmlar bilan ishlaydi. Bepul foydalanuvchida kunlik limit bor, premiumda cheksiz.

Bu 1-bosqich (MVP). OCR, AI, parol, suv belgisi qo'yish va referal keyingi bosqich.

## Ishga tushirish

Python 3.11 yoki yangiroq kerak. Word → PDF uchun [LibreOffice](https://www.libreoffice.org/) ham kerak. Qolgan amallar LibreOffice siz ishlaydi.

```bash
cd pdf_mega_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

1. Telegramda @BotFather dan bot yarating va token oling.
2. `.env` faylini oching.
3. `BOT_TOKEN` ga tokenni yozing.
4. `ADMIN_IDS` ga o'z raqamingizni yozing (botda `/start` bosing, ID ni @userinfobot dan olasiz).
5. Narx va kartani xohlasangiz `.env` da o'zgartiring. Hozirgi narxlar sinov uchun.

```bash
python main.py
```

Tekshiruv (bot tokenisiz):

```bash
python tests/test_services.py
```

## Nima ishlaydi

- PDF → Word, Word → PDF, rasm → PDF, PDF → rasm
- Birlashtirish, bo'lish, siqish, sahifa o'chirish va burish
- Fayl nomi va premium uchun kichik rasm (thumbnail, 200 KB gacha)
- Kuniga 3 ta bepul amal (Toshkent vaqti bilan 00:00 da yangilanadi)
- Premium: Telegram Stars yoki karta cheki (admin tasdiqlaydi)
- Tillar: o'zbek, rus, ingliz
- Admin: `/admin` — statistika, to'lov, premium berish, xabar

Bepul natijaga kichik «PDF Mega Bot» yozuvi tushadi. Premiumda tushmaydi.

## Muhim

- Token va karta faqat `.env` da turadi.
- Foydalanuvchi fayli ishlovdan keyin `temp/` dan o'chiriladi.
- Oddiy Bot API 20 MB gacha fayl oladi. Bepul rejim 10 MB.
- Bitta odamda bir vaqtning o'zida bitta ish bor. Premium navbatda oldinroq o'tadi.
