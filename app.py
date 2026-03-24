import os
import time
import threading
import requests
from flask import Flask

app = Flask(__name__)

# قراءة المتغيرات
BOT_TOKEN = (os.getenv("8452344889:AAFkEzBOJ5RdWmXAQtxt8s42R_TUWPlrfFo") or "").strip()
CHAT_ID = (os.getenv("912977673") or "").strip()

FINNHUB_API_KEY = (
    os.getenv("FINNHUB_API_KEY")
    or os.getenv("FINNHUB_KEY")
    or os.getenv("API_KEY")
    or ""
).strip()

# تشخيص
print("BOT_TOKEN loaded:", bool(BOT_TOKEN), flush=True)
print("CHAT_ID loaded:", bool(CHAT_ID), flush=True)
print("FINNHUB_API_KEY loaded:", bool(FINNHUB_API_KEY), flush=True)

if FINNHUB_API_KEY:
    print("FINNHUB key prefix:", FINNHUB_API_KEY[:4], flush=True)
else:
    print("FINNHUB key is missing ❌", flush=True)


# إعدادات
WATCHLIST = ["TSLA", "NVDA", "AMD", "PLTR", "SOFI", "NIO"]
ALERT_COOLDOWN = 20 * 60
last_alert = {}


# إرسال تيليجرام
def send(msg):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram not configured ❌", flush=True)
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except Exception as e:
        print("send error:", e, flush=True)


# جلب البيانات من Finnhub
def get_data(symbol):
    if not FINNHUB_API_KEY:
        return None

    try:
        url = "https://finnhub.io/api/v1/quote"
        params = {
            "symbol": symbol,
            "token": FINNHUB_API_KEY
        }

        r = requests.get(url, params=params, timeout=10)

        print(f"{symbol} status:", r.status_code, flush=True)

        if r.status_code != 200:
            return None

        data = r.json()

        return {
            "price": data.get("c"),
            "change": data.get("dp")
        }

    except Exception as e:
        print("finnhub error:", e, flush=True)
        return None


# البوت
def run_bot():
    print("🔥 BOT STARTED", flush=True)

    send("🔥 البوت اشتغل")

    while True:
        print("📊 scanning stocks...", flush=True)

        for s in WATCHLIST:
            if not FINNHUB_API_KEY:
                print("Missing FINNHUB_API_KEY ❌", flush=True)
                time.sleep(5)
                continue

            d = get_data(s)

            if not d:
                continue

            if d["change"] is None:
                continue

            now = time.time()

            # شرط 2%
            if d["change"] > 2:
                last_t = last_alert.get(s, 0)

                if now - last_t > ALERT_COOLDOWN:
                    msg = f"""🚀 فرصة

{s}
السعر: {d['price']}
التغير: {round(d['change'], 2)}%
"""
                    send(msg)
                    last_alert[s] = now
                    print("sent:", s, flush=True)

            time.sleep(2)

        time.sleep(60)


# Flask (عشان Render)
@app.route("/")
def home():
    return "OK"


if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
