from flask import Flask
import threading
import time
import requests
import os

app = Flask(__name__)

BOT_TOKEN = "8452344889:AAFkEzBOJ5RdWmXAQtxt8s42R_TUWPlrfFo"
CHAT_ID = "912977673"

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
        print("🔥 البوت شغال ويفحص السوق...", flush=True)
        time.sleep(60)

@app.route("/")
def home():
    return "Bot is running"

if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
