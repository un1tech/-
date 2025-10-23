import telebot
import os
import json
import threading
import time
from datetime import datetime, timedelta
from flask import Flask
from telebot import types

# ================== إعداد التوكن ==================
TOKEN = os.getenv("BOT_TOKEN") or "ضع_توكن_البوت_هنا"
bot = telebot.TeleBot(TOKEN)

DATA_FILE = "data.json"

# ================== دوال مساعدة ==================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def log_study(user_id, task, duration):
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    if str(user_id) not in data:
        data[str(user_id)] = {}
    if today not in data[str(user_id)]:
        data[str(user_id)][today] = []
    data[str(user_id)][today].append({"task": task, "duration": duration})
    save_data(data)

# ================== بداية المحادثة ==================
@bot.message_handler(commands=["start"])
def start(msg):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🎯 ابدأ تحدي جديد")
    markup.add("📊 عرض إنجازاتي")
    bot.send_message(msg.chat.id, "🚀 أهلاً معتز! جاهز نبدأ المذاكرة؟", reply_markup=markup)

# ================== اختيار مدة التحدي ==================
@bot.message_handler(func=lambda m: m.text == "🎯 ابدأ تحدي جديد")
def challenge_start(msg):
    markup = types.InlineKeyboardMarkup()
    for h in [1, 2, 3, 4]:
        markup.add(types.InlineKeyboardButton(f"{h} ساعة", callback_data=f"hours_{h}"))
    bot.send_message(msg.chat.id, "⏰ اختار مدة التحدي:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("hours_"))
def choose_split(call):
    hours = int(call.data.split("_")[1])
    markup = types.InlineKeyboardMarkup()
    options = [(50, 10), (55, 5), (45, 15)]
    for m, r in options:
        markup.add(types.InlineKeyboardButton(f"{m} مذاكرة / {r} راحة", callback_data=f"split_{hours}_{m}_{r}"))
    bot.edit_message_text("💡 اختار طريقة التقسيم:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("split_"))
def ask_task(call):
    _, hours, study, rest = call.data.split("_")
    bot.send_message(call.message.chat.id, f"📘 ممتاز! هتذاكر إيه في التحدي ده؟")
    bot.register_next_step_handler(call.message, lambda msg: start_timer(msg, int(hours), int(study), int(rest)))

def start_timer(msg, hours, study, rest):
    task = msg.text
    bot.send_message(msg.chat.id, f"🔥 تمام، هنبدأ {hours} ساعة {study} دقيقة مذاكرة و {rest} راحة.")
    threading.Thread(target=run_sessions, args=(msg.chat.id, task, hours, study, rest)).start()

def run_sessions(chat_id, task, hours, study, rest):
    total_minutes = hours * 60
    session = 0
    while total_minutes > 0:
        session += 1
        bot.send_message(chat_id, f"📚 الجلسة {session} بدأت! ذاكر لمدة {study} دقيقة 💪")
        time.sleep(study * 60)
        log_study(chat_id, task, study)
        total_minutes -= study
        if total_minutes <= 0:
            break
        bot.send_message(chat_id, f"😴 خُد راحة {rest} دقيقة ⏳")
        time.sleep(rest * 60)
        total_minutes -= rest

    bot.send_message(chat_id, f"🎉 خلصت التحدي! شُغل عظيم يا بطل 💪")

# ================== عرض الإنجازات ==================
@bot.message_handler(func=lambda m: m.text == "📊 عرض إنجازاتي")
def show_summary(msg):
    data = load_data()
    user_data = data.get(str(msg.chat.id), {})
    if not user_data:
        bot.send_message(msg.chat.id, "🤷‍♂️ لسه ما عندكش إنجازات.")
        return
    summary = "🏆 إنجازاتك:\n"
    for date, tasks in user_data.items():
        total = sum(t["duration"] for t in tasks)
        summary += f"\n📅 {date}: {total} دقيقة"
    bot.send_message(msg.chat.id, summary)

# ================== Flask Server ==================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is running on Render!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask).start()

# ================== تشغيل البوت ==================
def run_bot():
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

threading.Thread(target=run_bot).start()
