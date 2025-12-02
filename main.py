import telebot
from telebot import types
import sqlite3
import time
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import json
from flask import Flask
from threading import Thread
import os

# --- AYARLAR ---
BOT_TOKEN = "8329709843:AAHiIyYpEWz6Bl8IzzRvdbVpnMIoA3wogMQ"
BOT_USERNAME = "ibadetciftligi_bot" 
# Threaded=False veritabanı kilitlenmesini önler
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
DB_NAME = "ibadet_ciftligi.db"

# --- JSONBIN AYARLARI (YEDEKLEME İÇİN) ---
# JsonBin.io'dan aldığın kodları buraya yapıştır:
JSONBIN_MASTER_KEY = "$2a$10$omG4QT.h/MV6wz5WTmZFsu/sL7j82fX8Sh64yr9xgK2ZYH/Pgw622" 
JSONBIN_BIN_ID = "692dfc3f43b1c97be9d14abb"

# --- FLASK SUNUCUSU (RENDER İÇİN) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot Calisiyor!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Renkler ve Emojiler 
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

# Görev Listesi ve Ödülleri
GUNLUK_GOREVLER = [
    {"id": 0, "text": "50 'La İlahe İllallah' Çek", "emoji": "📿", "reward": 1},
    {"id": 1, "text": "50 'Salavat' Çek", "emoji": "🌹", "reward": 1},
    {"id": 2, "text": "50 'Estağfirullah' Çek", "emoji": "🤲", "reward": 1},
    {"id": 3, "text": "50 'Subhanallahi ve Bihamdihi' Çek", "emoji": "✨", "reward": 1},
    {"id": 4, "text": "1 Adet Kaza/Nafile Namazı Kıl", "emoji": "🕌", "reward": 2}
]

