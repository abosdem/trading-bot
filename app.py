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

WATCHLIST = [
    "VSA","NIO","CPIX","SOUN","BOF",
    "SND","PRSO","AGRZ","LASE","DDD"
]

ALERT_COOLDOWN = 1800
SCAN_INTERVAL = 40
DELAY = 1.2

MIN_PRICE = 0.5
MAX_PRICE = 20
MIN_CHANGE = 2

last_alert = {}

session = requests.Session()

# ===== TELEGRAM =====
def send(msg):
    try:
        session.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except:
        pass

# ===== DATA =====
def get_quote(symbol):
    try:
        r = session.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": symbol, "token": FINNHUB_API_KEY},
            timeout=10
        )
        d = r.json()

        if not d.get("c"):
            return None

        return {
            "price": d["c"],
            "change": d["dp"],
            "high": d["h"],
            "low": d["l"],
            "open": d["o"]
        }
    except:
        return None

# ===== SIGNAL =====
def check(symbol, q):

    price = q["price"]
    change = q["change"]

    if price < MIN_PRICE or price > MAX_PRICE:
        return None

    if change < MIN_CHANGE:
        return None

    if price <= q["open"]:
        return None

    day_range = q["high"] - q["low"]
    if day_range <= 0:
        return None

    recovery = (price - q["low"]) / day_range

    if recovery < 0.7:
        return None

    near_high = price >= q["high"] * 0.97

    if not near_high:
        return None

    score = 0

    if change >= 3: score += 2
    if change >= 5: score += 1
    if recovery > 0.85: score += 1

    if score < 3:
        return None

    return f"""🚨 إشارة

📊 {symbol}
⭐ {score}/5

💰 {round(price,2)}
🎯 {round(price*1.05,2)} / {round(price*1.1,2)}
🛑 {round(price*0.96,2)}

⚡ {round(change,2)}%
"""

# ===== BOT =====
def bot():
    print("🔥 RUNNING")

    while True:
        for s in WATCHLIST:

            q = get_quote(s)

            if not q:
                print(s, "no data")
                time.sleep(DELAY)
                continue

            signal = check(s, q)

            if signal:
                now = time.time()

                if now - last_alert.get(s, 0) > ALERT_COOLDOWN:
                    send(signal)
                    last_alert[s] = now
                    print("sent:", s)
                else:
                    print(s, "cooldown")

            else:
                print(s, "no setup")

            time.sleep(DELAY)

        time.sleep(SCAN_INTERVAL)

# ===== WEBHOOK =====
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

@app.route("/")
def home():
    return "OK"

# ===== RUN =====
if __name__ == "__main__":
    threading.Thread(target=bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
