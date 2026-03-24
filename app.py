import os
import time
import threading
import requests
from bs4 import BeautifulSoup
from flask import Flask

app = Flask(__name__)

BOT_TOKEN = os.environ.get("8452344889:AAFkEzBOJ5RdWmXAQtxt8s42R_TUWPlrfFo")
CHAT_ID = os.environ.get("912977673")

CHECK_INTERVAL = 180
COOLDOWN = 3600

sent = {}

def send(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except:
        pass

# 🔥 نسحب الأسهم من Finviz
def get_stocks():
    try:
        url = "https://finviz.com/screener.ashx?v=111&f=geo_usa,sh_price_u10,sh_avgvol_o500,sh_relvol_o2"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)

        soup = BeautifulSoup(r.text, "lxml")
        tickers = []

        for a in soup.select("a.screener-link-primary"):
            t = a.text.strip()
            if t not in tickers:
                tickers.append(t)

        return tickers[:15]

    except:
        return []

# 🔥 مصدر بيانات ثابت (بديل Yahoo)
def get_data(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
        headers = {"User-Agent": "Mozilla/5.0"}

        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()

        result = data["quoteResponse"]["result"]
        if not result:
            return None

        q = result[0]

        price = q.get("regularMarketPrice", 0)
        change = q.get("regularMarketChangePercent", 0)
        volume = q.get("regularMarketVolume", 0)

        if not price or not volume:
            return None

        liquidity = price * volume

        return {
            "price": round(price, 2),
            "change": round(change, 2),
            "volume": int(volume),
            "liquidity": int(liquidity)
        }

    except:
        return None

def analyze(symbol):
    data = get_data(symbol)
    if not data:
        return None

    score = 0

    if data["change"] > 2:
        score += 3
    if data["volume"] > 500000:
        score += 3
    if data["price"] < 10:
        score += 2
    if data["liquidity"] > 1000000:
        score += 2

    if score < 6:
        return None

    entry = data["price"]
    stop = round(entry * 0.96, 2)
    t1 = round(entry * 1.04, 2)
    t2 = round(entry * 1.07, 2)
    t3 = round(entry * 1.10, 2)

    return f"""🚨 إشارة نخبة

📊 السهم: {symbol}
⭐ التقييم: {score}/10

💰 الدخول: {entry}
🛑 الوقف: {stop}

🎯 الهدف 1: {t1}
🎯 الهدف 2: {t2}
🎯 الهدف 3: {t3}

💧 السيولة: {data['liquidity']:,}$
⚡ التغير: {data['change']}%
"""

def bot():
    print("🔥 BOT STARTED", flush=True)
    send("🔥 البوت شغال")

    while True:
        stocks = get_stocks()
        print(f"stocks: {stocks}", flush=True)

        for s in stocks:
            sig = analyze(s)

            if sig and time.time() - sent.get(s, 0) > COOLDOWN:
                send(sig)
                sent[s] = time.time()
                print(f"✅ {s}", flush=True)

            time.sleep(1.5)

        print("🔥 يفحص السوق...", flush=True)
        time.sleep(CHECK_INTERVAL)

@app.route("/")
def home():
    return "RUNNING"

if __name__ == "__main__":
    t = threading.Thread(target=bot)
    t.daemon = True
    t.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
