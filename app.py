from flask import Flask
import threading
import time
import requests
import os

app = Flask(__name__)

BOT_TOKEN = "حط_توكن_البوت_هنا"
CHAT_ID = "حط_ايدي_التليجرام_هنا"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.post(url, data=data)

def bot_loop():
    send_telegram("🚀 البوت اشتغل بنجاح")

    while True:
        print("🔥 البوت شغال ويفحص السوق...")
        time.sleep(60)

threading.Thread(target=bot_loop).start()

@app.route("/")
def home():
    return "Bot is running"

# 🔥 هذا أهم سطر
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
