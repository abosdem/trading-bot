import os
import time
import requests
import threading
from flask import Flask

app = Flask(__name__)

# ===== إعدادات =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY")

# ===== قائمة الأسهم (من صورك) =====
WATCHLIST = [
    "VEEE","SOWG","STI","ATPC","SMSI","LGVN","ACXP",
    "AGRZ","LASE","DDD","ALTO","MOBX","IOVA","PRSO",
    "EDSA","YYAI","JEM","DXST","ASNS","SMWB","TPET",
    "BSM","SND","BOF","SOUN","CPIX","NIO","VSA","MYO","MNDR","FIEE"
]

sent_alerts = {}

# ===== إرسال تيليجرام =====
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=data)

# ===== جلب بيانات السهم =====
def get_stock_data(symbol):
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
    r = requests.get(url).json()
    return r

# ===== تحليل =====
def analyze_stock(symbol):
    data = get_stock_data(symbol)

    price = data.get("c", 0)
    prev = data.get("pc", 0)

    if price == 0 or prev == 0:
        return None

    change = ((price - prev) / prev) * 100

    # شرط الاختراق
    if change < 5:
        return None

    target = price * 1.10
    stop = price * 0.97

    return {
        "price": price,
        "change": change,
        "target": target,
        "stop": stop
    }

# ===== البوت =====
def market_bot():
    while True:
        print("📊 scanning stocks...", flush=True)

        for stock in WATCHLIST:
            try:
                result = analyze_stock(stock)

                if result:
                    # منع التكرار
                    if stock in sent_alerts:
                        continue

                    msg = f"""🚀 اختراق قوي

📊 السهم: {stock}
💰 السعر: {result['price']:.2f}
📈 التغير: {result['change']:.2f}%

🎯 الهدف: {result['target']:.2f}
🛑 وقف الخسارة: {result['stop']:.2f}
"""

                    send_telegram(msg)
                    sent_alerts[stock] = True

            except Exception as e:
                print("error:", e)

        time.sleep(60)  # كل دقيقة

# ===== أوامر تيليجرام =====
def telegram_listener():
    last_update = None

    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            r = requests.get(url).json()

            for update in r["result"]:
                update_id = update["update_id"]

                if last_update and update_id <= last_update:
                    continue

                last_update = update_id

                text = update["message"]["text"]

                if text == "/start":
                    send_telegram("🚀 البوت شغال")

                elif text == "/watchlist":
                    send_telegram("📊 الأسهم:\n" + ", ".join(WATCHLIST))

                elif text == "/status":
                    send_telegram("✅ البوت يعمل بشكل طبيعي")

        except:
            pass

        time.sleep(3)

# ===== Flask =====
@app.route("/")
def home():
    return "OK"

# ===== تشغيل =====
if __name__ == "__main__":
    print("🔥 STARTING BOT...", flush=True)

    threading.Thread(target=market_bot, daemon=True).start()
    threading.Thread(target=telegram_listener, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
