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

MIN_PRICE = 0.5
MAX_PRICE = 10
MIN_RVOL = 2.0
MIN_CHANGE = 1.0
MIN_VOLUME = 500000
MIN_SCORE = 6

sent = {}

def send(msg):
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing BOT_TOKEN or CHAT_ID", flush=True)
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram error: {e}", flush=True)

def get_finviz_stocks():
    try:
        url = "https://finviz.com/screener.ashx?v=111&f=geo_usa,sh_price_u10,sh_avgvol_o500,sh_relvol_o2,sh_float_u20"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, "lxml")
        tickers = []

        for a in soup.find_all("a"):
            href = a.get("href", "")
            if "quote.ashx?t=" in href:
                t = a.text.strip().upper()
                if t.isalpha() and 1 <= len(t) <= 5 and t not in tickers:
                    tickers.append(t)

        return tickers[:20]
    except Exception as e:
        print(f"Finviz error: {e}", flush=True)
        return []

def get_stock_data(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=5m&range=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15)

        if r.status_code != 200:
            return None

        try:
            data = r.json()
        except Exception:
            return None

        chart = data.get("chart", {})
        result = chart.get("result")
        if not result:
            return None

        quote = result[0].get("indicators", {}).get("quote", [{}])[0]

        closes = [x for x in quote.get("close", []) if x is not None]
        highs = [x for x in quote.get("high", []) if x is not None]
        volumes = [x for x in quote.get("volume", []) if x is not None]

        if len(closes) < 20 or len(highs) < 20 or len(volumes) < 20:
            return None

        price = float(closes[-1])
        prev = float(closes[-2])

        if prev <= 0:
            return None

        change = ((price - prev) / prev) * 100
        last_vol = float(volumes[-1])
        avg_vol = sum(volumes[-20:]) / 20

        if avg_vol <= 0:
            return None

        rvol = last_vol / avg_vol
        breakout = max(highs[-20:-1]) if len(highs) >= 20 else max(highs)
        liquidity = int(price * last_vol)

        return {
            "price": round(price, 2),
            "change": round(change, 2),
            "rvol": round(rvol, 2),
            "volume": int(last_vol),
            "liquidity": liquidity,
            "breakout": round(float(breakout), 2),
            "near_breakout": price >= breakout * 0.995
        }

    except Exception as e:
        print(f"Quote error {symbol}: {e}", flush=True)
        return None

def analyze(symbol):
    data = get_stock_data(symbol)
    if not data:
        return None

    if not (MIN_PRICE <= data["price"] <= MAX_PRICE):
        return None

    score = 0

    if data["rvol"] >= MIN_RVOL:
        score += 3
    if data["change"] >= MIN_CHANGE:
        score += 2
    if data["near_breakout"]:
        score += 3
    if data["volume"] >= MIN_VOLUME:
        score += 2

    if score < MIN_SCORE:
        return None

    entry = data["price"]
    stop = round(entry * 0.96, 2)
    t1 = round(entry * 1.04, 2)
    t2 = round(entry * 1.07, 2)
    t3 = round(entry * 1.10, 2)

    return f"""🚨 إشارة وحش

📊 السهم: {symbol}
⭐ التقييم: {score}/10

💰 الدخول: {entry}
🛑 الوقف: {stop}

🎯 الهدف 1: {t1}
🎯 الهدف 2: {t2}
🎯 الهدف 3: {t3}

💧 السيولة: {data['liquidity']:,}$
📈 RVOL: {data['rvol']}
⚡ تغير 5 دقائق: {data['change']}%
📍 مستوى الاختراق: {data['breakout']}
"""

def bot_loop():
    print("🔥 الوحش بدأ", flush=True)
    send("🔥 الوحش بدأ")

    while True:
        try:
            stocks = get_finviz_stocks()
            print(f"📊 stocks found: {len(stocks)}", flush=True)

            for symbol in stocks:
                signal = analyze(symbol)

                if signal and time.time() - sent.get(symbol, 0) > COOLDOWN:
                    send(signal)
                    sent[symbol] = time.time()
                    print(f"✅ أرسل: {symbol}", flush=True)

                time.sleep(2)

            print("🔥 يفحص السوق...", flush=True)
            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print(f"Loop error: {e}", flush=True)
            time.sleep(60)

@app.route("/", methods=["GET", "POST"])
def home():
    return "ELITE BOT RUNNING"

if __name__ == "__main__":
    print("🔥 STARTING BOT...", flush=True)
    t = threading.Thread(target=bot_loop)
    t.daemon = True
    t.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)
