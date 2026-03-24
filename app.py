import os
import time
import threading
import requests
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("CHAT_ID") or "").strip()
FINNHUB_API_KEY = (os.getenv("FINNHUB_API_KEY") or "").strip()

WATCHLIST = [
    "VEEE","SOWG","STI","ATPC","SMSI","LGVN","ACXP",
    "AGRZ","LASE","DDD","ALTO","MOBX","IOVA","PRSO",
    "EDSA","YYAI","JEM","DXST","ASNS","SMWB","TPET",
    "BSM","SND","BOF","SOUN","CPIX","NIO","VSA","MYO","MNDR","FIEE"
]

ALERT_COOLDOWN = 20 * 60
SCAN_INTERVAL = 60
last_alert = {}

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
})

def send(msg, chat_id=None):
    cid = str(chat_id or CHAT_ID).strip()
    if not BOT_TOKEN or not cid:
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        session.post(url, data={"chat_id": cid, "text": msg}, timeout=10)
    except Exception as e:
        print("send error:", e, flush=True)

def handle_command(text, chat_id):
    text = (text or "").strip().lower()

    if text == "/start":
        send(
            "🚀 البوت الوحش جاهز\n\n"
            "/status - حالة البوت\n"
            "/watchlist - الأسهم\n"
            "/test - اختبار",
            chat_id
        )

    elif text == "/status":
        send("✅ البوت يعمل بشكل طبيعي", chat_id)

    elif text == "/watchlist":
        send("📊 القائمة:\n" + "\n".join(WATCHLIST), chat_id)

    elif text == "/test":
        send("🔥 تم الاختبار بنجاح", chat_id)

def get_quote(symbol):
    if not FINNHUB_API_KEY:
        print("Missing FINNHUB_API_KEY", flush=True)
        return None

    try:
        url = "https://finnhub.io/api/v1/quote"
        params = {"symbol": symbol, "token": FINNHUB_API_KEY}
        r = session.get(url, params=params, timeout=10)

        if r.status_code != 200:
            print(f"finnhub status error {symbol}: {r.status_code}", flush=True)
            return None

        data = r.json()

        price = data.get("c")
        change = data.get("dp")
        day_high = data.get("h")
        day_low = data.get("l")
        prev_close = data.get("pc")

        if price in (None, 0) or change is None:
            return None

        return {
            "price": float(price),
            "change": float(change),
            "day_high": float(day_high) if day_high not in (None, 0) else None,
            "day_low": float(day_low) if day_low not in (None, 0) else None,
            "prev_close": float(prev_close) if prev_close not in (None, 0) else None,
        }

    except Exception as e:
        print(f"finnhub error {symbol}: {e}", flush=True)
        return None

def build_signal(symbol, d):
    price = d["price"]
    change = d["change"]
    day_high = d["day_high"]

    score = 0
    reasons = []

    if price < 0.3:
        return None

    if change > 1.5:
        score += 2
        reasons.append("بداية زخم")
    if change > 3:
        score += 2
        reasons.append("زخم قوي")
    if change > 5:
        score += 1
        reasons.append("اختراق واضح")

    if price < 10:
        score += 1
        reasons.append("سعر مضاربي")

    if day_high not in (None, 0):
        if price >= day_high * 0.995:
            score += 2
            reasons.append("قريب من قمة اليوم")

    if score < 4:
        return None

    entry = round(price, 2)
    stop = round(entry * 0.96, 2)
    t1 = round(entry * 1.04, 2)
    t2 = round(entry * 1.08, 2)
    t3 = round(entry * 1.12, 2)

    reasons_text = " - ".join(reasons[:4]) if reasons else "زخم"

    return f"""🚨 إشارة اختراق

📊 السهم: {symbol}
⭐ التقييم: {score}/8

💰 الدخول: {entry}
🛑 وقف الخسارة: {stop}

🎯 الهدف 1: {t1}
🎯 الهدف 2: {t2}
🎯 الهدف 3: {t3}

⚡ التغير: {round(change, 2)}%""" + (
        f"\n📍 قمة اليوم: {round(day_high, 2)}" if day_high else ""
    ) + f"\n\n✅ الأسباب: {reasons_text}"

def market_bot():
    print("🔥 MARKET BOT STARTED", flush=True)

    if BOT_TOKEN and CHAT_ID:
        send("🔥 البوت شغال على Finnhub")

    while True:
        try:
            now = time.time()
            print("📊 scanning...", flush=True)

            for symbol in WATCHLIST:
                d = get_quote(symbol)
                if not d:
                    time.sleep(1)
                    continue

                signal = build_signal(symbol, d)
                if signal:
                    last_t = last_alert.get(symbol, 0)
                    if now - last_t > ALERT_COOLDOWN:
                        send(signal)
                        last_alert[symbol] = now
                        print("sent:", symbol, flush=True)

                time.sleep(1)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            print("bot error:", e, flush=True)
            time.sleep(10)

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
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

@app.route("/", methods=["GET", "POST"])
def home():
    return "OK", 200

if __name__ == "__main__":
    print("🔥 STARTING...", flush=True)
    print("BOT_TOKEN:", bool(BOT_TOKEN), flush=True)
    print("CHAT_ID:", bool(CHAT_ID), flush=True)
    print("FINNHUB:", bool(FINNHUB_API_KEY), flush=True)

    threading.Thread(target=market_bot, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
