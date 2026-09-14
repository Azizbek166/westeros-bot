# 👑 THE IRON THRONE — 500+ PLAYER WESTEROS MMORPG

Telegram uchun Game of Thrones olamiga asoslangan keng masshtabli strategik MMORPG bot.

---

## 🎮 Asosiy Tizimlar

1. **50 ta Westeros Xonadoni (`data/houses_data.py`):**
   - 8 ta mintaqa (The North, Westerlands, Crownlands, The Reach, Dorne, The Vale, Riverlands, Iron Islands, Stormlands).
   - Har bir xonadonning maxsus askari (Direwolf Guard, Rose Knights, Crimson Lancers va h.k.).
2. **Westeros Xaritasi va 21 ta Qal'a (`data/map_data.py`):**
   - Winterfell, King's Landing, Casterly Rock, Highgarden, Sunspear, The Eyrie, Riverrun, Pyke, Storm's End va boshqalar.
3. **Tosh-Qaychi-Qog'oz (RPS) Taktik Jang Formulasi (`core/battle_engine.py`):**
   - Otliq > Kamonchi (+40%)
   - Nayzachi > Otliq (+40%)
   - Kamonchi > Piyoda (+30%)
   - Piyoda > Nayzachi (+30%)
4. **Iqtisodiyot va Oziq-ovqat iste'moli (`core/economy_engine.py`):**
   - 🪙 Oltin, 🌾 Oziq-ovqat, ⛓️ Temir. Armiya oziq-ovqat iste'mol qiladi.
5. **Yurish Vaqti (March Time) va Tinchlik Qalqoni (Peace Shield):**
   - Yangi o'yinchilarga 3 kunlik himoya qalqoni.
   - Hujumlar real vaqtda yetib boradi (March Timer).
6. **Questlar va Citadel Viktorinasi (`data/quests_data.py`, `data/quiz_data.py`):**
   - Asosiy hikoya, kunlik vazifalar, 1024 ta Citadel viktorina savoli va 500 ta Kengash qarorlari.
7. **White Walkers Global Boss Reydi va Temir Taxt Hukmronligi:**
   - 250,000 lik zombi armiyasiga qarshi Buyuk Ittifoq (Great Alliance).

---

## 🚀 Ishga Tushirish

### 1. Bog'liqliklarni o'rnatish:
```bash
pip install -r requirements.txt
```

### 2. Sozlash:
`config.py` yoki `.env` faylida `BOT_TOKEN` va kerak bo'lsa `DATABASE_URL` ni kiriting (standart holatda `aiosqlite` bilan darhol ishlaydi, ishlab chiqarish uchun PostgreSQL ga ulanadi).

### 3. Botni ishga tushirish:
```bash
python bot.py
```
