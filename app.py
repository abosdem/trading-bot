from flask import Flask
import threading
import time
import requests
import os
import yfinance as yf
import pandas as pd

app = Flask(__name__)

BOT_TOKEN = "حط_توكنك"
CHAT_ID = "حط_ايديك"

WATCHLIST = ["NIO", "TSLA", "AMD", "PLTR"]

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=data)

def get_data(symbol, interval):
    df = yf.download(symbol, period="1d", interval=interval)
    return df

def check_signal(symbol):
    df5 = get_data(symbol, "5m")
    df15 = get_data(symbol, "15m")

    if df5.empty or df15.empty:
        return None

    # EMA
    df5["EMA20"] = df5["Close"].ewm(span=20).mean()
    df15["EMA20"] = df15["Close"].ewm(span=20).mean()

    # Volume
    avg_vol = df5["Volume"].rolling(20).mean()

    last = df5.iloc[-1]
    prev = df5.iloc[-20:]

    breakout = last["Close"] > prev["High"].max()
    trend5 = last["Close"] > last["EMA20"]
    trend15 = df15.iloc[-1]["Close"] > df15.iloc[-1]["EMA20"]
    volume = last["Volume"] > avg_vol.iloc[-1] * 1.8

    if breakout and trend5 and trend15 and volume:
        entry = round(last["Close"], 2)
        stop = round(entry * 0.97, 2)
        target = round(entry * 1.05, 2)

        return f"""🚨 إشارة تداول

📊 {symbol}
💰 دخول: {entry}
🛑 وقف: {stop}
🎯 هدف: {target}

🔥 اختراق + سيولة + اتجاه
"""

    return None

def bot_loop():
    send_telegram("🚀 البوت بدأ يفحص السوق")

    while True:
        for stock in WATCHLIST:
            signal = check_signal(stock)
            if signal:
                send_telegram(signal)
                print(f"Signal found for {stock}")

        print("🔥 يفحص السوق...")
        time.sleep(60)

@app.route("/")
def home():
    return "Bot is running"

if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
