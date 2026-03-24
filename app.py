import requests
import time
import threading
import os
from bs4 import BeautifulSoup
from flask import Flask

BOT_TOKEN = os.environ.get("8452344889:AAFkEzBOJ5RdWmXAQtxt8s42R_TUWPlrfFo")
CHAT_ID = os.environ.get("912977673")

app = Flask(__name__)
sent = set()

# ===== Telegram =====
def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# ===== Finviz =====
def get_stocks():
    url = "https://finviz.com/screener.ashx?v=111&f=sh_price_u10,sh_avgvol_o500,sh_relvol_o2,sh_float_u20"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")

    tickers = []
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if "quote.ashx?t=" in href:
            t = a.text.strip()
            if t.isupper() and len(t) <= 5:
                tickers.append(t)

    return list(set(tickers))[:20]

# ===== بيانات مباشرة =====
def get_data(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=5m&range=1d"
        r = requests.get(url).json()

        result = r["chart"]["result"][0]
        close = result["indicators"]["quote"][0]["close"]
        volume = result["indicators"]["quote"][0]["volume"]

        if not close or len(close) < 5:
            return None

        price = close[-1]
        prev = close[-2]

        vol = volume[-1]
        avg_vol = sum(volume[-20:]) / 20 if len(volume) >= 20 else 0

        if avg_vol == 0:
            return None

        rvol = vol / avg_vol
        change = ((price - prev) / prev) * 100

        return price, rvol, change, vol

    except:
        return None

# ===== تحليل =====
def analyze(symbol):
    data = get_data(symbol)
    if not data:
        return None

    price, rvol, change, volume = data

    score = 0
    if rvol > 2: score += 3
    if change > 1: score += 2
    if volume > 500000: score += 3

    if score < 5:
        return None

    entry = round(price, 2)
    stop = round(price * 0.96, 2)

    tp1 = round(price * 1.05, 2)
    tp2 = round(price * 1.08, 2)
    tp3 = round(price * 1.10, 2)

    liquidity = int(price * volume)

    return {
        "symbol": symbol,
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "rvol": round(rvol, 2),
        "change": round(change, 2),
        "liq": liquidity,
        "score": score
    }

# ===== البوت =====
def bot():
    send("🔥 الوحش الاحترافي بدأ")

    while True:
        try:
            stocks = get_stocks()

            for s in stocks:
                res = analyze(s)

                if res and s not in sent:
                    sent.add(s)

                    msg = f"""
🚨 إشارة نخبة

📊 {res['symbol']}
⭐ {res['score']}/10

💰 دخول: {res['entry']}
🛑 وقف: {res['stop']}

🎯 1: {res['tp1']}
🎯 2: {res['tp2']}
🎯 3: {res['tp3']}

💧 {res['liq']:,}$
📈 RVOL {res['rvol']}
⚡ {res['change']}%

🔥 زخم + سيولة
"""
                    send(msg)
                    print("Signal:", s)

                time.sleep(1)

            time.sleep(60)

        except Exception as e:
            print("ERR:", e)
            time.sleep(30)

# ===== Flask =====
@app.route("/")
def home():
    return "🔥 PRO BOT RUNNING"

# ===== تشغيل =====
if __name__ == "__main__":
    threading.Thread(target=bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
