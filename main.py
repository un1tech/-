import telebot
import os

TOKEN = os.getenv("BOT_TOKEN") or "ضع_توكن_البوت_بتاعك_هنا_لو_عايز_تجرب_محلي"
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, "🚀 أهلاً معتز! البوت اشتغل بنجاح 💪")

bot.polling()
