import os
import time
import threading
import requests
from flask import Flask, request

app = Flask(__name__)

# =========================
# ENV
# =========================
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("CHAT_ID") or "").strip()
FINNHUB_API_KEY = (os.getenv("FINNHUB_API_KEY") or "").strip()
ALLOWED_USER_ID = (os.getenv("ALLOWED_USER_ID") or "912977673").strip()

# =========================
# WATCHLIST
# =========================
WATCHLIST = [
    "VEEE", "SOWG", "STI", "ATPC", "SMSI", "LGVN", "ACXP",
    "AGRZ", "LASE", "DDD", "ALTO", "MOBX", "IOVA", "PRSO",
    "EDSA", "YYAI", "JEM", "DXST", "ASNS", "SMWB", "TPET",
    "BSM", "SND", "BOF", "SOUN", "CPIX", "NIO", "VSA",
    "MYO", "MNDR", "FIEE"
]

# =========================
# SETTINGS
# =========================
ALERT_COOLDOWN = 45 * 60   # 45 دقيقة لكل سهم
SCAN_INTERVAL = 180        # كل 3 دقائق
PER_SYMBOL_DELAY = 1.5     # تخفيف الضغط على المفتاح

MIN_PRICE = 0.50
MAX_PRICE = 20.0

MIN_CHANGE_PCT = 1.5
MAX_CHANGE_PCT = 20.0

# قريب من القمة
PRESSURE_NEAR_HIGH_BUFFER = 0.985
# اختراق مؤكد
BREAKOUT_BUFFER = 1.0005

# =========================
# STATE
# =========================
last_alert = {}
last_signal_text = {}

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
})

# =========================
# HELPERS
# =========================
def log(msg):
    print(msg, flush=True)

def now_ts():
    return time.time()

