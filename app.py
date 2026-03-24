from flask import Flask
import threading
import time
import requests

app = Flask(__name__)

# 🔐 بياناتك
BOT_TOKEN = "حط_توكن_البوت_هنا"
CHAT_ID = "حط_ايدي_التليجرام_هنا"

# 📤 إرسال رسالة
def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.post(url, data=data)

# 🤖 البوت
def bot_loop():
    send_telegram("🚀 البوت اشتغل بنجاح على Render")

    while True:
        print("🔥 البوت شغال ويفحص السوق...")
        time.sleep(60)

# تشغيل البوت
threading.Thread(target=bot_loop).start()

# ويب بسيط عشان Render
@app.route("/")
def home():
    return "Trading Bot Running"
