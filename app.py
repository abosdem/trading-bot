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

# ===== SECURITY =====
ALLOWED_USER_ID = "912977673"

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
MAX_CHANGE = 15.0

MIN_VOLUME = 500000
STRONG_VOLUME = 1000000

NEAR_HIGH_BUFFER = 0.9985
NEW_HIGH_BUFFER = 1.0010

PRESSURE_RECOVERY_MIN = 0.82
PRESSURE_DRIVE_MIN = 0.02

BREAKOUT_RECOVERY_MIN = 0.88
BREAKOUT_DRIVE_MIN = 0.03

# ===== RUNTIME STATE =====
last_alert = {}
symbol_state = {}

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
            "🚀 البوت الوحش جاهز\n\n"
            "/status - حالة البوت\n"
            "/watchlist - قائمة الأسهم\n"
            "/test - اختبار",
            chat_id
        )

    elif cmd == "/status":
        send_message("✅ البوت يعمل بالنسخة المطورة", chat_id)

    elif cmd == "/watchlist":
        send_message("📊 القائمة:\n" + "\n".join(WATCHLIST), chat_id)

    elif cmd == "/test":
        send_message("🔥 الاختبار ناجح", chat_id)

    else:
        send_message("📩 الأمر غير معروف", chat_id)

# ===== FINNHUB =====
def get_quote(symbol):
    if not FINNHUB_API_KEY:
        print("Missing FINNHUB_API_KEY", flush=True)
        return None

    url = "https://finnhub.io/api/v1/quote"
    params = {"symbol": symbol, "token": FINNHUB_API_KEY}

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
        volume = data.get("v")

        if price in (None, 0) or change is None or prev_close in (None, 0):
            return None

        return {
            "price": float(price),
            "change": float(change),
            "day_high": float(day_high) if day_high not in (None, 0) else None,
            "day_low": float(day_low) if day_low not in (None, 0) else None,
            "prev_close": float(prev_close),
            "open_price": float(open_price) if open_price not in (None, 0) else None,
            "volume": float(volume) if volume not in (None, 0) else 0.0,
        }

    except Exception as e:
        print(f"Finnhub error {symbol}: {e}", flush=True)
        return None

# ===== SIGNAL ENGINE =====
def build_signal(symbol, q):
    price = q["price"]
    change = q["change"]
    day_high = q["day_high"]
    day_low = q["day_low"]
    prev_close = q["prev_close"]
    open_price = q["open_price"]
    volume = q["volume"]

    if price < MIN_PRICE or price > MAX_PRICE:
        return None

    if change < MIN_CHANGE or change > MAX_CHANGE:
        return None

    if volume < MIN_VOLUME:
        return None

    if not day_high or not day_low or not open_price:
        return None

    if price <= prev_close:
        return None

    if price <= open_price:
        return None

    day_range = day_high - day_low
    if day_range <= 0:
        return None

    recovery_ratio = (price - day_low) / day_range
    open_drive = (price - open_price) / open_price

    if recovery_ratio < PRESSURE_RECOVERY_MIN:
        return None

    if open_drive < PRESSURE_DRIVE_MIN:
        return None

    near_high = price >= day_high * NEAR_HIGH_BUFFER

    state = symbol_state.get(symbol, {})
    prev_seen_high = state.get("last_seen_high")
    prev_seen_price = state.get("last_seen_price")
    prev_seen_volume = state.get("last_seen_volume")

    breakout_confirmed = (
        prev_seen_high is not None
        and day_high > prev_seen_high * NEW_HIGH_BUFFER
        and price >= day_high * 0.999
        and recovery_ratio >= BREAKOUT_RECOVERY_MIN
        and open_drive >= BREAKOUT_DRIVE_MIN
        and volume >= STRONG_VOLUME
    )

    pressure_setup = (
        not breakout_confirmed
        and near_high
        and recovery_ratio >= 0.86
        and open_drive >= 0.025
        and volume >= MIN_VOLUME
    )

    if not breakout_confirmed and not pressure_setup:
        return None

    if prev_seen_price is not None and prev_seen_volume is not None:
        price_growth = (price - prev_seen_price) / prev_seen_price if prev_seen_price > 0 else 0
        volume_growth = volume - prev_seen_volume

        if pressure_setup and price_growth < -0.002:
            return None

        if breakout_confirmed and volume_growth < 0:
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

    if volume >= MIN_VOLUME:
        score += 1
        reasons.append("سيولة مؤكدة")

    if volume >= STRONG_VOLUME:
        score += 1
        reasons.append("سيولة قوية")

    if recovery_ratio >= 0.90:
        score += 1
        reasons.append("سيطرة مشترين")

    if open_drive >= 0.04:
        score += 1
        reasons.append("اندفاع من الافتتاح")

    if breakout_confirmed:
        score += 2
        reasons.append("اختراق مؤكد")
        signal_type = "اختراق مؤكد"
    else:
        score += 1
        reasons.append("ضغط قبل الاختراق")
        signal_type = "ضغط قوي قبل الاختراق"

    if score < 7:
        return None

    entry = round(price, 2)
    stop = round(entry * 0.97, 2)
    target1 = round(entry * 1.04, 2)
    target2 = round(entry * 1.08, 2)
    target3 = round(entry * 1.12, 2)

    reasons_text = " - ".join(reasons[:5])

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
        f"💧 السيولة: {int(volume):,}\n"
        f"📍 قمة اليوم: {round(day_high, 2)}\n"
        f"📍 قاع اليوم: {round(day_low, 2)}\n"
        f"📍 الافتتاح: {round(open_price, 2)}\n\n"
        f"✅ الأسباب: {reasons_text}"
    )

    return message

