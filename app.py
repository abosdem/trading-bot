import os
import time
import threading
import requests
from flask import Flask

app = Flask(__name__)

BOT_TOKEN = os.environ.get("8452344889:AAFkEzBOJ5RdWmXAQtxt8s42R_TUWPlrfFo")
CHAT_ID = os.environ.get("912977673")
FINNHUB_API_KEY = os.environ.get("d71aavhr01qot5jcmbq0d71aavhr01qot5jcmbqg")

WATCHLIST = ["TSLA", "NVDA", "AMD", "PLTR", "SOFI", "NIO"]

ALERT_COOLDOWN = 20 * 60
SCAN_INTERVAL = 60

last_alert = {}
last_update_id = 0

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})

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
    target_chat = chat_id or CHAT_ID
    if not target_chat:
        print("Missing CHAT_ID", flush=True)
        return
    tg_api("sendMessage", {"chat_id": target_chat, "text": msg})

def get_finnhub_quote(symbol):
    if not FINNHUB_API_KEY:
        print("Missing FINNHUB_API_KEY", flush=True)
        return None

    try:
        url = "https://finnhub.io/api/v1/quote"
        params = {
            "symbol": symbol,
            "token": FINNHUB_API_KEY
        }

        r = session.get(url, params=params, timeout=12)

        if r.status_code != 200:
            print(f"finnhub quote status error {symbol}: {r.status_code}", flush=True)
            return None

        data = r.json()

        current_price = data.get("c")
        change_percent = data.get("dp")
        high_price = data.get("h")
        prev_close = data.get("pc")

        if current_price in (None, 0) or change_percent is None:
            return None

        return {
            "price": float(current_price),
            "change": float(change_percent),
            "day_high": float(high_price) if high_price not in (None, 0) else None,
            "prev_close": float(prev_close) if prev_close not in (None, 0) else None,
        }

    except Exception as e:
        print(f"finnhub quote error {symbol}: {e}", flush=True)
        return None

def get_finnhub_profile(symbol):
    if not FINNHUB_API_KEY:
        return None

    try:
        url = "https://finnhub.io/api/v1/stock/profile2"
        params = {
            "symbol": symbol,
            "token": FINNHUB_API_KEY
        }

        r = session.get(url, params=params, timeout=12)

        if r.status_code != 200:
            print(f"finnhub profile status error {symbol}: {r.status_code}", flush=True)
            return None

        data = r.json()
        if not isinstance(data, dict):
            return None

        return data

    except Exception as e:
        print(f"finnhub profile error {symbol}: {e}", flush=True)
        return None

def get_finnhub_metrics(symbol):
    if not FINNHUB_API_KEY:
        return None

    try:
        url = "https://finnhub.io/api/v1/stock/metric"
        params = {
            "symbol": symbol,
            "metric": "all",
            "token": FINNHUB_API_KEY
        }

        r = session.get(url, params=params, timeout=12)

        if r.status_code != 200:
            print(f"finnhub metric status error {symbol}: {r.status_code}", flush=True)
            return None

        data = r.json()
        metric = data.get("metric", {})
        if not isinstance(metric, dict):
            return None

        return metric

    except Exception as e:
        print(f"finnhub metric error {symbol}: {e}", flush=True)
        return None

def estimate_liquidity(price, shares_outstanding):
    try:
        if price is None or shares_outstanding in (None, 0):
            return None
        return int(float(price) * float(shares_outstanding))
    except Exception:
        return None

def build_signal(symbol):
    quote = get_finnhub_quote(symbol)
    if not quote:
        return None

    profile = get_finnhub_profile(symbol) or {}
    metric = get_finnhub_metrics(symbol) or {}

    price = quote.get("price")
    change = quote.get("change")
    day_high = quote.get("day_high")
    prev_close = quote.get("prev_close")

    shares_outstanding = profile.get("shareOutstanding")
    avg_volume_10d = metric.get("10DayAverageTradingVolume")

    liquidity = estimate_liquidity(price, shares_outstanding)

    score = 0
    reasons = []

    if change is not None and change > 2:
        score += 3
        reasons.append("تغير قوي")
    if change is not None and change > 4:
        score += 1
        reasons.append("زخم أعلى")

    if price is not None and price < 10:
        score += 1
        reasons.append("سعر مناسب للمضاربة")

    if day_high not in (None, 0) and price >= day_high * 0.985:
        score += 2
        reasons.append("قريب من قمة اليوم")

    if avg_volume_10d not in (None, 0):
        try:
            if float(avg_volume_10d) > 500000:
                score += 2
                reasons.append("متوسط حجم جيد")
            if float(avg_volume_10d) > 1500000:
                score += 1
                reasons.append("متوسط حجم قوي")
        except Exception:
            pass

    if liquidity not in (None, 0):
        if liquidity > 1000000:
            score += 1
            reasons.append("سيولة جيدة")
        if liquidity > 5000000:
            score += 1
            reasons.append("سيولة أعلى")

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
⭐ التقييم: {score}/11

💰 الدخول: {entry}
🛑 الوقف: {stop}

🎯 الهدف 1: {t1}
🎯 الهدف 2: {t2}
🎯 الهدف 3: {t3}

⚡ التغير: {round(change, 2)}%"""

    if day_high not in (None, 0):
        msg += f"\n📍 قمة اليوم: {round(day_high, 2)}"

    if avg_volume_10d not in (None, 0):
        try:
            msg += f"\n📈 متوسط الحجم 10 أيام: {int(float(avg_volume_10d)):,}"
        except Exception:
            pass

    if liquidity not in (None, 0):
        msg += f"\n💧 السيولة التقديرية: {liquidity:,}$"

    msg += f"\n\n✅ الأسباب: {reasons_text}"

    return msg

def market_bot():
    print("🔥 FINNHUB BOT STARTED", flush=True)
    send("🔥 البوت شغال على Finnhub")

    while True:
        try:
            now = time.time()
            print(f"📊 scanning {len(WATCHLIST)} stocks", flush=True)

            for symbol in WATCHLIST:
                signal = build_signal(symbol)

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
            time.sleep(30)

def handle_command(text, chat_id):
    t = text.strip().lower()

    if t == "/start":
        send(
            "🚀 البوت شغال على Finnhub\n\n"
            "الأوامر:\n"
            "/status - حالة البوت\n"
            "/watchlist - قائمة الأسهم\n"
            "/test - رسالة اختبار",
            chat_id=chat_id,
        )

    elif t == "/status":
        send(
            f"✅ البوت يعمل\n"
            f"📊 عدد الأسهم في القائمة: {len(WATCHLIST)}\n"
            f"⏱️ مدة منع التكرار: {ALERT_COOLDOWN // 60} دقيقة\n"
            f"🔁 الفحص كل: {SCAN_INTERVAL} ثانية",
            chat_id=chat_id,
        )

    elif t == "/watchlist":
        send("📋 القائمة:\n" + "\n".join(WATCHLIST), chat_id=chat_id)

    elif t == "/test":
        send("🔥 اختبار البوت ناجح", chat_id=chat_id)

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

@app.route("/", methods=["GET", "POST"])
def home():
    return "OK"

if __name__ == "__main__":
    print("🔥 STARTING BOT...", flush=True)

    threading.Thread(target=market_bot, daemon=True).start()
    threading.Thread(target=telegram_listener, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)
