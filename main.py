import telebot
import os
from flask import Flask
import threading
import time

# 🧠 جلب التوكن من متغير البيئة
TOKEN = os.getenv("BOT_TOKEN") or "ضع_توكن_البوت_بتاعك_هنا_لو_تجرب_محلي"
bot = telebot.TeleBot(TOKEN)

# 🚀 رسالة البداية
@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, "🚀 أهلاً معتز! البوت اشتغل بنجاح 💪")

# 🌐 إنشاء Flask server عشان Render يحس أن الخدمة شغالة
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is running on Render!"

def run_flask():
    # Render بيدي بورت تلقائي، نستخدمه هنا
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# 🧵 تشغيل Flask في خيط منفصل
threading.Thread(target=run_flask).start()

# 🔁 تشغيل البوت، مع حماية من الخطأ 409
def run_bot():
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            print("Bot crashed, restarting in 5s:", e)
            time.sleep(5)

if __name__ == "__main__":
    run_bot()
