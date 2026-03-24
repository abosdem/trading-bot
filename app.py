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

# ===== WATCHLIST =====
WATCHLIST = [
    "VEEE", "SOWG", "STI", "ATPC", "SMSI", "LGVN", "ACXP",
    "AGRZ", "LASE", "DDD", "ALTO", "MOBX", "IOVA", "PRSO",
    "EDSA", "YYAI", "JEM", "DXST", "ASNS", "SMWB", "TPET",
    "BSM", "SND", "BOF", "SOUN", "CPIX", "NIO", "VSA",
    "MYO", "MNDR", "FIEE"
]

# ===== SETTINGS =====
ALERT_COOLDOWN = 45 * 60
SCAN_INTERVAL = 90

MIN_PRICE = 0.50
MAX_PRICE = 20.0
MIN_CHANGE = 3.0
MAX_CHANGE = 12.0

BREAKOUT_BUFFER = 1.0015      # لازم السعر يكون فوق القمة السابقة قليلًا
NEAR_HIGH_BUFFER = 0.9985
MAX_RETESTS = 2               # لو تكرر لمس القمة كثير نرفض
MIN_RECOVERY_RATIO = 0.85
MIN_OPEN_DRIVE = 0.025

last_alert = {}
touch_state = {}  # symbol -> {"high": x, "touches": n, "last_seen": t}

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
})

# ===== TELEGRAM =====
def send_message(text, chat_id=None):
    target_chat_id = str(chat_id or CHAT_ID).strip()

    if not BOT_TOKEN or not target_chat_id:
        print("Missing BOT_TOKEN or CHAT_ID", flush=True)
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        response = session.post(
            url,
            data={"chat_id": target_chat_id, "text": text},
            timeout=15
        )
        print(f"Telegram send status: {response.status_code}", flush=True)
    except Exception as e:
        print(f"Telegram send error: {e}", flush=True)

def handle_command(text, chat_id):
    cmd = (text or "").strip().lower()

    if cmd == "/start":
        send_message(
            "🚀 البوت 9/10 جاهز\n\n"
            "/status - حالة البوت\n"
            "/watchlist - قائمة الأسهم\n"
            "/test - اختبار",
            chat_id
        )

    elif cmd == "/status":
        send_message("✅ البوت يعمل بفلترة 9/10", chat_id)

    elif cmd == "/watchlist":
        send_message("📊 القائمة:\n" + "\n".join(WATCHLIST), chat_id)

    elif cmd == "/test":
        send_message("🔥 تم الاختبار بنجاح", chat_id)

# ===== FINNHUB =====
def get_quote(symbol):
    if not FINNHUB_API_KEY:
        print("Missing FINNHUB_API_KEY", flush=True)
        return None

    url = "https://finnhub.io/api/v1/quote"
    params = {
        "symbol": symbol,
        "token": FINNHUB_API_KEY
    }

    try:
        response = session.get(url, params=params, timeout=15)

        if response.status_code != 200:
            print(f"Finnhub status error {symbol}: {response.status_code}", flush=True)
            return None

        data = response.json()

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
        print(f"Finnhub error {symbol}: {e}", flush=True)
        return None

# ===== TOUCH FILTER =====
def repeated_touch_filter(symbol, day_high, price):
    """
    يمنع الأسهم التي تعيد لمس نفس القمة كثيرًا بدون اختراق فعلي.
    """
    now = time.time()
    state = touch_state.get(symbol)

    if state is None:
        touch_state[symbol] = {
            "high": day_high,
            "touches": 1 if price >= day_high * NEAR_HIGH_BUFFER else 0,
            "last_seen": now
        }
        return False

    # إذا تغيرت قمة اليوم بشكل واضح، نعيد التصفير
    if abs(day_high - state["high"]) > max(0.01, day_high * 0.003):
        touch_state[symbol] = {
            "high": day_high,
            "touches": 1 if price >= day_high * NEAR_HIGH_BUFFER else 0,
            "last_seen": now
        }
        return False

    # إذا مر وقت طويل بدون متابعة، نخفف الحالة
    if now - state["last_seen"] > 20 * 60:
        state["touches"] = 0

    if price >= day_high * NEAR_HIGH_BUFFER:
        state["touches"] += 1

    state["last_seen"] = now
    touch_state[symbol] = state

    return state["touches"] > MAX_RETESTS

