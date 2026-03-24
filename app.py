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
    except:
        pass

def get_stocks_data():
    try:
        url = "https://finviz.com/screener.ashx?v=111&f=geo_usa,sh_price_u10,sh_avgvol_o500,sh_relvol_o2"
        headers = {"User-Agent": "Mozilla/5.0"}

        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")

        rows = soup.select("table.table-light tr")[1:]
        stocks = []

        for row in rows[:15]:
            cols = row.find_all("td")
            if len(cols) < 9:
                continue

            symbol = cols[1].text.strip()
            price = float(cols[8].text)
            change = float(cols[9].text.replace("%", ""))
            volume = int(cols[10].text.replace(",", ""))

            liquidity = int(price * volume)

            stocks.append({
                "symbol": symbol,
                "price": price,
                "change": change,
                "volume": volume,
                "liquidity": liquidity
            })

        return stocks

    except Exception as e:
        print(f"Finviz error: {e}", flush=True)
        return []

def analyze(stock):
    score = 0

    if stock["change"] > 2:
        score += 4
    if stock["volume"] > 500000:
        score += 3
    if stock["liquidity"] > 1000000:
        score += 3

    if score < 6:
        return None

    entry = stock["price"]
    stop = round(entry * 0.96, 2)
    t1 = round(entry * 1.04, 2)
    t2 = round(entry * 1.07, 2)
    t3 = round(entry * 1.10, 2)

    return f"""🚨 إشارة نخبة

📊 السهم: {stock['symbol']}
⭐ التقييم: {score}/10

💰 الدخول: {entry}
🛑 الوقف: {stop}

🎯 الهدف 1: {t1}
🎯 الهدف 2: {t2}
🎯 الهدف 3: {t3}

💧 السيولة: {stock['liquidity']:,}$
⚡ التغير: {stock['change']}%
"""

def bot():
    print("🔥 BOT STARTED", flush=True)
    send("🔥 البوت شغال")

    while True:
        stocks = get_stocks_data()
        print(f"📊 stocks: {len(stocks)}", flush=True)

        for s in stocks:
            signal = analyze(s)

            if signal and time.time() - sent.get(s["symbol"], 0) > 3600:
                send(signal)
                sent[s["symbol"]] = time.time()
                print(f"✅ {s['symbol']}", flush=True)

            time.sleep(1)

        print("🔥 يفحص السوق...", flush=True)
        time.sleep(180)

@app.route("/")
def home():
    return "RUNNING"

if __name__ == "__main__":
    t = threading.Thread(target=bot)
    t.daemon = True
    t.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
