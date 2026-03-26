import os
import time
import threading
import requests
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID", "912977673")

WATCHLIST = ["VSA","NIO","CPIX","SOUN","BOF","SND"]

ALERT_COOLDOWN = 1800
SCAN_INTERVAL = 40

last_alert = {}

def send(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg}
        )
    except:
        pass

def get_quote(symbol):
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": symbol, "token": FINNHUB_API_KEY}
        )
        d = r.json()
        return d
    except:
        return None

def check(symbol, d):
    price = d.get("c")
    change = d.get("dp")
    high = d.get("h")
    low = d.get("l")
    open_p = d.get("o")

    if not price or not change:
        return None

    if price < 0.5 or price > 20:
        return None

    if change < 2:
        return None

    if price <= open_p:
        return None

    if high <= low:
        return None

    recovery = (price - low) / (high - low)

    if recovery < 0.7:
        return None

    if price < high * 0.97:
        return None

    return f"""🚨 إشارة

📊 {symbol}
💰 {round(price,2)}
⚡ {round(change,2)}%
"""

def bot():
    print("🔥 RUNNING", flush=True)

    while True:
        for s in WATCHLIST:
            d = get_quote(s)

            if not d:
                print("no data", s, flush=True)
                continue

            sig = check(s, d)

            if sig:
                now = time.time()
                if now - last_alert.get(s,0) > ALERT_COOLDOWN:
                    send(sig)
                    last_alert[s] = now
                    print("sent", s, flush=True)
                else:
                    print("cooldown", s, flush=True)
            else:
                print("no setup", s, flush=True)

        time.sleep(SCAN_INTERVAL)

@app.route("/")
def home():
    return "OK"

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.json
    msg = data.get("message", {})
    user = str(msg.get("from", {}).get("id"))

    if user != ALLOWED_USER_ID:
        return "ok"

    text = msg.get("text")

    if text == "/test":
        send("🔥 شغال")

    return "ok"

if __name__ == "__main__":
    threading.Thread(target=bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
