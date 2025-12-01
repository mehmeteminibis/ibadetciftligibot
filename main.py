import telebot
from telebot import types
import sqlite3
import time
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import requests
from flask import Flask
from threading import Thread
import os
import json

# --- AYARLAR ---
BOT_TOKEN = "8329709843:AAHiIyYpEWz6Bl8IzzRvdbVpnMIoA3wogMQ"
BOT_USERNAME = "ibadetciftligi_bot" 
bot = telebot.TeleBot(BOT_TOKEN, threaded=False) 
DB_NAME = "ibadet_ciftligi.db"

# --- JSONBIN AYARLARI (YEDEKLEME İÇİN) ---
# Buraya JsonBin.io'dan aldığın kodları yapıştır:
JSONBIN_MASTER_KEY = "$2a$10$omG4QT.h/MV6wz5WTmZFsu/sL7j82fX8Sh64yr9xgK2ZYH/Pgw622" 
JSONBIN_BIN_ID = "692dfc3f43b1c97be9d14abb"

# --- FLASK SUNUCUSU ---
app = Flask('')

@app.route('/')
def home():
    return "Ibadet Ciftligi Botu Aktif!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- OYUN AYARLARI ---
COLORS = {
    "sari": {"name": "Sarı Civciv", "emoji": "💛"},
    "kirmizi": {"name": "Kırmızı Civciv", "emoji": "❤️"},
    "pembe": {"name": "Pembe Civciv", "emoji": "🩷"},
    "mavi": {"name": "Mavi Civciv", "emoji": "💙"},
    "yesil": {"name": "Yeşil Civciv", "emoji": "💚"},
    "turuncu": {"name": "Turuncu Civciv", "emoji": "🧡"},
    "mor": {"name": "Mor Civciv", "emoji": "💜"},
    "beyaz": {"name": "Beyaz Civciv", "emoji": "🤍"}
}

NAMAZ_VAKITLERI = ["Sabah", "Öğle", "İkindi", "Akşam", "Yatsı"]
NAMAZ_EMOJILERI = ["🌅", "☀️", "🌤️", "🌇", "🌌"]

GUNLUK_GOREVLER = [
    {"id": 0, "text": "50 'La İlahe İllallah' Çek", "emoji": "📿", "reward": 1},
    {"id": 1, "text": "50 'Salavat' Çek", "emoji": "🌹", "reward": 1},
    {"id": 2, "text": "50 'Estağfirullah' Çek", "emoji": "🤲", "reward": 1},
    {"id": 3, "text": "50 'Subhanallahi ve Bihamdihi' Çek", "emoji": "✨", "reward": 1},
    {"id": 4, "text": "1 Adet Kaza/Nafile Namazı Kıl", "emoji": "🕌", "reward": 2} 
]