def safe_float(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default

def should_send_symbol(symbol):
    current = now_ts()
    last_ts = last_alert.get(symbol, 0)
    return (current - last_ts) > ALERT_COOLDOWN

# =========================
# TELEGRAM
# =========================
def send_message(text, chat_id=None):
    target_chat_id = str(chat_id or CHAT_ID).strip()

    if not BOT_TOKEN or not target_chat_id:
        log("Missing BOT_TOKEN or CHAT_ID")
        return False

    try:
        response = session.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": target_chat_id,
                "text": text
            },
            timeout=20
        )
        log(f"Telegram send status: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        log(f"Telegram send error: {e}")
        return False

def handle_command(text, chat_id):
    cmd = (text or "").strip().lower()

    if cmd == "/start":
        send_message(
            "🚀 البوت الخاص جاهز\n\n"
            "/status - حالة البوت\n"
            "/test - اختبار\n"
            "/last - آخر التنبيهات\n"
            "/watchlist - الأسهم الحالية",
            chat_id
        )

    elif cmd == "/status":
        send_message(
            "✅ البوت يعمل\n"
            f"📡 عدد الأسهم: {len(WATCHLIST)}\n"
            f"⏱️ الفحص كل: {SCAN_INTERVAL} ثانية\n"
            f"🧊 التبريد: {ALERT_COOLDOWN // 60} دقيقة\n"
            f"📊 المصدر: Finnhub Quote",
            chat_id
        )

    elif cmd == "/test":
        send_message("🔥 الاختبار ناجح", chat_id)

    elif cmd == "/watchlist":
        send_message("📋 الأسهم:\n" + "\n".join(WATCHLIST), chat_id)

    elif cmd == "/last":
        if not last_alert:
            send_message("📭 لا توجد تنبيهات مرسلة بعد", chat_id)
        else:
            current = now_ts()
            lines = []
            for symbol, ts in sorted(last_alert.items(), key=lambda x: x[1], reverse=True)[:10]:
                mins = int((current - ts) / 60)
                lines.append(f"{symbol} - قبل {mins} دقيقة")
            send_message("🕘 آخر التنبيهات:\n" + "\n".join(lines), chat_id)

    else:
        send_message("📩 الأمر غير معروف", chat_id)

# =========================
# FINNHUB
# =========================
def get_quote(symbol):
    if not FINNHUB_API_KEY:
        log("Missing FINNHUB_API_KEY")
        return None

    try:
        response = session.get(
            "https://finnhub.io/api/v1/quote",
            params={
                "symbol": symbol,
                "token": FINNHUB_API_KEY
            },
            timeout=20
        )

        if response.status_code != 200:
            log(f"Finnhub status error {symbol}: {response.status_code}")
            return None

        data = response.json()

        price = safe_float(data.get("c"))
        change_pct = safe_float(data.get("dp"))
        day_high = safe_float(data.get("h"))
        day_low = safe_float(data.get("l"))
        prev_close = safe_float(data.get("pc"))
        open_price = safe_float(data.get("o"))

        if None in (price, change_pct, day_high, day_low, prev_close, open_price):
            return None

        return {
            "price": price,
            "change_pct": change_pct,
            "day_high": day_high,
            "day_low": day_low,
            "prev_close": prev_close,
            "open_price": open_price,
        }

    except Exception as e:
        log(f"Finnhub request error {symbol}: {e}")
        return None

# =========================
# SIGNAL ENGINE
# =========================
def build_signal(symbol, q):
    price = q["price"]
    change_pct = q["change_pct"]
    day_high = q["day_high"]
    day_low = q["day_low"]
    prev_close = q["prev_close"]
    open_price = q["open_price"]

    if price < MIN_PRICE or price > MAX_PRICE:
        return None, "price_outside_range"

    if change_pct < MIN_CHANGE_PCT or change_pct > MAX_CHANGE_PCT:
        return None, "change_outside_range"

    if day_high <= 0 or day_low <= 0 or open_price <= 0:
        return None, "invalid_levels"

    if price <= open_price:
        return None, "below_open"

    if price <= prev_close:
        return None, "below_prev_close"

    day_range = day_high - day_low
    if day_range <= 0:
        return None, "invalid_day_range"

    recovery_ratio = (price - day_low) / day_range
    if recovery_ratio < 0.78:
        return None, "weak_recovery"

    pullback_from_high = (day_high - price) / day_high if day_high > 0 else 1.0
    if pullback_from_high > 0.08:
        return None, "too_far_from_high"

    pressure_setup = (
        price >= day_high * PRESSURE_NEAR_HIGH_BUFFER
        and recovery_ratio >= 0.82
    )

    breakout_confirmed = (
        price >= day_high * BREAKOUT_BUFFER
        and recovery_ratio >= 0.88
    )

    if not pressure_setup and not breakout_confirmed:
        return None, "no_setup"

    score = 0
    reasons = []

    if change_pct >= 1.5:
        score += 1
        reasons.append("زخم")

    if change_pct >= 3:
        score += 1
        reasons.append("زخم قوي")

    if change_pct >= 5:
        score += 1
        reasons.append("اندفاع")

    if price > open_price:
        score += 1
        reasons.append("فوق الافتتاح")

    if price > prev_close:
        score += 1
        reasons.append("فوق إغلاق أمس")

    if recovery_ratio >= 0.85:
        score += 1
        reasons.append("تعافي قوي")

    if recovery_ratio >= 0.90:
        score += 1
        reasons.append("سيطرة مشترين")

    signal_type = None
    min_score_required = 0

    if breakout_confirmed:
        score += 2
        reasons.append("اختراق مؤكد")
        signal_type = "اختراق مؤكد"
        min_score_required = 6
    else:
        score += 1
        reasons.append("ضغط قبل الاختراق")
        signal_type = "ضغط قوي قبل الاختراق"
        min_score_required = 5

    if score < min_score_required:
        return None, f"score_too_low_{score}"

    entry = round(price, 4 if price < 1 else 2)
    stop = round(entry * 0.97, 4 if entry < 1 else 2)
    target1 = round(entry * 1.04, 4 if entry < 1 else 2)
    target2 = round(entry * 1.08, 4 if entry < 1 else 2)
    target3 = round(entry * 1.12, 4 if entry < 1 else 2)

    reasons_text = " - ".join(reasons[:6])

    message = (
        f"🚨 {signal_type}\n\n"
        f"📊 السهم: {symbol}\n"
        f"⭐ التقييم: {score}/9\n\n"
        f"💰 الدخول: {entry}\n"
        f"🛑 وقف الخسارة: {stop}\n\n"
        f"🎯 الهدف 1: {target1}\n"
        f"🎯 الهدف 2: {target2}\n"
        f"🎯 الهدف 3: {target3}\n\n"
        f"⚡ التغير: {round(change_pct, 2)}%\n"
        f"📍 قمة الجلسة: {round(day_high, 4 if day_high < 1 else 2)}\n"
        f"📍 قاع الجلسة: {round(day_low, 4 if day_low < 1 else 2)}\n"
        f"📍 الافتتاح: {round(open_price, 4 if open_price < 1 else 2)}\n\n"
        f"✅ الأسباب: {reasons_text}"
    )

    return message, "ok"

# =========================
# BOT LOOP
# =========================
def market_bot():
    log("🔥 FINNHUB BOT STARTED")

    if BOT_TOKEN and CHAT_ID:
        send_message("🔥 البوت الخاص شغال على Finnhub")

    while True:
        try:
            log("📊 scanning finnhub mode...")

            for symbol in WATCHLIST:
                try:
                    quote = get_quote(symbol)

                    if not quote:
                        log(f"{symbol} rejected: no_quote")
                        time.sleep(PER_SYMBOL_DELAY)
                        continue

                    signal, reason = build_signal(symbol, quote)

                    if signal:
                        if should_send_symbol(symbol):
                            sent = send_message(signal)
                            if sent:
                                last_alert[symbol] = now_ts()
                                last_signal_text[symbol] = signal
                                log(f"sent: {symbol}")
                        else:
                            remaining = int((ALERT_COOLDOWN - (now_ts() - last_alert.get(symbol, 0))) / 60)
                            log(f"{symbol} rejected: cooldown_{remaining}m")
                    else:
                        log(f"{symbol} rejected: {reason}")

                    time.sleep(PER_SYMBOL_DELAY)

                except Exception as symbol_error:
                    log(f"symbol loop error {symbol}: {symbol_error}")
                    time.sleep(5)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            log(f"market_bot error: {e}")
            time.sleep(15)

# =========================
# WEBHOOK
# =========================
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    try:
        data = request.get_json(force=True) or {}
        msg = data.get("message", {})
        user = msg.get("from")

        if not user:
            return "", 200

        user_id = str(user.get("id") or "")
        if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
            log(f"🚫 BLOCKED USER: {user_id}")
            return "", 200

        text = msg.get("text")
        chat_id = msg.get("chat", {}).get("id")

        if text and chat_id:
            handle_command(text, str(chat_id))

        return "ok", 200

    except Exception as e:
        log(f"telegram_webhook error: {e}")
        return "ok", 200

@app.route("/", methods=["GET"])
def home():
    return "OK", 200

# =========================
# RUN
# =========================
if __name__ == "__main__":
    log("🔥 STARTING PRIVATE FINNHUB BOT...")
    log(f"BOT_TOKEN loaded: {bool(BOT_TOKEN)}")
    log(f"CHAT_ID loaded: {bool(CHAT_ID)}")
    log(f"FINNHUB_API_KEY loaded: {bool(FINNHUB_API_KEY)}")
    log(f"ALLOWED_USER_ID loaded: {bool(ALLOWED_USER_ID)}")

    threading.Thread(target=market_bot, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
