from flask import Flask
import threading
import time
import requests

app = Flask(__name__)

BOT_TOKEN = "حط_توكن_البوت_هنا"
CHAT_ID = "حط_الشات_ايدي_هنا"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.post(url, data=data)

def bot_loop():
    send_telegram("✅ البوت اشتغل على Render بنجاح")
    while True:
        print("🔥 البوت شغال ويفحص السوق...")
        time.sleep(60)

threading.Thread(target=bot_loop).start()

@app.route("/")
def home():
    return "Trading Bot Running"
