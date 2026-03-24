import os
import time
import threading
import requests
from bs4 import BeautifulSoup
from flask import Flask

app = Flask(__name__)

BOT_TOKEN = os.environ.get("8452344889:AAFkEzBOJ5RdWmXAQtxt8s42R_TUWPlrfFo")
CHAT_ID = os.environ.get("912977673")

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

def get_stocks():
    try:
        url = "https://finviz.com/screener.ashx?v=111&f=geo_usa,sh_price_u10,sh_avgvol_o500,sh_relvol_o2"
        headers = {"User-Agent": "Mozilla/5.0"}

        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")

        tickers = []
        for a in soup.find_all("a"):
            href = a.get("href", "")
            txt = a.get_text(strip=True).upper()

            if "quote.ashx?t=" in href and txt.isalpha() and 1 <= len(txt) <= 5:
                if txt not in tickers:
                    tickers.append(txt)

        return tickers[:15]

    except Exception as e:
        print(f"Finviz error: {e}", flush=True)
        return []

def get_quote(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }

        r = requests.get(url, headers=headers, timeout=10)

        if "application/json" not in r.headers.get("Content-Type", ""):
            print(f"Blocked quote for {symbol}", flush=True)
            return None

        data = r.json()
        result = data.get("quoteResponse", {}).get("result", [])
        if not result:
            return None

        q = result[0]
        price = q.get("regularMarketPrice")
        change = q.get("regularMarketChangePercent")
        volume = q.get("regularMarketVolume")

        if price is None or change is None or volume is None:
            return None

        return {
            "price": round(float(price), 2),
            "change": round(float(change), 2),
            "volume": int(volume),
            "liquidity": int(float(price) * int(volume))
        }

    except Exception as e:
        print(f"Quote error {symbol}: {e}", flush=True)
        return None

def analyze(symbol):
    data = get_quote(symbol)
    if not data:
        return None

    score = 0

    if data["change"] > 2:
        score += 4
    if data["volume"] > 500000:
        score += 3
    if data["liquidity"] > 1000000:
        score += 3

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
📈 الفوليوم: {data['volume']:,}
"""

def run_bot():
    print("🔥 BOT WORKING", flush=True)

    while True:
        try:
            stocks = get_stocks()
            print(f"📊 stocks: {len(stocks)}", flush=True)

            for symbol in stocks:
                signal = analyze(symbol)

                if signal and time.time() - sent.get(symbol, 0) > 3600:
                    send(signal)
                    sent[symbol] = time.time()
                    print(f"✅ sent: {symbol}", flush=True)

                time.sleep(3)

            print("🔥 يفحص السوق...", flush=True)
            time.sleep(180)

        except Exception as e:
            print(f"ERROR: {e}", flush=True)
            time.sleep(60)

@app.route("/")
def home():
    return "OK"

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