def update_symbol_state(symbol, q):
    symbol_state[symbol] = {
        "last_seen_high": q.get("day_high"),
        "last_seen_price": q.get("price"),
        "last_seen_volume": q.get("volume"),
        "updated_at": time.time(),
    }

# ===== BOT =====
def market_bot():
    print("🔥 BEAST BOT STARTED", flush=True)

    if BOT_TOKEN and CHAT_ID:
        send_message("🔥 البوت الوحش شغال")

    while True:
        try:
            print("📊 scanning beast mode...", flush=True)

            for symbol in WATCHLIST:
                q = get_quote(symbol)

                if not q:
                    time.sleep(1)
                    continue

                signal = build_signal(symbol, q)

                if signal:
                    last_time = last_alert.get(symbol, 0)
                    now = time.time()

                    if now - last_time > ALERT_COOLDOWN:
                        send_message(signal)
                        last_alert[symbol] = now
                        print(f"sent: {symbol}", flush=True)

                update_symbol_state(symbol, q)
                time.sleep(1)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            print(f"market_bot error: {e}", flush=True)
            time.sleep(10)

# ===== WEBHOOK =====
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    try:
        data = request.get_json(force=True)
        message = data.get("message", {})

        user = message.get("from")
        if not user:
            return "ok", 200

        user_id = str(user.get("id"))
        if user_id != ALLOWED_USER_ID:
            print(f"🚫 BLOCKED: {user_id}", flush=True)
            return "ok", 200

        text = message.get("text")
        chat_id = message.get("chat", {}).get("id")

        if text and chat_id:
            handle_command(text, str(chat_id))

        return "ok", 200

    except Exception as e:
        print(f"telegram_webhook error: {e}", flush=True)
        return "ok", 200

@app.route("/", methods=["GET"])
def home():
    return "OK", 200

# ===== RUN =====
if __name__ == "__main__":
    print("🔥 STARTING BEAST BOT...", flush=True)
    print("BOT_TOKEN:", bool(BOT_TOKEN), flush=True)
    print("CHAT_ID:", bool(CHAT_ID), flush=True)
    print("FINNHUB:", bool(FINNHUB_API_KEY), flush=True)

    threading.Thread(target=market_bot, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