# ===== SIGNAL FILTER =====
def build_signal(symbol, quote_data):
    price = quote_data["price"]
    change = quote_data["change"]
    day_high = quote_data["day_high"]
    day_low = quote_data["day_low"]
    prev_close = quote_data["prev_close"]
    open_price = quote_data["open_price"]

    if price < MIN_PRICE or price > MAX_PRICE:
        return None

    if change < MIN_CHANGE or change > MAX_CHANGE:
        return None

    if not day_high or not day_low or not open_price:
        return None

    day_range = day_high - day_low
    if day_range <= 0:
        return None

    # 1) لازم السهم أخضر وواضح
    if price <= prev_close:
        return None

    # 2) لازم فوق الافتتاح
    if price <= open_price:
        return None

    # 3) لازم يكون راجع من القاع بقوة
    recovery_ratio = (price - day_low) / day_range
    if recovery_ratio < MIN_RECOVERY_RATIO:
        return None

    # 4) لازم الاندفاع من الافتتاح واضح
    open_drive = (price - open_price) / open_price
    if open_drive < MIN_OPEN_DRIVE:
        return None

    # 5) فلتر التأخر: إذا السعر بعيد جدًا عن الافتتاح نرفض
    if open_drive > 0.18:
        return None

    # 6) فلتر الاختراق الحقيقي
    real_breakout = price > day_high * BREAKOUT_BUFFER
    near_high = price >= day_high * NEAR_HIGH_BUFFER

    if not (real_breakout or near_high):
        return None

    # 7) إذا مجرد ضغط تحت القمة، لازم يكون قوي جدًا
    if near_high and not real_breakout:
        if change < 5:
            return None
        if recovery_ratio < 0.90:
            return None
        if open_drive < 0.04:
            return None

    # 8) فلتر التكرار
    if repeated_touch_filter(symbol, day_high, price):
        return None

    score = 0
    reasons = []

    if change >= 3:
        score += 2
        reasons.append("زخم قوي")

    if change >= 5:
        score += 1
        reasons.append("اندفاع واضح")

    if MIN_PRICE <= price <= 10:
        score += 1
        reasons.append("سعر مضاربي")

    if real_breakout:
        score += 3
        reasons.append("اختراق فعلي")
    elif near_high:
        score += 1
        reasons.append("ضغط نظيف")

    if recovery_ratio >= 0.90:
        score += 1
        reasons.append("سيطرة مشترين")

    if price > open_price:
        score += 1
        reasons.append("فوق الافتتاح")

    if open_drive >= 0.04:
        score += 1
        reasons.append("اندفاع من الافتتاح")

    if score < 7:
        return None

    entry = round(price, 2)
    stop = round(entry * 0.97, 2)
    target1 = round(entry * 1.04, 2)
    target2 = round(entry * 1.08, 2)
    target3 = round(entry * 1.12, 2)

    reasons_text = " - ".join(reasons[:4])
    signal_type = "اختراق فعلي" if real_breakout else "ضغط قوي قبل الاختراق"

    message = (
        f"🚨 {signal_type}\n\n"
        f"📊 السهم: {symbol}\n"
        f"⭐ التقييم: {score}/10\n\n"
        f"💰 الدخول: {entry}\n"
        f"🛑 وقف الخسارة: {stop}\n\n"
        f"🎯 الهدف 1: {target1}\n"
        f"🎯 الهدف 2: {target2}\n"
        f"🎯 الهدف 3: {target3}\n\n"
        f"⚡ التغير: {round(change, 2)}%\n"
        f"📍 قمة اليوم: {round(day_high, 2)}\n"
        f"📍 قاع اليوم: {round(day_low, 2)}\n"
        f"📍 الافتتاح: {round(open_price, 2)}\n\n"
        f"✅ الأسباب: {reasons_text}"
    )

    return message

# ===== BOT =====
def market_bot():
    print("🔥 BOT 9/10 STARTED", flush=True)

    if BOT_TOKEN and CHAT_ID:
        send_message("🔥 البوت 9/10 شغال")

    while True:
        try:
            now = time.time()
            print("📊 scanning 9/10...", flush=True)

            for symbol in WATCHLIST:
                quote_data = get_quote(symbol)

                if not quote_data:
                    time.sleep(1)
                    continue

                signal = build_signal(symbol, quote_data)

                if signal:
                    last_time = last_alert.get(symbol, 0)

                    if now - last_time > ALERT_COOLDOWN:
                        send_message(signal)
                        last_alert[symbol] = now
                        print(f"sent: {symbol}", flush=True)

                time.sleep(1)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            print(f"bot error: {e}", flush=True)
            time.sleep(10)

# ===== WEBHOOK =====
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    try:
        data = request.get_json(force=True, silent=False)
        print(f"🔥 TELEGRAM UPDATE: {data}", flush=True)

        if not data:
            return "ok", 200

        message = data.get("message", {})
        text = message.get("text", "")
        chat_id = message.get("chat", {}).get("id")

        if text and chat_id:
            print(f"📩 TEXT: {text}", flush=True)
            handle_command(text, str(chat_id))

        return "ok", 200

    except Exception as e:
        print(f"telegram_webhook error: {e}", flush=True)
        return "ok", 200

# ===== ROOT =====
@app.route("/", methods=["GET", "POST"])
def home():
    return "OK", 200

# ===== MAIN =====
if __name__ == "__main__":
    print("🔥 STARTING 9/10...", flush=True)
    print("BOT_TOKEN:", bool(BOT_TOKEN), flush=True)
    print("CHAT_ID:", bool(CHAT_ID), flush=True)
    print("FINNHUB:", bool(FINNHUB_API_KEY), flush=True)

    threading.Thread(target=market_bot, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
