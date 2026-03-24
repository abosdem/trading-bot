import os
import time
import threading
import requests
from flask import Flask

app = Flask(__name__)

# ===== Environment Variables =====
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("CHAT_ID") or "").strip()
FINNHUB_API_KEY = (os.getenv("FINNHUB_API_KEY") or "").strip()

# ===== Settings =====
WATCHLIST = ["TSLA", "NVDA", "AMD", "PLTR", "SOFI", "NIO"]
ALERT_COOLDOWN = 20 * 60
SCAN_INTERVAL = 60

last_alert = {}
last_update_id = 0

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
})

# ===== Telegram =====
def tg_api(method, data=None, timeout=15):
    if not BOT_TOKEN:
        print("Missing BOT_TOKEN", flush=True)
        return None

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        r = session.post(url, data=data, timeout=timeout)
        return r.json()
    except Exception as e:
        print(f"telegram api error: {e}", flush=True)
        return None

def send(msg, chat_id=None):
    target_chat = str(chat_id or CHAT_ID).strip()
    if not target_chat:
        print("Missing CHAT_ID", flush=True)
        return

    tg_api("sendMessage", {"chat_id": target_chat, "text": msg})

# ===== Finnhub =====
def get_finnhub_quote(symbol):
    if not FINNHUB_API_KEY:
        print("Missing FINNHUB_API_KEY", flush=True)
        return None

    try:
        url = "https://finnhub.io/api/v1/quote"
        params = {"symbol": symbol, "token": FINNHUB_API_KEY}
        r = session.get(url, params=params, timeout=12)

        if r.status_code != 200:
            print(f"finnhub status error {symbol}: {r.status_code}", flush=True)
            return None

        data = r.json()

        price = data.get("c")
        change = data.get("dp")
        day_high = data.get("h")

        if price in (None, 0) or change is None:
            return None

        return {
            "price": float(price),
            "change": float(change),
            "day_high": float(day_high) if day_high not in (None, 0) else None,
        }

    except Exception as e:
        print(f"finnhub error {symbol}: {e}", flush=True)
        return None

# ===== Signal Logic =====
def build_signal(symbol, d):
    price = d.get("price")
    change = d.get("change")
    day_high = d.get("day_high")

    if price is None or change is None:
        return None

    score = 0
    reasons = []

    if change > 2:
        score += 3
        reasons.append("تغير قوي")

    if change > 4:
        score += 2
        reasons.append("زخم أعلى")

    if price < 10:
        score += 1
        reasons.append("سعر مناسب للمضاربة")

    if day_high not in (None, 0) and price >= day_high * 0.985:
        score += 2
        reasons.append("قريب من قمة اليوم")

    if score < 5:
        return None

    entry = round(price, 2)
    stop = round(entry * 0.96, 2)
    t1 = round(entry * 1.04, 2)
    t2 = round(entry * 1.07, 2)
    t3 = round(entry * 1.10, 2)

    reasons_text = " - ".join(reasons[:4]) if reasons else "زخم"

    msg = f"""🚨 إشارة قوية

📊 السهم: {symbol}
⭐ التقييم: {score}/8

💰 الدخول: {entry}
🛑 الوقف: {stop}

🎯 الهدف 1: {t1}
🎯 الهدف 2: {t2}
🎯 الهدف 3: {t3}

⚡ التغير: {round(change, 2)}%"""

    if day_high not in (None, 0):
        msg += f"\n📍 قمة اليوم: {round(day_high, 2)}"

    msg += f"\n\n✅ الأسباب: {reasons_text}"
    return msg

# ===== Market Bot =====
def market_bot():
    print("🔥 FINNHUB BOT STARTED", flush=True)

    if BOT_TOKEN and CHAT_ID:
        send("🔥 البوت شغال على Finnhub")

    while True:
        try:
            now = time.time()
            print(f"📊 scanning {len(WATCHLIST)} stocks", flush=True)

            for symbol in WATCHLIST:
                d = get_finnhub_quote(symbol)
                if not d:
                    time.sleep(1)
                    continue

                signal = build_signal(symbol, d)
                if signal:
                    last_t = last_alert.get(symbol, 0)
                    if now - last_t > ALERT_COOLDOWN:
                        send(signal)
                        last_alert[symbol] = now
                        print(f"✅ sent: {symbol}", flush=True)

                time.sleep(1)

            print("🔥 يفحص السوق...", flush=True)
            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            print(f"market bot error: {e}", flush=True)
            time.sleep(20)

# ===== Telegram Commands =====
def handle_command(text, chat_id):
    t = text.strip().lower()

    if t == "/start":
        send(
            "🚀 البوت شغال\n\n"
            "الأوامر:\n"
            "/status - حالة البوت\n"
            "/watchlist - قائمة الأسهم\n"
            "/test - رسالة اختبار",
            chat_id=chat_id
        )

    elif t == "/status":
        send(
            f"✅ البوت يعمل\n"
            f"📊 عدد الأسهم في القائمة: {len(WATCHLIST)}\n"
            f"⏱️ مدة منع التكرار: {ALERT_COOLDOWN // 60} دقيقة\n"
            f"🔁 الفحص كل: {SCAN_INTERVAL} ثانية",
            chat_id=chat_id
        )

    elif t == "/watchlist":
        send("📋 القائمة:\n" + "\n".join(WATCHLIST), chat_id=chat_id)

    elif t == "/test":
        send("🔥 اختبار البوت ناجح", chat_id=chat_id)

# ===== Telegram Listener =====
def telegram_listener():
    global last_update_id
    print("🤖 TELEGRAM LISTENER STARTED", flush=True)

    while True:
        try:
            if not BOT_TOKEN:
                time.sleep(5)
                continue

            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            params = {"timeout": 20, "offset": last_update_id + 1}
            r = session.get(url, params=params, timeout=30)
            data = r.json()

            if not data.get("ok"):
                time.sleep(3)
                continue

            for upd in data.get("result", []):
                last_update_id = upd["update_id"]

                message = upd.get("message", {})
                text = message.get("text", "")
                chat_id = message.get("chat", {}).get("id")

                if not chat_id or not text:
                    continue

                handle_command(text, chat_id)

        except Exception as e:
            print(f"telegram listener error: {e}", flush=True)
            time.sleep(5)

# ===== Flask Routes =====
@app.route("/", methods=["GET", "POST"])
def home():
    return "OK"

# ===== Main =====
if __name__ == "__main__":
    print("🔥 STARTING BOT...", flush=True)
    print("BOT_TOKEN loaded:", bool(BOT_TOKEN), flush=True)
    print("CHAT_ID loaded:", bool(CHAT_ID), flush=True)
    print("FINNHUB_API_KEY loaded:", bool(FINNHUB_API_KEY), flush=True)

    threading.Thread(target=market_bot, daemon=True).start()
    threading.Thread(target=telegram_listener, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)
