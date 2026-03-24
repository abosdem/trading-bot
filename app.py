import requests
import time
from flask import Flask
import threading

app = Flask(__name__)

BOT_TOKEN = "8452344889:AAFkEzBOJ5RdWmXAQtxt8s42R_TUWPlrfFo"
CHAT_ID = "912977673"

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

def get_price(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        r = requests.get(url).json()
        return r["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except:
        return None

def scan():
    symbols = ["NIO","TPET","YYAI","ASNS","SOWG","VEEE","ACXP","AAGR","IMPP"]

    while True:
        print("🔥 يفحص السوق...")
        for s in symbols:
            price = get_price(s)
            if not price:
                continue

            entry = price
            stop = round(entry * 0.96, 2)
            t1 = round(entry * 1.03, 2)
            t2 = round(entry * 1.07, 2)
            t3 = round(entry * 1.10, 2)

            msg = f"""🚨 إشارة نخبة

📊 السهم: {s}
💰 الدخول: {entry}

🛑 الوقف: {stop}

🎯 الهدف 1: {t1}
🎯 الهدف 2: {t2}
🎯 الهدف 3: {t3}

🔥 فرصة محتملة
"""
            send(msg)
            print("✅ أرسل:", s)

            time.sleep(2)

        time.sleep(60)

@app.route('/')
def home():
    return "BOT RUNNING 🔥"

def run_bot():
    scan()

threading.Thread(target=run_bot).start()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
