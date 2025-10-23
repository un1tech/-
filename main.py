# main.py
# TreloxBot - Webhook + multi-user + SQLite + APScheduler
# Requirements: see requirements.txt

import os
import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot import types
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

# ----------------- Config -----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("Set BOT_TOKEN environment variable")

# External hostname for webhook
RENDER_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if not RENDER_HOST:
    raise SystemExit("Set RENDER_EXTERNAL_HOSTNAME environment variable (e.g. bmy3vv0zd6.onrender.com)")

DATABASE = os.getenv("DATABASE", "trelox.db")
JOBSTORE_DB = os.getenv("JOBSTORE_DB", "sqlite:///jobs.sqlite")  # APScheduler jobstore

# ----------------- Bot & Flask -----------------
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ----------------- Scheduler -----------------
jobstores = {"default": SQLAlchemyJobStore(url=JOBSTORE_DB)}
scheduler = BackgroundScheduler(jobstores=jobstores)
scheduler.start()

# ----------------- Database helpers -----------------
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    # users: basic info
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY,           -- telegram id
      username TEXT,
      first_name TEXT,
      created_at TEXT,
      points INTEGER DEFAULT 0,
      streak INTEGER DEFAULT 0,
      last_study_day TEXT
    )
    """)
    # sessions log
    c.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      task TEXT,
      started_at TEXT,
      duration_min INTEGER,
      completed INTEGER DEFAULT 0
    )
    """)
    # tasks (todo)
    c.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      title TEXT,
      created_at TEXT,
      done INTEGER DEFAULT 0
    )
    """)
    # badges
    c.execute("""
    CREATE TABLE IF NOT EXISTS badges (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      name TEXT,
      awarded_at TEXT
    )
    """)
    # challenges with friends
    c.execute("""
    CREATE TABLE IF NOT EXISTS friend_challenges (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      creator_id INTEGER,
      friend_id INTEGER,
      target_minutes INTEGER,
      started_at TEXT,
      ended_at TEXT,
      completed BOOLEAN DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

def db_conn():
    return sqlite3.connect(DATABASE)

def ensure_user(tg_user):
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE id=?", (tg_user.id,))
    if not c.fetchone():
        c.execute("INSERT INTO users (id, username, first_name, created_at) VALUES (?,?,?,?)",
                  (tg_user.id, tg_user.username, tg_user.first_name, datetime.utcnow().isoformat()))
        conn.commit()
    conn.close()

# ----------------- Utils -----------------
def add_points(user_id, pts):
    conn = db_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET points = points + ? WHERE id=?", (pts, user_id))
    conn.commit()
    conn.close()

def record_session(user_id, task, minutes, completed=1):
    conn = db_conn()
    c = conn.cursor()
    c.execute("INSERT INTO sessions (user_id, task, started_at, duration_min, completed) VALUES (?,?,?,?,?)",
              (user_id, task, datetime.utcnow().isoformat(), minutes, completed))
    conn.commit()
    conn.close()

def award_badge(user_id, name):
    conn = db_conn()
    c = conn.cursor()
    c.execute("INSERT INTO badges (user_id, name, awarded_at) VALUES (?,?,?)", (user_id, name, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_week_summary(user_id):
    conn = db_conn()
    c = conn.cursor()
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    c.execute("SELECT SUM(duration_min) FROM sessions WHERE user_id=? AND started_at>=? AND completed=1", (user_id, week_ago))
    s = c.fetchone()[0] or 0
    conn.close()
    return int(s)

# ----------------- Interactive flow state (in-memory short-lived) -----------------
# We keep minimal state to manage step-by-step keyboard flows.
# Long-term data stored in DB.
user_flow = {}  # user_id -> dict {stage:..., temp: ...}
flow_lock = threading.Lock()

def set_flow(user_id, data):
    with flow_lock:
        user_flow[user_id] = data

def get_flow(user_id):
    with flow_lock:
        return user_flow.get(user_id, {})

def clear_flow(user_id):
    with flow_lock:
        if user_id in user_flow:
            del user_flow[user_id]

# ----------------- Keyboard helpers -----------------
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🎯 ابدأ تحدي جديد", "📊 عرض إنجازاتي")
    markup.row("📝 مهامي", "🏆 الأوسمة")
    return markup

def hours_inline():
    markup = types.InlineKeyboardMarkup()
    for h in [1,2,3,4,5]:
        markup.add(types.InlineKeyboardButton(f"{h} ساعة", callback_data=f"hours:{h}"))
    return markup

def splits_inline(hours):
    markup = types.InlineKeyboardMarkup()
    opts = [(55,5),(50,10),(45,15),(40,20)]
    for s,r in opts:
        markup.add(types.InlineKeyboardButton(f"{s}m / {r}m", callback_data=f"split:{hours}:{s}:{r}"))
    markup.add(types.InlineKeyboardButton("🔧 إدخال يدوي", callback_data=f"split_custom:{hours}"))
    return markup

# ----------------- Bot handlers -----------------
@bot.message_handler(commands=['start'])
def handle_start(m):
    ensure_user(m.from_user)
    clear_flow(m.from_user.id)
    bot.send_message(m.chat.id, f"أهلاً {m.from_user.first_name}! 👋\nأنا TreloxBot — جاهز أبدأ معاك التحدي.", reply_markup=main_keyboard())

@bot.message_handler(func=lambda m: m.text == "🎯 ابدأ تحدي جديد")
def handle_new_challenge(m):
    ensure_user(m.from_user)
    bot.send_message(m.chat.id, "اختار مدة التحدي (ساعات):", reply_markup=types.ReplyKeyboardRemove())
    bot.send_message(m.chat.id, "اختر:", reply_markup=hours_inline())

@bot.callback_query_handler(func=lambda c: c.data.startswith("hours:"))
def cb_hours(call):
    _, h = call.data.split(":")
    hours = int(h)
    # save stage
    set_flow(call.from_user.id, {"stage":"await_split", "hours":hours})
    bot.edit_message_text("اختار تقسيم كل ساعة:", call.message.chat.id, call.message.message_id, reply_markup=splits_inline(hours))

@bot.callback_query_handler(func=lambda c: c.data.startswith("split:"))
def cb_split(call):
    # format split:hours:study:rest
    _, hours, study, rest = call.data.split(":")
    hours = int(hours); study = int(study); rest = int(rest)
    set_flow(call.from_user.id, {"stage":"await_task", "hours":hours, "study":study, "rest":rest})
    bot.send_message(call.message.chat.id, "اكتب الهدف/المادة اللي هتذاكرها للتحدي:")

@bot.callback_query_handler(func=lambda c: c.data.startswith("split_custom:"))
def cb_split_custom(call):
    _, hours = call.data.split(":")
    hours = int(hours)
    set_flow(call.from_user.id, {"stage":"await_custom_split", "hours":hours})
    bot.send_message(call.message.chat.id, "اكتب تقسيم الساعة على الشكل: <مذاكرة> <راحة> (مثال: 52 8)")

@bot.message_handler(func=lambda m: get_flow(m.from_user.id).get("stage")=="await_custom_split")
def handle_custom_split(m):
    parts = m.text.strip().split()
    if len(parts)!=2:
        bot.reply_to(m, "الصيغة غلط. اكتب مثال: 52 8")
        return
    try:
        study = int(parts[0]); rest = int(parts[1])
    except:
        bot.reply_to(m, "ادخل أرقام صحيحة.")
        return
    flow = get_flow(m.from_user.id)
    hours = flow.get("hours")
    set_flow(m.from_user.id, {"stage":"await_task", "hours":hours, "study":study, "rest":rest})
    bot.send_message(m.chat.id, "اكتب الهدف/المادة اللي هتذاكرها للتحدي:")

@bot.message_handler(func=lambda m: get_flow(m.from_user.id).get("stage")=="await_task")
def handle_task_text(m):
    flow = get_flow(m.from_user.id)
    hours = flow["hours"]; study = flow["study"]; rest = flow["rest"]
    task = m.text.strip()
    # start challenge
    bot.send_message(m.chat.id, f"تمام! هنبدأ تحدي {hours} ساعة على {task}. كل جلسة {study} دقيقة وراحة {rest} دقيقة. هبدأ أبعث تنبيهات.")
    # schedule sessions using scheduler (persistent jobstore)
    total_minutes = hours*60
    session_num = 0
    now = datetime.utcnow()
    # schedule sequential jobs per session
    t = now
    session_index = 0
    while total_minutes > 0:
        session_index += 1
        # session start
        run_at = t
        minutes = min(study, total_minutes)
        job_id = f"session_{m.from_user.id}_{int(run_at.timestamp())}_{session_index}"
        # schedule a job to send "session started" immediately (we'll schedule start now) and job to mark completion after duration
        scheduler.add_job(func=job_send_start, trigger='date', run_date=run_at, args=[m.chat.id, m.from_user.id, task, session_index, minutes], id=job_id, replace_existing=True)
        # schedule completion job
        finish_at = run_at + timedelta(minutes=minutes)
        finish_job_id = f"finish_{m.from_user.id}_{int(finish_at.timestamp())}_{session_index}"
        scheduler.add_job(func=job_finish_session, trigger='date', run_date=finish_at, args=[m.chat.id, m.from_user.id, task, session_index, minutes, rest], id=finish_job_id, replace_existing=True)
        # advance time
        t = finish_at + timedelta(minutes=rest)
        total_minutes -= (minutes + rest)
    # store challenge summary in sessions as "planned" rows (duration only) - real completion logged when job_finish_session runs
    conn = db_conn()
    c = conn.cursor()
    # store a high level session count for user's metrics
    conn.commit()
    conn.close()
    clear_flow(m.from_user.id)

def job_send_start(chat_id, user_id, task, session_num, minutes):
    try:
        bot.send_message(chat_id, f"📚 الجلسة {session_num} بدأت — {minutes} دقيقة. التركيز دلوقتي!")
    except Exception as e:
        print("job_send_start error:", e)

def job_finish_session(chat_id, user_id, task, session_num, minutes, rest):
    try:
        # record session done
        record_session(user_id, task, minutes)
        add_points(user_id, 10)  # reward points
        bot.send_message(chat_id, f"✅ خلصت الجلسة {session_num} — {minutes} دقيقة.\nخُد راحة {rest} دقيقة الآن.")
        # award simple badges
        weekly = get_week_summary(user_id)
        if weekly >= 300:  # example badge threshold 5 hours = 300 min
            award_badge(user_id, "🔥 أسطورة الأسبوع")
            bot.send_message(chat_id, "🏅 مبارك! حصلت على شارة: أسطورة الأسبوع")
    except Exception as e:
        print("job_finish_session error:", e)

# ----------------- simple task list handlers -----------------
@bot.message_handler(func=lambda m: m.text == "📝 مهامي")
def list_tasks(m):
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT id,title,done FROM tasks WHERE user_id=?", (m.from_user.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.send_message(m.chat.id, "لا يوجد مهام مضافة. استخدم /addtask لإضافة مهمة.")
        return
    text = "مهامك:\n"
    for r in rows:
        tid, title, done = r
        status = "✅" if done else "🔲"
        text += f"{tid}. {status} {title}\n"
    bot.send_message(m.chat.id, text)

@bot.message_handler(commands=['addtask'])
def addtask_cmd(m):
    bot.send_message(m.chat.id, "اكتب عنوان المهمة:")
    set_flow(m.from_user.id, {"stage":"addtask"})

@bot.message_handler(func=lambda m: get_flow(m.from_user.id).get("stage")=="addtask")
def addtask_text(m):
    title = m.text.strip()
    conn = db_conn()
    c = conn.cursor()
    c.execute("INSERT INTO tasks (user_id, title, created_at) VALUES (?,?,?)",(m.from_user.id, title, datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    clear_flow(m.from_user.id)
    bot.send_message(m.chat.id, "تم إضافة المهمة ✅")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("/donetask"))
def donetask_cmd(m):
    parts = m.text.split()
    if len(parts)<2:
        bot.reply_to(m, "استخدام: /donetask <id>")
        return
    try:
        tid = int(parts[1])
    except:
        bot.reply_to(m, "أدخل رقم مهمة صحيح")
        return
    conn = db_conn()
    c = conn.cursor()
    c.execute("UPDATE tasks SET done=1 WHERE id=? AND user_id=?", (tid, m.from_user.id))
    conn.commit(); conn.close()
    bot.send_message(m.chat.id, "تم تعليم المهمة كمكتملة ✅")

# ----------------- show badges and points -----------------
@bot.message_handler(func=lambda m: m.text == "🏆 الأوسمة")
def show_badges(m):
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT name,awarded_at FROM badges WHERE user_id=?", (m.from_user.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.send_message(m.chat.id, "مافيش أوسمة لحد دلوقتي. خلّيك مستمر!")
        return
    text = "أوسمتك:\n"
    for r in rows:
        text += f"🏅 {r[0]} ({r[1].split('T')[0]})\n"
    bot.send_message(m.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "📊 عرض إنجازاتي")
def show_stats(m):
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT SUM(duration_min) FROM sessions WHERE user_id=? AND completed=1",(m.from_user.id,))
    total = c.fetchone()[0] or 0
    c.execute("SELECT points FROM users WHERE id=?",(m.from_user.id,))
    pts = c.fetchone()[0] or 0
    conn.close()
    bot.send_message(m.chat.id, f"📈 إجمالي وقت مذاكرة: {total} دقيقة\n⭐ نقاطك: {pts}")

# ----------------- webhooks endpoints -----------------
@app.route('/')
def root():
    return "TreloxBot is running."

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# ----------------- start webhook & set on boot -----------------
def set_webhook():
    url = f"https://{RENDER_HOST}/{BOT_TOKEN}"
    try:
        bot.remove_webhook()
    except:
        pass
    bot.set_webhook(url=url)

if __name__ == "__main__":
    # init DB
    init_db()
    # set webhook
    set_webhook()
    # run flask app (webhook receiver)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
