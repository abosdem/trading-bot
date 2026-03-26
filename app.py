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
MAX_CHANGE = 15.0

# لازم يكون فوق القمة بنسبة بسيطة لتأكيد الاختراق
BREAKOUT_BUFFER = 1.002   # 0.2%

# لو كان فقط قريب من القمة، ما نرسل إلا لو الاندفاع قوي
NEAR_HIGH_BUFFER = 0.998  # قريب جدًا من القمة

last_alert = {}

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
            "🚀 البوت المطور جاهز\n\n"
            "/status - حالة البوت\n"
            "/watchlist - قائمة الأسهم\n"
            "/test - اختبار",
            chat_id
        )

    elif cmd == "/status":
        send_message("✅ البوت يعمل بالفلترة المطورة", chat_id)

    elif cmd == "/watchlist":
        send_message("📊 القائمة:\n" + "\n".join(WATCHLIST), chat_id)

    elif cmd == "/test":
        send_message("🔥 تم الاختبار بنجاح", chat_id)

    else:
        send_message(f"📩 وصلني: {text}", chat_id)

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

# ===== فلترة مطورة =====
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

    # فوق إغلاق أمس
    if price <= prev_close:
        return None

    # فوق الافتتاح
    if price <= open_price:
        return None

    # ارتداد قوي من قاع اليوم
    recovery_ratio = (price - day_low) / day_range
    if recovery_ratio < 0.82:
        return None

    # قوة الاندفاع من الافتتاح
    open_drive = (price - open_price) / open_price
    if open_drive < 0.02:
        return None

    # اختراق فعلي أو تثبيت قوي قرب القمة
    real_breakout = price >= day_high * BREAKOUT_BUFFER
    near_high = price >= day_high * NEAR_HIGH_BUFFER

    if not real_breakout and not near_high:
        return None

    # إذا كان فقط قريب من القمة، لازم تكون القوة أعلى
    if near_high and not real_breakout:
        if change < 5:
            return None
        if open_drive < 0.035:
            return None
        if recovery_ratio < 0.90:
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
        reasons.append("ضغط تحت القمة")

    if recovery_ratio >= 0.90:
        score += 1
        reasons.append("سيطرة مشترين")

    if price > open_price:
        score += 1
        reasons.append("فوق الافتتاح")

    if open_drive >= 0.04:
        score += 1
        reasons.append("اندفاع من الافتتاح")

    # نبي إشارات أقل وأقوى
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

# ===== البوت =====
def market_bot():
    print("🔥 FILTERED BOT STARTED", flush=True)

    if BOT_TOKEN and CHAT_ID:
        send_message("🔥 البوت المطور شغال")

    while True:
        try:
            now = time.time()
            print("📊 scanning filtered...", flush=True)

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

# ===== Webhook =====
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

# ===== الصفحة الرئيسية =====
@app.route("/", methods=["GET", "POST"])
def home():
    return "OK", 200

# ===== التشغيل =====
if __name__ == "__main__":
    print("🔥 STARTING...", flush=True)
    print("BOT_TOKEN:", bool(BOT_TOKEN), flush=True)
    print("CHAT_ID:", bool(CHAT_ID), flush=True)
    print("FINNHUB:", bool(FINNHUB_API_KEY), flush=True)

    threading.Thread(target=market_bot, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
