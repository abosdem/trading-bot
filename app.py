from flask import Flask
import threading
import time
import requests
import os
import yfinance as yf
import pandas as pd

app = Flask(__name__)

BOT_TOKEN = "8452344889:AAFkEzBOJ5RdWmXAQtxt8s42R_TUWPlrfFo"
CHAT_ID = "912977673"

WATCHLIST = [
    "VEEE","SOWG","STI","ATPC","SMSI","LGVN","ACXP",
    "AGRZ","LASE","DDD","ALTO","MOBX","IOVA","PRSO",
    "EDSA","YYAI","JEM","DXST","ASNS","SMWB","TPET",
    "BSM","SND","BOF","SOUN","CPIX","NIO","VSA",
    "MYO","MNDR","FIEE"
]

sent_start = False
last_sent = {}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}", flush=True)

@app.route("/", methods=["GET", "POST"])
def home():
    return "Bot is running"

def get_data(symbol, interval):
    try:
        df = yf.download(
            symbol,
            period="1d",
            interval=interval,
            progress=False,
            auto_adjust=False,
            threads=False
        )
        if df is None or df.empty:
            return pd.DataFrame()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        return df.dropna()
    except Exception as e:
        print(f"Data error {symbol} {interval}: {e}", flush=True)
        return pd.DataFrame()

def check_signal(symbol):
    df5 = get_data(symbol, "5m")
    df15 = get_data(symbol, "15m")

    if df5.empty or df15.empty:
        return None

    if len(df5) < 25 or len(df15) < 25:
        return None

    try:
        df5["EMA20"] = df5["Close"].ewm(span=20).mean()
        df15["EMA20"] = df15["Close"].ewm(span=20).mean()
        df5["AVG_VOL"] = df5["Volume"].rolling(20).mean()

        last5 = df5.iloc[-1]
        last15 = df15.iloc[-1]

        breakout_level = float(df5["High"].iloc[-21:-1].max())

        close5 = float(last5["Close"])
        ema5 = float(last5["EMA20"])
        close15 = float(last15["Close"])
        ema15 = float(last15["EMA20"])
        vol5 = float(last5["Volume"])
        avg_vol5 = float(last5["AVG_VOL"]) if pd.notna(last5["AVG_VOL"]) else 0.0

        breakout = close5 > breakout_level
        trend5 = close5 > ema5
        trend15 = close15 > ema15
        volume_ok = avg_vol5 > 0 and vol5 > avg_vol5 * 1.8

        if breakout and trend5 and trend15 and volume_ok:
            entry = round(close5, 2)
            stop = round(entry * 0.97, 2)
            target = round(entry * 1.05, 2)

            return f"""🚨 إشارة تداول

📊 السهم: {symbol}
💰 الدخول: {entry}
🛑 الوقف: {stop}
🎯 الهدف: {target}

🔥 اختراق + سيولة + اتجاه
"""
    except Exception as e:
        print(f"Signal error {symbol}: {e}", flush=True)

    return None

def bot_loop():
    global sent_start

    if not sent_start:
        send_telegram("🚀 البوت بدأ يفحص السوق")
        sent_start = True

    while True:
        try:
            now_ts = time.time()

            for stock in WATCHLIST:
                signal = check_signal(stock)

                if signal:
                    last_time = last_sent.get(stock, 0)

                    if now_ts - last_time > 900:
                        send_telegram(signal)
                        last_sent[stock] = now_ts
                        print(f"Signal sent: {stock}", flush=True)

            print("🔥 يفحص السوق...", flush=True)
            time.sleep(15)

        except Exception as e:
            print(f"Loop error: {e}", flush=True)
            time.sleep(15)

if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
