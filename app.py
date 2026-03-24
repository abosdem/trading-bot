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

FMP_API = "demo"  # غيره لاحقًا لو تبغى قوة أعلى

CHECK_INTERVAL = 15
COOLDOWN = 1800

MIN_PRICE = 0.2
MAX_PRICE = 10

MIN_LIQ = 200000
MIN_RVOL = 2.0
MIN_CHANGE = 1.5

sent = {}

# =========================
def send(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except:
        pass

@app.route("/")
def home():
    return "ELITE BOT RUNNING"

# =========================
# جلب الأسهم القوية
# =========================
def get_stocks():
    try:
        url = f"https://financialmodelingprep.com/api/v3/stock_market/gainers?apikey={FMP_API}"
        data = requests.get(url, timeout=10).json()
        return [x["symbol"] for x in data if MIN_PRICE <= x.get("price", 0) <= MAX_PRICE][:40]
    except:
        return []

# =========================
# جلب الأخبار
# =========================
def get_news(symbol):
    try:
        url = f"https://financialmodelingprep.com/api/v3/stock_news?tickers={symbol}&limit=3&apikey={FMP_API}"
        data = requests.get(url, timeout=10).json()

        if not data:
            return "لا يوجد خبر"

        titles = [x["title"] for x in data[:2]]
        return " | ".join(titles)

    except:
        return "لا يوجد خبر"

# =========================
def get(symbol, tf):
    try:
        df = yf.download(symbol, period="1d", interval=tf, progress=False, prepost=True)
        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.dropna()
        if df.empty:
            return None

        return df
    except:
        return None

# =========================
def ind(df):
    df["ema9"] = df["Close"].ewm(9).mean()
    df["ema20"] = df["Close"].ewm(20).mean()
    df["ema50"] = df["Close"].ewm(50).mean()

    df["avgv"] = df["Volume"].rolling(20).mean()
    df["rvol"] = df["Volume"] / df["avgv"]

    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    df["vwap"] = (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()

    return df

# =========================
def signal(sym):
    d1 = get(sym, "1m")
    d5 = get(sym, "5m")
    d15 = get(sym, "15m")

    if d1 is None or d5 is None or d15 is None:
        return None

    if len(d1) < 30 or len(d5) < 30 or len(d15) < 30:
        return None

    d1 = ind(d1)
    d5 = ind(d5)
    d15 = ind(d15)

    l = d1.iloc[-1]

    price = float(l["Close"])
    prev = float(d1["Close"].iloc[-6])

    change = ((price - prev) / prev) * 100 if prev else 0
    if change < MIN_CHANGE:
        return None

    vol = d1["Volume"].tail(5).mean()
    if pd.isna(vol) or vol <= 0:
        return None

    liq = price * vol
    if liq < MIN_LIQ:
        return None

    rvol = float(l["rvol"]) if pd.notna(l["rvol"]) else 0
    if rvol < MIN_RVOL:
        return None

    breakout = float(d5["High"].iloc[-20:-1].max())
    near = price >= breakout * 0.995

    if not near:
        return None

    ema9 = float(l["ema9"])
    ema20 = float(l["ema20"])
    ema50 = float(l["ema50"])

    if not (price > ema9 > ema20):
        return None

    if float(d5.iloc[-1]["Close"]) < float(d5.iloc[-1]["ema20"]):
        return None

    if float(d15.iloc[-1]["Close"]) < float(d15.iloc[-1]["ema20"]):
        return None

    if pd.isna(l["vwap"]) or price < float(l["vwap"]):
        return None

    news = get_news(sym)

    entry = round(price, 2)
    stop = round(entry * 0.96, 2)

    t1 = round(entry * 1.04, 2)
    t2 = round(entry * 1.07, 2)
    t3 = round(entry * 1.10, 2)

    return f"""🚨 إشارة النخبة القصوى

📊 {sym}

💰 دخول: {entry}
🛑 وقف: {stop}

🎯 هدف1: {t1}
🎯 هدف2: {t2}
🎯 هدف3: {t3}

💧 سيولة: {round(liq/1000,1)}K
📈 RVOL: {round(rvol,2)}
⚡ 5m: {round(change,2)}%

📰 الخبر:
{news}
"""

# =========================
def loop():
    send("🔥 الوحش النهائي بدأ")

    while True:
        try:
            stocks = get_stocks()

            for s in stocks:
                sig = signal(s)

                if sig:
                    if time.time() - sent.get(s, 0) > COOLDOWN:
                        send(sig)
                        sent[s] = time.time()

            time.sleep(CHECK_INTERVAL)

        except:
            time.sleep(10)

# =========================
if __name__ == "__main__":
    threading.Thread(target=loop, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
