import telebot
import os
from flask import Flask
import threading

# 🧠 جلب التوكن من المتغيرات البيئية (Environment Variables)
TOKEN = os.getenv("BOT_TOKEN") or "ضع_توكن_البوت_بتاعك_هنا_لو_تجرب_محلي"
bot = telebot.TeleBot(TOKEN)

# 🚀 نقطة البداية في البوت
@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, "🚀 أهلاً معتز! البوت اشتغل بنجاح 💪")

# 🌐 إعداد سيرفر Flask عشان Render يفضل شايف التطبيق حي
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=10000)

# 🧵 تشغيل Flask في خيط منفصل (thread)
threading.Thread(target=run_flask).start()

# 🔄 تشغيل البوت باستمرار
bot.infinity_polling()