# --- VERİTABANI İŞLEMLERİ ---
def get_db_connection():
    # Timeout=30 veritabanı kilitlenmesini önler
    conn = sqlite3.connect(DB_NAME, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Kullanıcılar Tablosu
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
    
    # Civcivler Tablosu
    c.execute('''CREATE TABLE IF NOT EXISTS chickens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        color_code TEXT,
        feed_count INTEGER DEFAULT 0
    )''')
    
    # --- OTOMATİK ONARIM BLOĞU ---
    try:
        c.execute("SELECT state FROM users LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE users ADD COLUMN state TEXT DEFAULT 'main'")
        
    try:
        c.execute("SELECT eggs_score FROM users LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE users ADD COLUMN eggs_score INTEGER DEFAULT 0")

    conn.commit()
    conn.close()

# --- YEDEKLEME SİSTEMİ (JSONBIN) ---
def backup_to_cloud():
    """Veritabanını JSON'a çevirip Buluta Yükler"""
    try:
        conn = get_db_connection()
        
        users_query = conn.execute("SELECT * FROM users").fetchall()
        users = [dict(row) for row in users_query]
        
        chickens_query = conn.execute("SELECT * FROM chickens").fetchall()
        chickens = [dict(row) for row in chickens_query]
        
        conn.close()

        data = {"users": users, "chickens": chickens}
        
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
        headers = {
            "Content-Type": "application/json",
            "X-Master-Key": JSONBIN_MASTER_KEY
        }
        requests.put(url, json=data, headers=headers)
    except:
        pass 

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
                print("⚠️ Bulut boş.")
                return

            conn = get_db_connection()
            c = conn.cursor()
            
            c.execute("DELETE FROM users")
            c.execute("DELETE FROM chickens")
            
            for u in users:
                cols = ', '.join(u.keys())
                placeholders = ', '.join('?' * len(u))
                sql = f"INSERT INTO users ({cols}) VALUES ({placeholders})"
                c.execute(sql, list(u.values()))
                
            for ch in chickens:
                cols = ', '.join(ch.keys())
                placeholders = ', '.join('?' * len(ch))
                sql = f"INSERT INTO chickens ({cols}) VALUES ({placeholders})"
                c.execute(sql, list(ch.values()))
            
            conn.commit()
            conn.close()
            print("✅ Veriler geri yüklendi.")
    except Exception as e:
        print(f"Restore Hatası: {e}")

# --- YARDIMCI FONKSİYONLAR ---

def update_user_state(user_id, state):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET state=? WHERE user_id=?", (state, user_id))
        conn.commit()
        conn.close()
    except:
        pass

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
    except:
        pass

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
            
            production_cycle = 14400 # 4 saat
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
    except:
        return 0

# --- KLAVYELER ---

def main_menu_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📜 Oyun Nasıl Oynanır?")
    markup.add("🕋 Namaz Takibi", "📝 Günlük Görevler")
    markup.add("🐥 Civciv Besle", "🛒 Civciv Pazarı")
    markup.add("🥚 Yumurta Pazarı", "📊 Genel Durum")
    markup.add("🏆 Haftalık Sıralama", "👥 Referans Sistemi")
    markup.add("📍 Konum Güncelle")
    return markup

def namaz_menu_keyboard(user_id):
    conn = get_db_connection()
    user = conn.execute("SELECT prayed_mask FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    mask = list(user['prayed_mask'])
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = []
    
    for idx, vakit in enumerate(NAMAZ_VAKITLERI):
        emoji = NAMAZ_EMOJILERI[idx]
        if mask[idx] == '1':
            btn_text = f"✅ {vakit} (Kılındı)"
        else:
            btn_text = f"{emoji} {vakit} Kıldım"
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
    mask = list(user['tasks_mask'])
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    
    for idx, gorev in enumerate(GUNLUK_GOREVLER):
        if mask[idx] == '1':
            btn_text = f"✅ {gorev['text']} (Yapıldı)"
        else:
            btn_text = f"{gorev['emoji']} {gorev['text']} (+{gorev['reward']} Yem)"
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
        if code in owned_colors:
            btn_text = f"✅ {details['name']} (Var)"
        else:
            btn_text = f"{details['emoji']} {details['name']} (50 Altın)"
        row_btns.append(btn_text)
        
    for i in range(0, len(row_btns), 2):
        if i+1 < len(row_btns):
            markup.add(row_btns[i], row_btns[i+1])
        else:
            markup.add(row_btns[i])
            
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
        color_info = COLORS[chick['color_code']]
        progress = chick['feed_count']
        btn_text = f"{color_info['emoji']} {color_info['name']} Civcivi Besle ({progress}/10)"
        markup.add(btn_text)
        
    markup.add("🔙 Ana Menüye Dön")
    return markup, True

def confirmation_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("✅ Evet, Yaptım", "❌ Vazgeç")
    return markup

# --- NAMAZ VAKTİ SERVİSİ ---
def get_prayer_times_from_api(city, district):
    try:
        url = f"http://api.aladhan.com/v1/timingsByCity?city={city}&country=Turkey&method=13"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            timings = data['data']['timings']
            return {
                "Sabah": timings['Fajr'],
                "Öğle": timings['Dhuhr'],
                "İkindi": timings['Asr'],
                "Akşam": timings['Maghrib'],
                "Yatsı": timings['Isha']
            }
    except Exception as e:
        print(f"API Hatası: {e}")
    return None

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
                            msg = f"📢 **Ezan Vakti!**\n\n📍 {user['city']}/{user['district']} için **{vakit_adi}** vakti girdi.\n\nNamazını kıldıktan sonra 'Namaz Takibi' menüsünden işaretlemeyi unutma! +10 Altın seni bekliyor. 🕌"
                            bot.send_message(user['user_id'], msg, parse_mode="Markdown")
                        except:
                            pass
        conn.close()
    except:
        pass

# --- BOT HANDLERS ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].isdigit():
        ref_candidate = int(args[1])
        if ref_candidate != user_id:
            referrer_id = ref_candidate

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
                except:
                    pass
            
            # YENİ KULLANICI -> YEDEK AL
            backup_to_cloud()
            
            welcome_msg = (
                f"👋 **Selamun Aleyküm {first_name}!**\n\n"
                f"🐮 **İbadet Çiftliği'ne Hoş Geldin!**\n"
                f"Bu bot, hem ibadetlerini takip etmeni sağlayan hem de bu süreçte çiftliğini geliştirip civcivler besleyebileceğin eğlenceli ve manevi bir oyundur.\n\n"
                f"Namazlarını kıl, zikirlerini çek, altınları topla ve en büyük yumurta üreticisi sen ol! 🏆\n\n"
                f"Sistemi başlatmak için öncelikle **Şehir ve İlçe** bilgisini girmen gerekiyor.\n"
                f"Lütfen aralarında boşluk bırakarak yaz (Örn: İstanbul Fatih):"
            )
            msg = bot.send_message(message.chat.id, welcome_msg, parse_mode="Markdown", reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, save_location)
        except sqlite3.IntegrityError:
             bot.send_message(message.chat.id, f"👋 Tekrar hoş geldin {first_name} kardeşim!", reply_markup=main_menu_keyboard())
    else:
        try:
            c.execute("UPDATE users SET username=?, state='main' WHERE user_id=?", (first_name, user_id))
            conn.commit()
            bot.send_message(message.chat.id, f"👋 Tekrar hoş geldin {first_name} kardeşim!", reply_markup=main_menu_keyboard())
        except:
             bot.send_message(message.chat.id, f"👋 Tekrar hoş geldin {first_name} kardeşim!", reply_markup=main_menu_keyboard())
    
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
        
        # KONUM DEĞİŞTİ -> YEDEK AL
        backup_to_cloud()
        
        bot.send_message(message.chat.id, f"✅ Konum kaydedildi: {city} / {district}\n\nArtık hazırsın! Menüden 'Oyun Nasıl Oynanır' butonuna basarak sistemi öğrenebilirsin. İyi eğlenceler! 🚜", reply_markup=main_menu_keyboard())
    except Exception as e:
        bot.send_message(message.chat.id, "Bir hata oluştu. Lütfen tekrar /start yazınız.")

# --- ANA MESAJ YÖNETİCİSİ ---
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

    try:
        if user_data['username'] != first_name:
            conn.execute("UPDATE users SET username=? WHERE user_id=?", (first_name, user_id))
            conn.commit()
    except:
        pass

    conn.close()

    check_daily_reset(user_id)
    new_eggs = calculate_egg_production(user_id)
    if new_eggs > 0:
        bot.send_message(user_id, f"🥚 Kümeste **{new_eggs}** yeni yumurta birikmiş!", parse_mode="Markdown")
        
    conn = get_db_connection()
    try:
        user_state_row = conn.execute("SELECT state FROM users WHERE user_id=?", (user_id,)).fetchone()
        user_state = user_state_row['state'] if user_state_row else 'main'
    except:
        user_state = 'main'
    conn.close()

    # --- ÖZEL DURUM: YUMURTA PAZARINDA SAYI GİRİŞİ ---
    if user_state == 'egg_market' and text.isdigit():
        amount = int(text)
        if amount < 10:
            bot.send_message(user_id, "⚠️ Minimum 10 yumurta satabilirsin.")
            return

        conn = get_db_connection()
        c = conn.cursor()
        user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        
        if user['eggs_balance'] >= amount:
            earn = int(amount * 0.10)
            if earn < 1: earn = 1
            
            c.execute("UPDATE users SET eggs_balance=eggs_balance-?, gold=gold+? WHERE user_id=?", (amount, earn, user_id))
            conn.commit()
            bot.send_message(user_id, f"✅ {amount} yumurta satıldı!\n💰 Kazanılan: **{earn} Altın**\n🥚 Kalan: {user['eggs_balance']-amount}", parse_mode="Markdown")
            
            # SATIŞ -> YEDEK AL
            backup_to_cloud()
        else:
            bot.send_message(user_id, f"⚠️ Yetersiz yumurta! Sahip olduğun: {user['eggs_balance']}")
        conn.close()
        return

    # --- NORMAL MENÜLER ---
    
    if text == "🔙 Ana Menüye Dön" or text == "🔙 Ana Menü":
        update_user_state(user_id, 'main')
        bot.send_message(user_id, "🏡 Ana Menü:", reply_markup=main_menu_keyboard())

    elif text == "📜 Oyun Nasıl Oynanır?":
        update_user_state(user_id, 'info')
        # BURASI DÜZELTİLDİ: Orijinal metin geri eklendi
        info_text = (
            "📜 **OYUN NASIL OYNANIR?**\n\n"
            "1️⃣ **Namaz Takibi:** 5 Vakit namazını kıldıkça işaretle, her vakit için **10 Altın** kazan! 💰\n"
            "2️⃣ **Günlük Görevler:** Zikirlerini çek ve **+1 Yem** kazan. Nafile/Kaza namazı görevi ise sana **+2 Yem** kazandırır! 🐛\n"
            "3️⃣ **Civciv Pazarı:** Kazandığın altınlarla (50 Altın) rengarenk civcivler satın al. 🐣\n"
            "4️⃣ **Civciv Besle:** Civcivlerini yemlerinle besle. Bir civcive toplam 10 yem verdiğinde büyür ve **Tavuk** olur! 🐓\n"
            "5️⃣ **Yumurta & Sıralama:** Her tavuk sana **4 saatte 1 yumurta** verir. Yumurtalar seni haftalık sıralamada yükseltir! 🏆\n"
            "6️⃣ **Yumurta Pazarı:** Yumurtalarını satarak (10 adedi 1 Altın) altına çevirebilirsin.\n"
            "7️⃣ **Referans:** Arkadaşlarını davet et, her arkadaşın için **+3 Yem** kazan! 🤝\n\n"
            "Hadi Yumurta Üretimine Başla ve Bu Haftanın Birincisi Sen Ol!"
        )
        bot.send_message(user_id, info_text, parse_mode="Markdown")

    elif text == "🕋 Namaz Takibi":
        update_user_state(user_id, 'namaz')
        conn = get_db_connection()
        user = conn.execute("SELECT gold FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        bot.send_message(user_id, f"🕋 **NAMAZ TAKİBİ**\n\nBugünkü namazlarını işaretle.\n💰 Mevcut Altın: **{user['gold']}**", 
                         parse_mode="Markdown", reply_markup=namaz_menu_keyboard(user_id))
    
    elif "Kıldım" in text:
        found_idx = -1
        for idx, vakit in enumerate(NAMAZ_VAKITLERI):
            if vakit in text:
                found_idx = idx
                break
        
        if found_idx != -1:
            conn = get_db_connection()
            c = conn.cursor()
            user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            mask = list(user['prayed_mask'])
            
            if mask[found_idx] == '0':
                mask[found_idx] = '1'
                new_mask = "".join(mask)
                c.execute("UPDATE users SET prayed_mask=?, gold=gold+10 WHERE user_id=?", (new_mask, user_id))
                conn.commit()
                bot.send_message(user_id, f"✅ Allah kabul etsin! **+10 Altın** kazandın.", parse_mode="Markdown", reply_markup=namaz_menu_keyboard(user_id))
                
                # NAMAZ KILINDI -> YEDEK AL
                backup_to_cloud()
            else:
                bot.send_message(user_id, "Bu vakti zaten işaretlemiştin.")
            conn.close()

    elif text == "📝 Günlük Görevler":
        update_user_state(user_id, 'tasks')
        conn = get_db_connection()
        user = conn.execute("SELECT feed FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        bot.send_message(user_id, f"📝 **GÜNLÜK GÖREVLER**\n\nZikirler +1 Yem, Namaz görevi +2 Yem kazandırır.\n🐛 Mevcut Yem: **{user['feed']}**",
                         parse_mode="Markdown", reply_markup=gorev_menu_keyboard(user_id))

    elif "(+" in text and "Yem)" in text:
        target_task_id = -1
        for g in GUNLUK_GOREVLER:
            if g['text'] in text:
                target_task_id = g['id']
                break
        
        if target_task_id != -1:
            msg = bot.send_message(user_id, f"❓ **GÖREV ONAYI**\n\nBu görevi gerçekten yaptın mı?\n\n_{GUNLUK_GOREVLER[target_task_id]['text']}_", 
                                   parse_mode="Markdown", reply_markup=confirmation_keyboard())
            bot.register_next_step_handler(msg, process_task_confirmation, target_task_id)

    elif text == "🏪 Civciv Pazarı" or text == "🛒 Civciv Pazarı":
        update_user_state(user_id, 'market')
        conn = get_db_connection()
        user = conn.execute("SELECT gold, hens FROM users WHERE user_id=?", (user_id,)).fetchone()
        c = conn.cursor()
        chick_count = c.execute("SELECT COUNT(*) FROM chickens WHERE user_id=?", (user_id,)).fetchone()[0]
        conn.close()
        
        info = (f"🏪 **CİVCİV PAZARI**\n"
                f"💰 Bakiye: **{user['gold']} Altın**\n"
                f"🐣 Civciv Sayısı: **{chick_count}/8**\n"
                f"🐓 Tavuk Sayısı: **{user['hens']}**\n\n"
                f"Bir renk seç ve satın al (50 Altın):")
        bot.send_message(user_id, info, parse_mode="Markdown", reply_markup=civciv_pazar_keyboard(user_id))

    elif "Civciv (50 Altın)" in text:
        selected_color_code = None
        for code, details in COLORS.items():
            if details['name'] in text:
                selected_color_code = code
                break
        
        if selected_color_code:
            conn = get_db_connection()
            c = conn.cursor()
            user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            chick_count = c.execute("SELECT COUNT(*) FROM chickens WHERE user_id=?", (user_id,)).fetchone()[0]
            
            if chick_count >= 8:
                bot.send_message(user_id, "⚠️ Kümesin dolu! (Maks 8 civciv). Önce birini büyütüp tavuk yapmalısın.")
            elif user['gold'] < 50:
                bot.send_message(user_id, "⚠️ Yetersiz Bakiye! 50 Altın gerekli.")
            else:
                c.execute("UPDATE users SET gold=gold-50 WHERE user_id=?", (user_id,))
                c.execute("INSERT INTO chickens (user_id, color_code) VALUES (?, ?)", (user_id, selected_color_code))
                conn.commit()
                bot.send_message(user_id, f"✅ {COLORS[selected_color_code]['name']} civciv kümese eklendi!", reply_markup=civciv_pazar_keyboard(user_id))
                
                # SATIN ALMA -> YEDEK AL
                backup_to_cloud()
            conn.close()

    elif text == "🐥 Civciv Besle":
        update_user_state(user_id, 'feed')
        conn = get_db_connection()
        user = conn.execute("SELECT feed FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        
        markup, has_chick = civciv_besle_keyboard(user_id)
        if not has_chick:
            bot.send_message(user_id, "😔 Hiç civcivin yok! Önce pazardan almalısın.", reply_markup=markup)
        else:
            bot.send_message(user_id, f"🐥 **CİVCİV BESLEME**\n\n🐛 Mevcut Yem: **{user['feed']}**\n\nBeslemek istediğin civcivi seç:", 
                             parse_mode="Markdown", reply_markup=markup)

    elif "Civcivi Besle" in text:
        conn = get_db_connection()
        c = conn.cursor()
        chickens = c.execute("SELECT * FROM chickens WHERE user_id=?", (user_id,)).fetchall()
        user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        
        target_chick_id = None
        for chick in chickens:
            color_info = COLORS.get(chick['color_code'], {"name": "Bilinmeyen", "emoji": "❓"})
            progress = chick['feed_count']
            generated_text = f"{color_info['emoji']} {color_info['name']} Civcivi Besle ({progress}/10)"
            if generated_text == text:
                target_chick_id = chick['id']
                break
        
        if target_chick_id is not None:
            if user['feed'] < 1:
                bot.send_message(user_id, "⚠️ Yemin bitti! Görev yaparak kazanabilirsin.")
            else:
                c.execute("UPDATE chickens SET feed_count = feed_count + 1 WHERE id=?", (target_chick_id,))
                c.execute("UPDATE users SET feed = feed - 1 WHERE user_id=?", (user_id,))
                conn.commit()
                
                updated_user = c.execute("SELECT feed FROM users WHERE user_id=?", (user_id,)).fetchone()
                
                updated_chick = c.execute("SELECT * FROM chickens WHERE id=?", (target_chick_id,)).fetchone()
                if updated_chick['feed_count'] >= 10:
                    c.execute("DELETE FROM chickens WHERE id=?", (target_chick_id,))
                    c.execute("UPDATE users SET hens = hens + 1 WHERE user_id=?", (user_id,))
                    conn.commit()
                    bot.send_message(user_id, f"🎉 Tebrikler! Bir civcivin büyüyüp **TAVUK** oldu! 🐓\n🐛 Kalan Yem: {updated_user['feed']}", parse_mode="Markdown")
                else:
                    bot.send_message(user_id, f"✅ Civciv yemlendi!\n🐛 Kalan Yem: {updated_user['feed']}")
                
                # BESLEME -> YEDEK AL
                backup_to_cloud()
                
                new_markup, _ = civciv_besle_keyboard(user_id)
                bot.send_message(user_id, "Beslemeye devam et:", reply_markup=new_markup)
        else:
            bot.send_message(user_id, "Civciv bulunamadı veya durum değişti.")
        conn.close()

    elif text == "🥚 Yumurta Pazarı":
        update_user_state(user_id, 'egg_market')
        conn = get_db_connection()
        user = conn.execute("SELECT eggs_balance FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("💰 Tüm Yumurtaları Sat")
        markup.add("🔙 Ana Menüye Dön")
        
        msg = (f"🥚 **YUMURTA PAZARI**\n"
               f"1 Yumurta = 0.10 Altın\n"
               f"Min Satış: 10 Adet\n\n"
               f"Senin Yumurtan: **{user['eggs_balance']}**\n\n"
               f"👇 **Satmak için aşağıdaki butona basabilir VEYA klavyeden satmak istediğin adedi yazıp gönderebilirsin (Örn: 20)**")
        bot.send_message(user_id, msg, parse_mode="Markdown", reply_markup=markup)

    elif text == "💰 Tüm Yumurtaları Sat":
        conn = get_db_connection()
        c = conn.cursor()
        user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        
        if user['eggs_balance'] >= 10:
            earn = int(user['eggs_balance'] * 0.10)
            if earn < 1: earn = 1
            
            c.execute("UPDATE users SET eggs_balance=0, gold=gold+? WHERE user_id=?", (earn, user_id))
            conn.commit()
            bot.send_message(user_id, f"✅ Satış Başarılı!\nKazanılan: **{earn} Altın**", parse_mode="Markdown", reply_markup=main_menu_keyboard())
            
            # SATIŞ -> YEDEK AL
            backup_to_cloud()
        else:
            bot.send_message(user_id, "⚠️ En az 10 yumurtan olmalı.")
        conn.close()

    elif text == "📊 Genel Durum":
        update_user_state(user_id, 'status')
        conn = get_db_connection()
        c = conn.cursor()
        
        # 1. Kullanıcı verisi
        user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        
        # 2. Civciv Sayısı (Senin istediğin 3/8 formatı için)
        civciv_sayisi = c.execute("SELECT COUNT(*) FROM chickens WHERE user_id=?", (user_id,)).fetchone()[0]
        
        # 3. Haftalık Sıralama Hesaplama
        # Senden daha yüksek yumurta skoru olan kişi sayısı + 1 = Senin sıran
        siralama = c.execute("SELECT COUNT(*) FROM users WHERE eggs_score > ?", (user['eggs_score'],)).fetchone()[0] + 1
        
        # 4. Bir Sonraki Yumurtaya Kalan Süre Hesaplama
        if user['hens'] > 0:
            now = time.time()
            last_update = user['last_egg_update'] if user['last_egg_update'] else now
            gecen_sure = now - last_update
            dongu_suresi = 14400 # 4 saat (Saniye cinsinden)
            
            kalan_saniye = dongu_suresi - (gecen_sure % dongu_suresi)
            
            # Saniyeyi Saat:Dakika:Saniye formatına çevir
            m, s = divmod(kalan_saniye, 60)
            h, m = divmod(m, 60)
            kalan_sure_yazisi = "{:02d}:{:02d}:{:02d}".format(int(h), int(m), int(s))
        else:
            kalan_sure_yazisi = "Tavuk Yok 🛑"

        # 5. İbadet ve Görev Sayıları
        namaz_durumu = user['prayed_mask'].count('1')
        gorev_durumu = user['tasks_mask'].count('1')
        
        conn.close()
        
        # SENİN İSTEDİĞİN TASLAK (Birebir Format)
        text_msg = (
            f"👤 **Çiftçi:** {user['username']}\n"
            f"📍 **Konum:** {user['city']} / {user['district']}\n"
            f"💰 **Altın Miktarı:** {user['gold']}\n"
            f"🐛 **Yem Miktarı:** {user['feed']}\n"
            f"🐥 **Civciv Sayısı:** {civciv_sayisi}/8\n"
            f"🐓 **Tavuk Sayısı:** {user['hens']}\n"
            f"🥚 **Güncel Yumurta Sayısı:** {user['eggs_balance']}\n"
            f"🐔 **Bir Sonraki Yumurtaya Kalan Süre:** {kalan_sure_yazisi}\n"
            f"🏆 **Haftalık Sıralaman:** {siralama}\n\n"
            f"📅 **Bugünkü İbadetler:**\n"
            f"🕌 **Namazlar:** {namaz_durumu}/5\n"
            f"📝 **Günlük Görevler:** {gorev_durumu}/5"
        )
        bot.send_message(user_id, text_msg, parse_mode="Markdown")

    elif text == "🏆 Haftalık Sıralama":
        update_user_state(user_id, 'ranking')
        conn = get_db_connection()
        top_users = conn.execute("SELECT username, eggs_score FROM users ORDER BY eggs_score DESC LIMIT 10").fetchall()
        conn.close()
        
        rank_text = "🏆 **HAFTALIK SIRALAMA** 🏆\n\n"
        for i, u in enumerate(top_users, 1):
            # 1. İsimdeki olası karışıklığı önlemek için ismi temizleyelim veya olduğu gibi alalım
            isim = u['username']
            
            # 2. Puanı kesinlikle matematiksel sayıya (Integer) çevirelim
            # Bu işlem "٠" gibi karakterleri engeller, "0" yapar.
            puan = int(u['eggs_score']) 
            
            # 3. Puanı **Kalın** yazdırıyoruz. Bu, Telegram'ın font değiştirmesini engeller.
            rank_text += f"{i}. {isim} ➡️ **{puan}** Yumurta\n"
        
        bot.send_message(user_id, rank_text, parse_mode="Markdown")

    elif text == "👥 Referans Sistemi":
        update_user_state(user_id, 'referral')
        ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        msg = (f"👥 **REFERANS SİSTEMİ**\n\n"
               f"Linkinle arkadaşını davet et, **+3 YEM** kazan!\n\n"
               f"🔗 Linkin:\n`{ref_link}`")
        bot.send_message(user_id, msg, parse_mode="Markdown")

    elif text == "📍 Konum Güncelle":
        msg = bot.send_message(user_id, "📍 Lütfen YENİ Şehir ve İlçe bilgisini giriniz (Örn: İzmir Bornova):", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, save_location)

def process_task_confirmation(message, task_id):
    user_id = message.from_user.id
    if message.text == "✅ Evet, Yaptım":
        conn = get_db_connection()
        c = conn.cursor()
        user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        mask = list(user['tasks_mask'])
        
        if mask[task_id] == '0':
            mask[task_id] = '1'
            new_mask = "".join(mask)
            reward = GUNLUK_GOREVLER[task_id]['reward'] 
            c.execute("UPDATE users SET tasks_mask=?, feed=feed+? WHERE user_id=?", (new_mask, reward, user_id))
            conn.commit()
            bot.send_message(user_id, f"✅ Görev onaylandı! **+{reward} Yem** kazandın.", parse_mode="Markdown", reply_markup=gorev_menu_keyboard(user_id))
            
            # GÖREV YAPILDI -> YEDEK AL
            backup_to_cloud()
        else:
            bot.send_message(user_id, "⚠️ Bu görevi bugün zaten yapmıştın.", reply_markup=gorev_menu_keyboard(user_id))
        conn.close()
    else:
        bot.send_message(user_id, "❌ İşlem iptal edildi.", reply_markup=gorev_menu_keyboard(user_id))

# --- ZAMANLAYICIYI BAŞLAT ---
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
            print("Haftalık sıralama sıfırlandı.")
            backup_to_cloud()
            
    scheduler.add_job(reset_weekly, 'cron', day_of_week='sun', hour=23, minute=59)
    scheduler.start()

if __name__ == "__main__":
    init_db()
    
    # 1. BOT AÇILIRKEN BULUTTAN VERİYİ ÇEK (RESTORE)
    restore_from_cloud()
    
    start_scheduler()
    keep_alive() # Flask sunucusu başlatıldı
    
    # Webhook temizliği (409 hatası için)
    try:
        bot.remove_webhook()
        time.sleep(1)
    except:
        pass

    print("Bot ve Web Server başlatıldı...")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=20, skip_pending=True)
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(5)





