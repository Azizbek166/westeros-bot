FROM python:3.12-slim

WORKDIR /app

# Tizim paketlari
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Talablar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Loyiha fayllari
COPY . .

# Botni ishga tushirish
CMD ["python", "bot.py"]