# --- VERİTABANI İŞLEMLERİ ---
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        city TEXT,
        district TEXT,
        gold INTEGER DEFAULT 0,
        feed INTEGER DEFAULT 0,
        hens INTEGER DEFAULT 0,
        eggs_balance INTEGER DEFAULT 0,
        eggs_score INTEGER DEFAULT 0,
        last_prayer_date TEXT,
        prayed_mask TEXT DEFAULT "00000",
        last_task_date TEXT,
        tasks_mask TEXT DEFAULT "00000",
        last_egg_update REAL,
        referrer_id INTEGER,
        state TEXT DEFAULT 'main'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS chickens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        color_code TEXT,
        feed_count INTEGER DEFAULT 0
    )''')
    try: c.execute("SELECT state FROM users LIMIT 1")
    except: c.execute("ALTER TABLE users ADD COLUMN state TEXT DEFAULT 'main'")
    try: c.execute("SELECT eggs_score FROM users LIMIT 1")
    except: c.execute("ALTER TABLE users ADD COLUMN eggs_score INTEGER DEFAULT 0")
    conn.commit()
    conn.close()

# --- YEDEKLEME SİSTEMİ (JSONBIN) ---
def backup_to_cloud():
    """Veritabanını JSON'a çevirip Buluta Yükler"""
    print("☁️ Buluta yedekleme yapılıyor...")
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row # Dict gibi erişim için
        
        # Kullanıcıları çek
        users = [dict(row) for row in conn.execute("SELECT * FROM users").fetchall()]
        # Civcivleri çek
        chickens = [dict(row) for row in conn.execute("SELECT * FROM chickens").fetchall()]
        conn.close()

        data = {"users": users, "chickens": chickens}
        
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
        headers = {
            "Content-Type": "application/json",
            "X-Master-Key": JSONBIN_MASTER_KEY
        }
        
        req = requests.put(url, json=data, headers=headers)
        if req.status_code == 200:
            print("✅ Yedekleme BAŞARILI!")
        else:
            print(f"❌ Yedekleme Hatası: {req.text}")
    except Exception as e:
        print(f"❌ Yedekleme Hatası (Kod): {e}")

def restore_from_cloud():
    """Bot açılınca Buluttaki veriyi çekip DB'ye yazar"""
    print("☁️ Buluttan veri çekiliyor...")
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
        headers = {"X-Master-Key": JSONBIN_MASTER_KEY}
        
        req = requests.get(url, headers=headers)
        if req.status_code == 200:
            data = req.json().get("record", {})
            users = data.get("users", [])
            chickens = data.get("chickens", [])
            
            if not users and not chickens:
                print("⚠️ Bulut boş, yeni kurulum gibi devam ediliyor.")
                return

            conn = get_db_connection()
            c = conn.cursor()
            
            # Eski veriyi temizle (restore etmek için)
            c.execute("DELETE FROM users")
            c.execute("DELETE FROM chickens")
            
            # Kullanıcıları geri yükle
            for u in users:
                cols = ', '.join(u.keys())
                placeholders = ', '.join('?' * len(u))
                sql = f"INSERT INTO users ({cols}) VALUES ({placeholders})"
                c.execute(sql, list(u.values()))
                
            # Civcivleri geri yükle
            for ch in chickens:
                cols = ', '.join(ch.keys())
                placeholders = ', '.join('?' * len(ch))
                sql = f"INSERT INTO chickens ({cols}) VALUES ({placeholders})"
                c.execute(sql, list(ch.values()))
            
            conn.commit()
            conn.close()
            print(f"✅ Geri Yükleme Tamamlandı! ({len(users)} kullanıcı)")
        else:
            print(f"⚠️ Veri çekilemedi: {req.text}")
    except Exception as e:
        print(f"❌ Restore Hatası: {e}")

# --- YARDIMCI FONKSİYONLAR ---
def update_user_state(user_id, state):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET state=? WHERE user_id=?", (state, user_id))
        conn.commit()
        conn.close()
    except: pass

def check_daily_reset(user_id):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not user: return
        today = datetime.date.today().isoformat()
        updates = {}
        if user['last_prayer_date'] != today:
            updates['last_prayer_date'] = today
            updates['prayed_mask'] = "00000"
        if user['last_task_date'] != today:
            updates['last_task_date'] = today
            updates['tasks_mask'] = "00000"
        if updates:
            sql = "UPDATE users SET " + ", ".join([f"{k}=?" for k in updates.keys()]) + " WHERE user_id=?"
            vals = list(updates.values()) + [user_id]
            c.execute(sql, vals)
            conn.commit()
        conn.close()
    except: pass

def calculate_egg_production(user_id):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        produced_eggs = 0
        if user and user['hens'] > 0:
            now = time.time()
            last_update = user['last_egg_update'] if user['last_egg_update'] else now
            elapsed_seconds = now - last_update
            production_cycle = 14400 
            cycles = int(elapsed_seconds // production_cycle)
            if cycles > 0:
                produced_eggs = cycles * user['hens']
                new_balance = user['eggs_balance'] + produced_eggs
                new_score = user['eggs_score'] + produced_eggs
                new_time = last_update + (cycles * production_cycle)
                c.execute("UPDATE users SET eggs_balance=?, eggs_score=?, last_egg_update=? WHERE user_id=?", 
                          (new_balance, new_score, new_time, user_id))
                conn.commit()
        elif user:
            c.execute("UPDATE users SET last_egg_update=? WHERE user_id=?", (time.time(), user_id))
            conn.commit()
        conn.close()
        return produced_eggs
    except: return 0

# --- KLAVYELER (AYNI KODLAR) ---
def main_menu_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📜 Oyun Nasıl Oynanır?")
    markup.add("🕋 Namaz Takibi", "📝 Günlük Görevler")
    markup.add("🐥 Civciv Besle", "🏪 Civciv Pazarı")
    markup.add("🥚 Yumurta Pazarı", "📊 Genel Durum")
    markup.add("🏆 Haftalık Sıralama", "👥 Referans Sistemi")
    markup.add("📍 Konum Güncelle")
    return markup

def namaz_menu_keyboard(user_id):
    conn = get_db_connection()
    user = conn.execute("SELECT prayed_mask FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    mask = list(user['prayed_mask'] if user['prayed_mask'] else "00000")
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = []
    for idx, vakit in enumerate(NAMAZ_VAKITLERI):
        emoji = NAMAZ_EMOJILERI[idx]
        if idx < len(mask) and mask[idx] == '1': btn_text = f"✅ {vakit} (Kılındı)"
        else: btn_text = f"{emoji} {vakit} Kıldım"
        buttons.append(btn_text)
    markup.add(buttons[0], buttons[1])
    markup.add(buttons[2], buttons[3])
    markup.add(buttons[4])
    markup.add("🔙 Ana Menüye Dön")
    return markup

def gorev_menu_keyboard(user_id):
    conn = get_db_connection()
    user = conn.execute("SELECT tasks_mask FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    mask = list(user['tasks_mask'] if user['tasks_mask'] else "00000")
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for idx, gorev in enumerate(GUNLUK_GOREVLER):
        if idx < len(mask) and mask[idx] == '1': btn_text = f"✅ {gorev['text']} (Yapıldı)"
        else: btn_text = f"{gorev['emoji']} {gorev['text']} (+{gorev['reward']} Yem)"
        markup.add(btn_text)
    markup.add("🔙 Ana Menüye Dön")
    return markup

def civciv_pazar_keyboard(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    user_chicks = c.execute("SELECT color_code FROM chickens WHERE user_id=?", (user_id,)).fetchall()
    owned_colors = [row['color_code'] for row in user_chicks]
    conn.close()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    row_btns = []
    for code, details in COLORS.items():
        if code in owned_colors: btn_text = f"✅ {details['name']} (Var)"
        else: btn_text = f"{details['emoji']} {details['name']} (50 Altın)"
        row_btns.append(btn_text)
    for i in range(0, len(row_btns), 2):
        if i+1 < len(row_btns): markup.add(row_btns[i], row_btns[i+1])
        else: markup.add(row_btns[i])
    markup.add("🔙 Ana Menüye Dön")
    return markup

def civciv_besle_keyboard(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    chickens = c.execute("SELECT * FROM chickens WHERE user_id=?", (user_id,)).fetchall()
    conn.close()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    if not chickens:
        markup.add("🔙 Ana Menüye Dön")
        return markup, False
    for chick in chickens:
        color_info = COLORS.get(chick['color_code'], {"name": "Bilinmeyen", "emoji": "❓"})
        progress = chick['feed_count']
        btn_text = f"{color_info['emoji']} {color_info['name']} Civcivi Besle ({progress}/10)"
        markup.add(btn_text)
    markup.add("🔙 Ana Menüye Dön")
    return markup, True

def confirmation_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("✅ Evet, Yaptım", "❌ Vazgeç")
    return markup

def get_prayer_times_from_api(city, district):
    try:
        url = f"http://api.aladhan.com/v1/timingsByCity?city={city}&country=Turkey&method=13"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            timings = data['data']['timings']
            return {"Sabah": timings['Fajr'], "Öğle": timings['Dhuhr'], "İkindi": timings['Asr'], "Akşam": timings['Maghrib'], "Yatsı": timings['Isha']}
    except: return None

def scheduled_prayer_check():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        users = c.execute("SELECT user_id, city, district FROM users WHERE city IS NOT NULL").fetchall()
        now = datetime.datetime.now()
        current_time_str = now.strftime("%H:%M")
        for user in users:
            times = get_prayer_times_from_api(user['city'], user['district'])
            if times:
                for vakit_adi, vakit_saati in times.items():
                    if vakit_saati == current_time_str:
                        try:
                            msg = f"📢 **Ezan Vakti!**\n\n📍 {user['city']}/{user['district']} için **{vakit_adi}** vakti girdi. 🕌"
                            bot.send_message(user['user_id'], msg, parse_mode="Markdown")
                        except: pass
        conn.close()
    except: pass

# --- HANDLERS ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].isdigit():
        ref_candidate = int(args[1])
        if ref_candidate != user_id: referrer_id = ref_candidate

    conn = get_db_connection()
    c = conn.cursor()
    user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user:
        try:
            c.execute("INSERT INTO users (user_id, username, last_egg_update, referrer_id, state) VALUES (?, ?, ?, ?, ?)", 
                      (user_id, first_name, time.time(), referrer_id, 'start_location'))
            conn.commit()
            if referrer_id:
                try:
                    c.execute("UPDATE users SET feed = feed + 3 WHERE user_id=?", (referrer_id,))
                    conn.commit()
                    bot.send_message(referrer_id, f"🎉 Tebrikler! {first_name} referansınla katıldı. **+3 Yem** kazandın!")
                except: pass
            
            # YENİ KULLANICI GELDİĞİ İÇİN YEDEK ALALIM
            backup_to_cloud() 

            welcome_msg = (f"👋 **Selamun Aleyküm {first_name}!**\n\n🐮 **İbadet Çiftliği'ne Hoş Geldin!**\nSistemi başlatmak için öncelikle **Şehir ve İlçe** bilgisini girmen gerekiyor.\nLütfen aralarında boşluk bırakarak yaz (Örn: İstanbul Fatih):")
            msg = bot.send_message(message.chat.id, welcome_msg, parse_mode="Markdown", reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, save_location)
        except: bot.send_message(message.chat.id, f"👋 Tekrar hoş geldin {first_name} kardeşim!", reply_markup=main_menu_keyboard())
    else:
        try:
            c.execute("UPDATE users SET username=?, state='main' WHERE user_id=?", (first_name, user_id))
            conn.commit()
            bot.send_message(message.chat.id, f"👋 Tekrar hoş geldin {first_name} kardeşim!", reply_markup=main_menu_keyboard())
        except: pass
    conn.close()

def save_location(message):
    try:
        location_text = message.text.strip().split()
        if len(location_text) < 2:
            msg = bot.send_message(message.chat.id, "⚠️ Lütfen Şehir ve İlçe bilgisini tam giriniz.\nÖrnek: *Ankara Çankaya*")
            bot.register_next_step_handler(msg, save_location)
            return
        city = location_text[0].capitalize()
        district = location_text[1].capitalize()
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET city=?, district=?, state='main' WHERE user_id=?", (city, district, message.from_user.id))
        conn.commit()
        conn.close()
        # KONUM DEĞİŞTİ YEDEK AL
        backup_to_cloud()
        bot.send_message(message.chat.id, f"✅ Konum kaydedildi: {city} / {district}\n\nİyi eğlenceler! 🚜", reply_markup=main_menu_keyboard())
    except: bot.send_message(message.chat.id, "Bir hata oluştu. Lütfen tekrar /start yazınız.")

@bot.message_handler(func=lambda message: True)
def handle_menus(message):
    user_id = message.from_user.id
    text = message.text
    first_name = message.from_user.first_name
    conn = get_db_connection()
    user_data = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user_data:
        conn.close()
        send_welcome(message)
        return
    conn.close()
    
    check_daily_reset(user_id)
    new_eggs = calculate_egg_production(user_id)
    if new_eggs > 0: bot.send_message(user_id, f"🥚 Kümeste **{new_eggs}** yeni yumurta birikmiş!", parse_mode="Markdown")

    if text == "🔙 Ana Menüye Dön" or text == "🔙 Ana Menü":
        update_user_state(user_id, 'main')
        bot.send_message(user_id, "🏡 Ana Menü:", reply_markup=main_menu_keyboard())
    elif text == "📜 Oyun Nasıl Oynanır?":
        update_user_state(user_id, 'info')
        bot.send_message(user_id, "📜 **OYUN NASIL OYNANIR?**\n\n(Burada oyun kuralları yazar...)", parse_mode="Markdown")
    elif text == "🕋 Namaz Takibi":
        update_user_state(user_id, 'namaz')
        conn = get_db_connection()
        user = conn.execute("SELECT gold FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        bot.send_message(user_id, f"🕋 **NAMAZ TAKİBİ**\nBugünkü namazlarını işaretle.\n💰 Altın: **{user['gold']}**", parse_mode="Markdown", reply_markup=namaz_menu_keyboard(user_id))
    elif text == "📝 Günlük Görevler":
        update_user_state(user_id, 'tasks')
        conn = get_db_connection()
        user = conn.execute("SELECT feed FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        bot.send_message(user_id, f"📝 **GÜNLÜK GÖREVLER**\nZikirler +1 Yem, Namaz görevi +2 Yem.\n🐛 Yem: **{user['feed']}**", parse_mode="Markdown", reply_markup=gorev_menu_keyboard(user_id))
    elif text == "🏪 Civciv Pazarı" or text == "🛒 Civciv Pazarı":
        update_user_state(user_id, 'market')
        conn = get_db_connection()
        user = conn.execute("SELECT gold, hens FROM users WHERE user_id=?", (user_id,)).fetchone()
        c = conn.cursor()
        chick_count = c.execute("SELECT COUNT(*) FROM chickens WHERE user_id=?", (user_id,)).fetchone()[0]
        conn.close()
        bot.send_message(user_id, f"🏪 **PAZAR**\n💰 Bakiye: {user['gold']}\n🐣 Civciv: {chick_count}/8", parse_mode="Markdown", reply_markup=civciv_pazar_keyboard(user_id))
    elif text == "🐥 Civciv Besle":
        update_user_state(user_id, 'feed')
        conn = get_db_connection()
        user = conn.execute("SELECT feed FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        markup, has_chick = civciv_besle_keyboard(user_id)
        if not has_chick: bot.send_message(user_id, "😔 Hiç civcivin yok!", reply_markup=markup)
        else: bot.send_message(user_id, f"🐥 **BESLEME**\n🐛 Yem: {user['feed']}", parse_mode="Markdown", reply_markup=markup)
    elif text == "🥚 Yumurta Pazarı":
        update_user_state(user_id, 'egg_market')
        conn = get_db_connection()
        user = conn.execute("SELECT eggs_balance FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("💰 Tüm Yumurtaları Sat")
        markup.add("🔙 Ana Menüye Dön")
        bot.send_message(user_id, f"🥚 **SATIŞ**\nYumurtan: {user['eggs_balance']}\nSatmak için sayı yaz veya butona bas.", parse_mode="Markdown", reply_markup=markup)
    elif text == "📊 Genel Durum":
        update_user_state(user_id, 'status')
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        bot.send_message(user_id, f"📊 **DURUM**\n👤 {user['username']}\n💰 {user['gold']} Altın\n🐓 {user['hens']} Tavuk", parse_mode="Markdown")
    elif text == "🏆 Haftalık Sıralama":
        update_user_state(user_id, 'ranking')
        conn = get_db_connection()
        top_users = conn.execute("SELECT username, eggs_score FROM users ORDER BY eggs_score DESC LIMIT 10").fetchall()
        conn.close()
        msg = "🏆 **SIRALAMA**\n"
        for i, u in enumerate(top_users, 1): msg += f"{i}. {u['username']} - {u['eggs_score']}\n"
        bot.send_message(user_id, msg)
    elif text == "👥 Referans Sistemi":
        update_user_state(user_id, 'referral')
        bot.send_message(user_id, f"Davet Linkin:\nhttps://t.me/{BOT_USERNAME}?start={user_id}")
    elif text == "📍 Konum Güncelle":
        msg = bot.send_message(user_id, "Yeni konum (Şehir İlçe):", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, save_location)
    
    # --- İŞLEMLER ---
    elif "Kıldım" in text:
        # Namaz işaretleme
        conn = get_db_connection()
        c = conn.cursor()
        user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        mask = list(user['prayed_mask'])
        found = False
        for idx, vakit in enumerate(NAMAZ_VAKITLERI):
            if vakit in text and mask[idx] == '0':
                mask[idx] = '1'
                c.execute("UPDATE users SET prayed_mask=?, gold=gold+10 WHERE user_id=?", ("".join(mask), user_id))
                conn.commit()
                bot.send_message(user_id, "✅ +10 Altın!", reply_markup=namaz_menu_keyboard(user_id))
                found = True
                backup_to_cloud() # ÖNEMLİ İŞLEM, YEDEK AL
                break
        conn.close()
        if not found: bot.send_message(user_id, "Zaten işaretli veya geçersiz.", reply_markup=namaz_menu_keyboard(user_id))

    elif "Civciv (50 Altın)" in text:
        # Satın alma
        conn = get_db_connection()
        c = conn.cursor()
        user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        cnt = c.execute("SELECT COUNT(*) FROM chickens WHERE user_id=?", (user_id,)).fetchone()[0]
        if cnt < 8 and user['gold'] >= 50:
            color = next((k for k,v in COLORS.items() if v['name'] in text), None)
            if color:
                c.execute("UPDATE users SET gold=gold-50 WHERE user_id=?", (user_id,))
                c.execute("INSERT INTO chickens (user_id, color_code) VALUES (?, ?)", (user_id, color))
                conn.commit()
                bot.send_message(user_id, "✅ Civciv alındı!", reply_markup=civciv_pazar_keyboard(user_id))
                backup_to_cloud()
        else: bot.send_message(user_id, "Yetersiz bakiye veya kümes dolu.")
        conn.close()

    elif "Civcivi Besle" in text:
        # Besleme
        conn = get_db_connection()
        c = conn.cursor()
        user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        chickens = c.execute("SELECT * FROM chickens WHERE user_id=?", (user_id,)).fetchall()
        target = next((ch for ch in chickens if f"{COLORS[ch['color_code']]['name']} Civcivi Besle ({ch['feed_count']}/10)" in text), None)
        
        if target and user['feed'] > 0:
            c.execute("UPDATE chickens SET feed_count=feed_count+1 WHERE id=?", (target['id'],))
            c.execute("UPDATE users SET feed=feed-1 WHERE user_id=?", (user_id,))
            conn.commit()
            
            # Tavuk oldu mu kontrolü
            if target['feed_count'] + 1 >= 10:
                c.execute("DELETE FROM chickens WHERE id=?", (target['id'],))
                c.execute("UPDATE users SET hens=hens+1 WHERE user_id=?", (user_id,))
                conn.commit()
                bot.send_message(user_id, "🐓 Büyüdü ve Tavuk oldu!")
            else:
                bot.send_message(user_id, "✅ Yemlendi.")
            
            backup_to_cloud()
            new_kb, _ = civciv_besle_keyboard(user_id)
            bot.send_message(user_id, "Devam:", reply_markup=new_kb)
        else: bot.send_message(user_id, "Yem yok veya civciv bulunamadı.")
        conn.close()
    
    elif "Tüm Yumurtaları Sat" in text or (text.isdigit() and int(text) >= 10):
        # Satış
        amount = int(text) if text.isdigit() else 999999
        conn = get_db_connection()
        c = conn.cursor()
        user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        sell_amount = user['eggs_balance'] if amount == 999999 else amount
        
        if user['eggs_balance'] >= sell_amount and sell_amount >= 10:
            earn = int(sell_amount * 0.10)
            if earn < 1: earn = 1
            c.execute("UPDATE users SET eggs_balance=eggs_balance-?, gold=gold+? WHERE user_id=?", (sell_amount, earn, user_id))
            conn.commit()
            bot.send_message(user_id, f"✅ {sell_amount} satıldı, +{earn} Altın!", reply_markup=main_menu_keyboard())
            backup_to_cloud()
        else: bot.send_message(user_id, "Yetersiz yumurta (Min 10).")
        conn.close()

    elif "(+" in text and "Yem)" in text:
         # Görev onayı için butona basıldı
        target_task_id = -1
        for g in GUNLUK_GOREVLER:
            if g['text'] in text:
                target_task_id = g['id']
                break
        if target_task_id != -1:
            msg = bot.send_message(user_id, f"❓ Gerçekten yaptın mı?\n_{GUNLUK_GOREVLER[target_task_id]['text']}_", 
                                   parse_mode="Markdown", reply_markup=confirmation_keyboard())
            bot.register_next_step_handler(msg, process_task_confirmation, target_task_id)

def process_task_confirmation(message, task_id):
    user_id = message.from_user.id
    if message.text == "✅ Evet, Yaptım":
        conn = get_db_connection()
        c = conn.cursor()
        user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        mask = list(user['tasks_mask'])
        if mask[task_id] == '0':
            mask[task_id] = '1'
            reward = GUNLUK_GOREVLER[task_id]['reward']
            c.execute("UPDATE users SET tasks_mask=?, feed=feed+? WHERE user_id=?", ("".join(mask), reward, user_id))
            conn.commit()
            bot.send_message(user_id, f"✅ +{reward} Yem!", reply_markup=gorev_menu_keyboard(user_id))
            backup_to_cloud()
        else: bot.send_message(user_id, "Zaten yapıldı.", reply_markup=gorev_menu_keyboard(user_id))
        conn.close()
    else: bot.send_message(user_id, "İptal.", reply_markup=gorev_menu_keyboard(user_id))


# --- ZAMANLAYICI VE BAŞLATMA ---
def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(scheduled_prayer_check, 'interval', minutes=15)
    
    # 15 dakikada bir otomatik yedekle
    scheduler.add_job(backup_to_cloud, 'interval', minutes=15)

    def reset_weekly():
        if datetime.datetime.now().weekday() == 6:
            conn = get_db_connection()
            conn.execute("UPDATE users SET eggs_score = 0")
            conn.commit()
            conn.close()
            backup_to_cloud()
            
    scheduler.add_job(reset_weekly, 'cron', day_of_week='sun', hour=23, minute=59)
    scheduler.start()

if __name__ == "__main__":
    init_db()
    # 1. ÖNCE BULUTTAN VERİYİ ÇEK (RESTORE)
    restore_from_cloud()
    
    start_scheduler()
    keep_alive()
    
    try:
        bot.remove_webhook()
        time.sleep(1)
    except: pass
        
    print("Bot ve Web Server başlatıldı...")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=20, skip_pending=True)
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(5)

