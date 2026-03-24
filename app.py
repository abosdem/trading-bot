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

ALERT_COOLDOWN = 30 * 60
SCAN_INTERVAL = 90
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
            "🚀 البوت B+ جاهز\n\n"
            "/status - حالة البوت\n"
            "/watchlist - الأسهم\n"
            "/test - اختبار",
            chat_id
        )

    elif text == "/status":
        send("✅ البوت يعمل بنسخة B+ فلتر اختراق حقيقي", chat_id)

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
        open_price = data.get("o")

        if price in (None, 0) or change is None or prev_close in (None, 0):
            return None

        return {
            "price": float(price),
            "change": float(change),
            "day_high": float(day_high) if day_high not in (None, 0) else None,
            "day_low": float(day_low) if day_low not in (None, 0) else None,
            "prev_close": float(prev_close),
            "open_price": float(open_price) if open_price not in (None, 0) else None,
        }

    except Exception as e:
        print(f"finnhub error {symbol}: {e}", flush=True)
        return None

def build_signal(symbol, d):
    price = d["price"]
    change = d["change"]
    day_high = d["day_high"]
    day_low = d["day_low"]
    prev_close = d["prev_close"]
    open_price = d["open_price"]

    # فلترة أولية
    if price < 0.50:
        return None

    if change < 3:
        return None

    if change > 18:
        return None

    if not day_high or not day_low or not open_price:
        return None

    day_range = day_high - day_low
    if day_range <= 0:
        return None

    # 1) اختراق حقيقي: السعر لازم يكون فوق افتتاح اليوم
    if price <= open_price:
        return None

    # 2) لا نريد مجرد ارتداد من قاع بعيد عن المقاومة
    recovery_ratio = (price - day_low) / day_range
    if recovery_ratio < 0.80:
        return None

    # 3) لازم يكون عند المقاومة تقريباً أو كاسرها
    near_high = price >= day_high * 0.998
    if not near_high:
        return None

    # 4) منع الأسهم الهابطة يومياً رغم الارتداد
    if price <= prev_close * 1.03:
        return None

    # 5) فلترة أسهم مضاربية مناسبة فقط
    if price > 20:
        return None

    score = 0
    reasons = []

    if change >= 3:
        score += 2
        reasons.append("زخم قوي")

    if change >= 5:
        score += 1
        reasons.append("اندفاع واضح")

    if 0.5 <= price <= 10:
        score += 1
        reasons.append("سعر مضاربي")

    if near_high:
        score += 2
        reasons.append("عند قمة اليوم")

    if recovery_ratio >= 0.90:
        score += 1
        reasons.append("سيطرة مشترين")

    if price > open_price:
        score += 1
        reasons.append("فوق الافتتاح")

    if score < 6:
        return None

    entry = round(price, 2)
    stop = round(entry * 0.97, 2)
    t1 = round(entry * 1.04, 2)
    t2 = round(entry * 1.08, 2)
    t3 = round(entry * 1.12, 2)

    reasons_text = " - ".join(reasons[:4])

    return f"""🚨 اختراق حقيقي

📊 السهم: {symbol}
⭐ التقييم: {score}/8

💰 الدخول: {entry}
🛑 وقف الخسارة: {stop}

🎯 الهدف 1: {t1}
🎯 الهدف 2: {t2}
🎯 الهدف 3: {t3}

⚡ التغير: {round(change, 2)}%
📍 قمة اليوم: {round(day_high, 2)}
📍 قاع اليوم: {round(day_low, 2)}
📍 الافتتاح: {round(open_price, 2)}

✅ الأسباب: {reasons_text}"""

def market_bot():
    print("🔥 B+ BOT STARTED", flush=True)

    if BOT_TOKEN and CHAT_ID:
        send("🔥 البوت B+ شغال")

    while True:
        try:
            now = time.time()
            print("📊 scanning B+...", flush=True)

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
    print("🔥 STARTING B+...", flush=True)
    print("BOT_TOKEN:", bool(BOT_TOKEN), flush=True)
    print("CHAT_ID:", bool(CHAT_ID), flush=True)
    print("FINNHUB:", bool(FINNHUB_API_KEY), flush=True)

    threading.Thread(target=market_bot, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
