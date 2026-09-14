#!/bin/bash
echo "🚀 Westeros Bot 24/7 Serverga o'rnatilmoqda..."

# Paketlarni yangilash
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv git

# Virtual muhit yaratish
python3 -m venv venv
source venv/bin/activate

# Kutubxonalarni o'rnatish
pip install --upgrade pip
pip install -r requirements.txt

# Systemd servisini o'rnatish
cp got_bot.service /etc/systemd/system/got_bot.service
systemctl daemon-reload
systemctl enable got_bot
systemctl restart got_bot

echo "✅ Bot muvaffaqiyatli ishga tushdi va 24/7 avtomatik rejimga o'tkazildi!"
echo "Holatni tekshirish uchun: systemctl status got_bot"
