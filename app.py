from flask import Flask
import requests
import time
import threading
import yfinance as yf
import pandas as pd
import os

app = Flask(__name__)

BOT_TOKEN = "8452344889:AAFkEzBOJ5RdWmXAQtxt8s42R_TUWPlrfFo"
CHAT_ID = "912977673"

CHECK_INTERVAL_SECONDS = 25
COOLDOWN_SECONDS = 2700
MIN_LIQUIDITY = 150000
MIN_RVOL = 1.8
MIN_PRICE_CHANGE_5M = 1.0
BREAKOUT_LOOKBACK = 20
NEAR_BREAKOUT_BUFFER = 0.995
MIN_SCORE = 6

STOP_LOSS_PCT = 0.04
TARGET1_PCT = 0.04
TARGET2_PCT = 0.07
TARGET3_PCT = 0.10

WATCHLIST = []
last_sent = {}
sent_start = False
last_scan_update = 0

def send_telegram(message):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": message},
            timeout=10
        )
    except:
        pass

@app.route("/", methods=["GET", "POST"])
def home():
    return "Bot Running"

def get_top_stocks():
    try:
        url = "https://financialmodelingprep.com/api/v3/stock_market/gainers?apikey=demo"
        r = requests.get(url, timeout=10).json()
        symbols = [x["symbol"] for x in r if x.get("price", 100) <= 10]
        return symbols[:30]
    except:
        return []

def update_watchlist():
    global WATCHLIST, last_scan_update
    if time.time() - last_scan_update > 300:
        new_list = get_top_stocks()
        if new_list:
            WATCHLIST = new_list
        last_scan_update = time.time()

def flatten(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def get_data(symbol, interval):
    try:
        df = yf.download(symbol, period="1d", interval=interval, progress=False, prepost=True)
        if df is None or df.empty:
            return pd.DataFrame()
        df = flatten(df)
        df = df.dropna()
        return df
    except:
        return pd.DataFrame()

def add_indicators(df):
    df["EMA9"] = df["Close"].ewm(span=9).mean()
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    df["AVG_VOL20"] = df["Volume"].rolling(20).mean()
    df["RVOL"] = df["Volume"] / df["AVG_VOL20"]
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    df["VWAP"] = (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()
    return df

def check_signal(symbol):
    df1 = get_data(symbol, "1m")
    df5 = get_data(symbol, "5m")
    df15 = get_data(symbol, "15m")

    if df1.empty or df5.empty or df15.empty:
        return None

    if len(df1) < 30 or len(df5) < 30 or len(df15) < 30:
        return None

    try:
        df1 = add_indicators(df1)
        df5 = add_indicators(df5)
        df15 = add_indicators(df15)

        l1 = df1.iloc[-1]
        l5 = df5.iloc[-1]
        l15 = df15.iloc[-1]

        price = float(l1["Close"])
        prev = float(df1["Close"].iloc[-6])
        change5 = ((price - prev) / prev) * 100 if prev else 0

        if change5 <= 0:
            return None

        vol = df1["Volume"].tail(5).mean()
        if pd.isna(vol) or vol <= 0:
            return None

        liquidity = price * vol
        if liquidity < MIN_LIQUIDITY:
            return None

        rvol = float(l1["RVOL"]) if pd.notna(l1["RVOL"]) else 0
        if rvol < MIN_RVOL:
            return None

        breakout_level = float(df5["High"].iloc[-BREAKOUT_LOOKBACK:-1].max())
        breakout = price > breakout_level
        near = price >= breakout_level * NEAR_BREAKOUT_BUFFER

        ema9 = float(l1["EMA9"])
        ema20 = float(l1["EMA20"])
        ema50 = float(l1["EMA50"])

        trend = price > ema9 > ema20
        trend5 = float(l5["Close"]) > float(l5["EMA20"])
        trend15 = float(l15["Close"]) > float(l15["EMA20"])
        vwap_ok = price > float(l1["VWAP"]) if pd.notna(l1["VWAP"]) else False

        score = 0
        if near: score += 2
        if breakout: score += 2
        if trend: score += 1
        if trend5: score += 1
        if trend15: score += 1
        if vwap_ok: score += 1
        if ema9 > ema20 > ema50: score += 1
        if liquidity >= MIN_LIQUIDITY: score += 1
        if rvol >= MIN_RVOL: score += 1
        if change5 >= MIN_PRICE_CHANGE_5M: score += 1

        if score < MIN_SCORE:
            return None

        entry = round(price, 2)
        stop = round(entry * (1 - STOP_LOSS_PCT), 2)
        t1 = round(entry * (1 + TARGET1_PCT), 2)
        t2 = round(entry * (1 + TARGET2_PCT), 2)
        t3 = round(entry * (1 + TARGET3_PCT), 2)

        return f"""🚨 إشارة

{symbol}
دخول: {entry}
وقف: {stop}
هدف1: {t1}
هدف2: {t2}
هدف3: {t3}
سيولة: {round(liquidity/1000,1)}K
RVOL: {round(rvol,2)}
تغير5م: {round(change5,2)}%
"""

    except:
        return None

def bot_loop():
    global sent_start

    if not sent_start:
        send_telegram("🚀 بدأ الفحص")
        sent_start = True

    while True:
        try:
            update_watchlist()

            for s in WATCHLIST:
                sig = check_signal(s)
                if sig:
                    if time.time() - last_sent.get(s, 0) > COOLDOWN_SECONDS:
                        send_telegram(sig)
                        last_sent[s] = time.time()

            time.sleep(CHECK_INTERVAL_SECONDS)

        except:
            time.sleep(10)

if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
