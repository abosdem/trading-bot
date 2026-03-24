import os
import time
import threading
import requests
from flask import Flask

app = Flask(__name__)

BOT_TOKEN = os.environ.get("8452344889:AAFkEzBOJ5RdWmXAQtxt8s42R_TUWPlrfFo")
CHAT_ID = os.environ.get("912977673")

WATCHLIST = ["TSLA", "NVDA", "AMD", "PLTR", "SOFI", "NIO"]

ALERT_COOLDOWN = 20 * 60
SCAN_INTERVAL = 60
last_alert = {}
last_update_id = 0

session = requests.Session()
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Connection": "keep-alive",
}

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

def get_batch_data(symbols):
    try:
        if not symbols:
            return {}

        symbols_str = ",".join(symbols)
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols_str}"

        r = session.get(url, headers=DEFAULT_HEADERS, timeout=12)

        if r.status_code != 200:
            print(f"yahoo status error: {r.status_code}", flush=True)
            time.sleep(5)
            return {}

        content_type = r.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            print(f"yahoo non-json response: {content_type}", flush=True)
            time.sleep(5)
            return {}

        data = r.json()
        out = {}

        for q in data.get("quoteResponse", {}).get("result", []):
            sym = q.get("symbol")
            if not sym:
                continue

            out[sym] = {
                "price": q.get("regularMarketPrice"),
                "change": q.get("regularMarketChangePercent"),
                "volume": q.get("regularMarketVolume"),
                "day_high": q.get("regularMarketDayHigh"),
                "day_low": q.get("regularMarketDayLow"),
                "prev_close": q.get("regularMarketPreviousClose"),
            }

        return out

    except Exception as e:
        print(f"yahoo error: {e}", flush=True)
        return {}

def build_signal(symbol, d):
    price = d.get("price")
    change = d.get("change")
    volume = d.get("volume")
    day_high = d.get("day_high")
    prev_close = d.get("prev_close")

    if price is None or change is None or volume is None:
        return None

    try:
        price = float(price)
        change = float(change)
        volume = int(volume)
    except Exception:
        return None

    if prev_close in (None, 0):
        prev_close = price

    liquidity = price * volume

    score = 0
    reasons = []

    if change > 2:
        score += 3
        reasons.append("تغير قوي")
    if change > 4:
        score += 1
        reasons.append("زخم أعلى")

    if volume > 500000:
        score += 2
        reasons.append("حجم جيد")
    if volume > 1500000:
        score += 1
        reasons.append("حجم قوي")

    if liquidity > 1000000:
        score += 2
        reasons.append("سيولة قوية")
    if liquidity > 5000000:
        score += 1
        reasons.append("سيولة عالية")

    if price < 10:
        score += 1
        reasons.append("سعر مناسب للمضاربة")

    if day_high not in (None, 0):
        try:
            day_high = float(day_high)
            if price >= day_high * 0.985:
                score += 1
                reasons.append("قريب من قمة اليوم")
        except Exception:
            day_high = None

    if score < 6:
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

⚡ التغير: {round(change, 2)}%
📈 الحجم: {volume:,}
💧 السيولة: {int(liquidity):,}$"""

    if day_high not in (None, 0):
        msg += f"\n📍 قمة اليوم: {round(day_high, 2)}"

    msg += f"\n\n✅ الأسباب: {reasons_text}"
    return msg

def market_bot():
    print("🔥 MARKET BOT STARTED", flush=True)
    send("🔥 البوت شغال")

    while True:
        try:
            data = get_batch_data(WATCHLIST)
            now = time.time()

            print(f"📊 scanning {len(WATCHLIST)} stocks", flush=True)

            if not data:
                print("No market data returned", flush=True)
                time.sleep(10)

            for symbol in WATCHLIST:
                d = data.get(symbol)
                if not d:
                    continue

                signal = build_signal(symbol, d)
                if not signal:
                    continue

                last_t = last_alert.get(symbol, 0)
                if now - last_t > ALERT_COOLDOWN:
                    send(signal)
                    last_alert[symbol] = now
                    print(f"✅ sent: {symbol}", flush=True)

            print("🔥 يفحص السوق...", flush=True)
            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            print(f"market bot error: {e}", flush=True)
            time.sleep(30)

def handle_command(text, chat_id):
    t = text.strip().lower()

    if t == "/start":
        send(
            "🚀 البوت شغال\n\n"
            "الأوامر المتاحة:\n"
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
            r = session.get(url, params=params, headers=DEFAULT_HEADERS, timeout=30)
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
