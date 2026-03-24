import os
import time
import threading
import requests
from flask import Flask, request

app = Flask(__name__)

# ===== ENV =====
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("CHAT_ID") or "").strip()
FINNHUB_API_KEY = (os.getenv("FINNHUB_API_KEY") or "").strip()

print("BOT_TOKEN:", bool(BOT_TOKEN), flush=True)
print("CHAT_ID:", bool(CHAT_ID), flush=True)
print("FINNHUB:", bool(FINNHUB_API_KEY), flush=True)

# ===== SETTINGS =====
WATCHLIST = ["TSLA", "NVDA", "AMD", "PLTR", "SOFI", "NIO"]
ALERT_COOLDOWN = 20 * 60
SCAN_INTERVAL = 60
last_alert = {}

# ===== TELEGRAM =====
def send(msg, chat_id=None):
    cid = str(chat_id or CHAT_ID).strip()
    if not BOT_TOKEN or not cid:
        print("Missing BOT_TOKEN or CHAT_ID", flush=True)
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": cid, "text": msg}, timeout=10)
    except Exception as e:
        print("send error:", e, flush=True)

# ===== COMMANDS =====
def handle_command(text, chat_id):
    text = (text or "").lower().strip()

    if text == "/start":
        send(
            "🚀 البوت جاهز\n\n"
            "/status - حالة البوت\n"
            "/watchlist - الأسهم\n"
            "/test - اختبار",
            chat_id
        )

    elif text == "/status":
        send("✅ البوت شغال 100%", chat_id)

    elif text == "/watchlist":
        send("📊 القائمة:\n" + "\n".join(WATCHLIST), chat_id)

    elif text == "/test":
        send("🔥 تم الاختبار بنجاح", chat_id)

# ===== FINNHUB =====
def get_price(symbol):
    if not FINNHUB_API_KEY:
        print("Missing FINNHUB_API_KEY", flush=True)
        return None

    try:
        url = "https://finnhub.io/api/v1/quote"
        params = {"symbol": symbol, "token": FINNHUB_API_KEY}
        r = requests.get(url, params=params, timeout=10)

        if r.status_code != 200:
            print(f"finnhub status error {symbol}: {r.status_code}", flush=True)
            return None

        data = r.json()

        price = data.get("c")
        change = data.get("dp")

        if price in (None, 0) or change is None:
            return None

        return {
            "price": float(price),
            "change": float(change)
        }
    except Exception as e:
        print(f"finnhub error {symbol}: {e}", flush=True)
        return None

# ===== MARKET BOT =====
def market_bot():
    print("🔥 MARKET BOT STARTED", flush=True)

    if BOT_TOKEN and CHAT_ID:
        send("🔥 البوت شغال على Finnhub")

    while True:
        try:
            now = time.time()
            print("📊 scanning...", flush=True)

            for symbol in WATCHLIST:
                d = get_price(symbol)
                if not d:
                    time.sleep(1)
                    continue

                if d["change"] > 2:
                    last = last_alert.get(symbol, 0)

                    if now - last > ALERT_COOLDOWN:
                        msg = f"""🚀 فرصة

{symbol}
السعر: {d['price']}
التغير: {round(d['change'], 2)}%
"""
                        send(msg)
                        last_alert[symbol] = now
                        print("sent:", symbol, flush=True)

                time.sleep(1)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            print("bot error:", e, flush=True)
            time.sleep(10)

# ===== WEBHOOK =====
@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json(silent=True)

    if not data:
        return "ok", 200

    message = data.get("message", {})
    text = message.get("text")
    chat_id = message.get("chat", {}).get("id")

    if text and chat_id:
        print("📩", text, flush=True)
        handle_command(text, chat_id)

    return "ok", 200

# ===== ROOT =====
@app.route("/", methods=["GET", "POST"])
def home():
    return "OK", 200

# ===== MAIN =====
if __name__ == "__main__":
    print("🔥 STARTING...", flush=True)

    threading.Thread(target=market_bot, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
