import os
import time
import threading
import requests
from bs4 import BeautifulSoup
from flask import Flask

app = Flask(__name__)

BOT_TOKEN = os.environ.get("8452344889:AAFkEzBOJ5RdWmXAQtxt8s42R_TUWPlrfFo")
CHAT_ID = os.environ.get("CHAT_ID")

CHECK_INTERVAL = 120
COOLDOWN = 3600

sent = {}

def send(msg):
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

def get_quote(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=5m&range=1d"
        r = requests.get(url, timeout=15).json()

        result = r["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]

        closes = [x for x in quote.get("close", []) if x is not None]
        highs = [x for x in quote.get("high", []) if x is not None]
        volumes = [x for x in quote.get("volume", []) if x is not None]

        if len(closes) < 20 or len(highs) < 20 or len(volumes) < 20:
            return None

        price = float(closes[-1])
        prev = float(closes[-2])
        breakout = max(highs[-20:-1])
        vol = float(volumes[-1])
        avg_vol = sum(volumes[-20:]) / 20

        if avg_vol <= 0 or prev <= 0:
            return None

        change = ((price - prev) / prev) * 100
        rvol = vol / avg_vol
        liq = price * vol

        return {
            "price": round(price, 2),
            "change": round(change, 2),
            "rvol": round(rvol, 2),
            "liq": int(liq),
            "breakout": round(float(breakout), 2),
            "near_breakout": price >= breakout * 0.995,
            "vol": int(vol)
        }
    except Exception as e:
        print(f"Quote error {symbol}: {e}", flush=True)
        return None

def analyze(symbol):
    q = get_quote(symbol)
    if not q:
        return None

    score = 0

    if q["rvol"] >= 2:
        score += 3
    if q["change"] >= 1:
        score += 2
    if q["near_breakout"]:
        score += 3
    if q["vol"] >= 500000:
        score += 2

    if score < 6:
        return None

    entry = q["price"]
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

💧 السيولة: {q['liq']:,}$
📈 RVOL: {q['rvol']}
⚡ تغير 5 دقائق: {q['change']}%
📍 مستوى الاختراق: {q['breakout']}
"""

def bot_loop():
    print("🔥 الوحش بدأ", flush=True)
    send("🔥 الوحش بدأ")

    while True:
        try:
            stocks = get_finviz_stocks()
            print(f"📊 stocks found: {len(stocks)}", flush=True)

            for s in stocks:
                sig = analyze(s)

                if sig and time.time() - sent.get(s, 0) > COOLDOWN:
                    send(sig)
                    sent[s] = time.time()
                    print(f"✅ أرسل: {s}", flush=True)

                time.sleep(1)

            print("🔥 يفحص السوق...", flush=True)
            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print(f"Loop error: {e}", flush=True)
            time.sleep(30)

@app.route("/", methods=["GET", "POST"])
def home():
    return "ELITE BOT RUNNING"
if __name__ == "__main__":
    import os

    print("🔥 STARTING BOT...", flush=True)

    t = threading.Thread(target=bot_loop)
    t.daemon = True
    t.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)
