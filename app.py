import os
import time
import threading
import requests
from flask import Flask

app = Flask(__name__)

BOT_TOKEN = os.environ.get("8452344889:AAFkEzBOJ5RdWmXAQtxt8s42R_TUWPlrfFo")
CHAT_ID = os.environ.get("912977673")

WATCHLIST = ["TSLA","NVDA","AMD","PLTR","SOFI","NIO"]

def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg}
    )

def get_data(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
        r = requests.get(url).json()

        q = r["quoteResponse"]["result"][0]

        return {
            "price": q["regularMarketPrice"],
            "change": q["regularMarketChangePercent"],
            "volume": q["regularMarketVolume"]
        }
    except:
        return None

def run_bot():
    print("🔥 BOT WORKING", flush=True)

    while True:
        for s in WATCHLIST:
            d = get_data(s)

            if d and d["change"] > 2:
                msg = f"""🚀 فرصة

{s}
السعر: {d['price']}
التغير: {round(d['change'],2)}%
"""
                send(msg)
                print(f"sent {s}", flush=True)

            time.sleep(2)

        time.sleep(60)

@app.route("/")
def home():
    return "OK"

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
