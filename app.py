import requests
import time
import threading
import os
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
from flask import Flask

BOT_TOKEN = os.environ.get("8452344889:AAFkEzBOJ5RdWmXAQtxt8s42R_TUWPlrfFo")
CHAT_ID = os.environ.get("912977673")

app = Flask(__name__)

sent_signals = set()

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=data, timeout=5)
    except:
        pass

# ======= جلب الأسهم من Finviz =======
def get_finviz_stocks():
    url = "https://finviz.com/screener.ashx?v=111&f=sh_price_u10,sh_avgvol_o500,sh_relvol_o2,sh_float_u20"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")

    tickers = []
    for link in soup.find_all("a"):
        href = link.get("href", "")
        if "quote.ashx?t=" in href:
            ticker = link.text.strip()
            if ticker.isupper() and len(ticker) <= 5:
                tickers.append(ticker)

    return list(set(tickers))[:30]  # نخبة فقط

# ======= تحليل السهم =======
def analyze_stock(symbol):
    try:
        df = yf.download(symbol, period="1d", interval="5m", progress=False)
        if df.empty or len(df) < 20:
            return None

        price = df["Close"].iloc[-1]

        volume = df["Volume"].iloc[-1]
        avg_volume = df["Volume"].mean()
        rvol = volume / avg_volume if avg_volume > 0 else 0

        change5 = ((price - df["Close"].iloc[-2]) / df["Close"].iloc[-2]) * 100

        high_break = df["High"].max()

        score = 0

        if rvol > 2:
            score += 3
        if change5 > 1:
            score += 2
        if price >= high_break * 0.98:
            score += 3
        if volume > 500000:
            score += 3

        if score < 6:
            return None

        entry = price
        stop = round(price * 0.96, 2)

        tp1 = round(price * 1.05, 2)
        tp2 = round(price * 1.08, 2)
        tp3 = round(price * 1.10, 2)

        liquidity = volume * price

        return {
            "symbol": symbol,
            "price": round(price, 2),
            "stop": stop,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "rvol": round(rvol, 2),
            "change5": round(change5, 2),
            "liquidity": int(liquidity),
            "score": score
        }

    except:
        return None

# ======= فحص السوق =======
def scan_market():
    send_telegram("🔥 الوحش بدأ يفحص السوق")

    while True:
        try:
            stocks = get_finviz_stocks()

            for symbol in stocks:
                result = analyze_stock(symbol)

                if result and symbol not in sent_signals:
                    sent_signals.add(symbol)

                    msg = f"""
🚨 إشارة نخبة

📊 السهم: {result['symbol']}
🧠 النوع: قبل الانفجار
⭐ التقييم: {result['score']}/11

💰 الدخول: {result['price']}
🛑 الوقف: {result['stop']}

🎯 الهدف 1: {result['tp1']}
🎯 الهدف 2: {result['tp2']}
🎯 الهدف 3: {result['tp3']}

💧 السيولة: {result['liquidity']:,}$
📈 RVOL: {result['rvol']}
⚡ تغير 5 دقائق: {result['change5']}%

🔥 سيولة + زخم + اقتراب اختراق
"""
                    send_telegram(msg)
                    print(f"Signal sent: {symbol}")

            time.sleep(60)

        except Exception as e:
            print("Error:", e)
            time.sleep(30)

@app.route("/")
def home():
    return "🔥 ELITE BOT RUNNING"

if __name__ == "__main__":
    threading.Thread(target=scan_market, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
