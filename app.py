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
COOLDOWN_SECONDS = 3600
MIN_PRICE = 0.5
MAX_PRICE = 10
MIN_CHANGE = 2.0
MIN_VOLUME = 500_000
MIN_LIQUIDITY = 1_000_000
MIN_SCORE = 6

sent_signals = {}
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"
})

def send_telegram(message: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing BOT_TOKEN or CHAT_ID", flush=True)
        return
    try:
        session.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": message},
            timeout=10,
        )
    except Exception as e:
        print(f"Telegram error: {e}", flush=True)

def get_finviz_stocks():
    try:
        url = (
            "https://finviz.com/screener.ashx"
            "?v=111&f=geo_usa,sh_price_u10,sh_avgvol_o500,sh_relvol_o2,sh_float_u20"
        )
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            return []

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

def get_quote(symbol: str):
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
        r = session.get(url, timeout=10)

        if r.status_code != 200:
            print(f"Quote status {symbol}: {r.status_code}", flush=True)
            return None

        content_type = r.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            print(f"Quote blocked {symbol}", flush=True)
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

        price = float(price)
        change = float(change)
        volume = int(volume)
        liquidity = int(price * volume)

        return {
            "price": round(price, 2),
            "change": round(change, 2),
            "volume": volume,
            "liquidity": liquidity,
        }
    except Exception as e:
        print(f"Quote error {symbol}: {e}", flush=True)
        return None

def analyze(symbol: str):
    data = get_quote(symbol)
    if not data:
        return None

    price = data["price"]
    change = data["change"]
    volume = data["volume"]
    liquidity = data["liquidity"]

    if not (MIN_PRICE <= price <= MAX_PRICE):
        return None

    score = 0

    if change >= MIN_CHANGE:
        score += 4
    if volume >= MIN_VOLUME:
        score += 3
    if liquidity >= MIN_LIQUIDITY:
        score += 3

    if score < MIN_SCORE:
        return None

    entry = price
    stop = round(entry * 0.96, 2)
    target1 = round(entry * 1.04, 2)
    target2 = round(entry * 1.07, 2)
    target3 = round(entry * 1.10, 2)

    return f"""🚨 إشارة وحش

📊 السهم: {symbol}
⭐ التقييم: {score}/10

💰 الدخول: {entry}
🛑 الوقف: {stop}

🎯 الهدف 1: {target1}
🎯 الهدف 2: {target2}
🎯 الهدف 3: {target3}

💧 السيولة: {liquidity:,}$
⚡ التغير: {change}%
📈 الفوليوم: {volume:,}
"""

def bot_loop():
    print("🔥 الوحش بدأ", flush=True)
    send_telegram("🔥 الوحش بدأ")

    while True:
        try:
            stocks = get_finviz_stocks()
            print(f"📊 stocks found: {len(stocks)}", flush=True)

            for symbol in stocks:
                signal = analyze(symbol)

                if signal and time.time() - sent_signals.get(symbol, 0) > COOLDOWN_SECONDS:
                    send_telegram(signal)
                    sent_signals[symbol] = time.time()
                    print(f"✅ أرسل: {symbol}", flush=True)

                time.sleep(3)

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
    t = threading.Thread(target=bot_loop, daemon=True)
    t.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)
