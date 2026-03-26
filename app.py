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
ALLOWED_USER_ID = (os.getenv("ALLOWED_USER_ID") or "912977673").strip()

# ===== WATCHLIST =====
WATCHLIST = [
    "VEEE", "SOWG", "STI", "ATPC", "SMSI", "LGVN", "ACXP",
    "AGRZ", "LASE", "DDD", "ALTO", "MOBX", "IOVA", "PRSO",
    "EDSA", "YYAI", "JEM", "DXST", "ASNS", "SMWB", "TPET",
    "BSM", "SND", "BOF", "SOUN", "CPIX", "NIO", "VSA",
    "MYO", "MNDR", "FIEE"
]

# ===== SETTINGS =====
ALERT_COOLDOWN = 30 * 60
SCAN_INTERVAL = 45
PER_SYMBOL_DELAY = 1.10

MIN_PRICE = 0.50
MAX_PRICE = 20.0

MIN_CHANGE = 3.0
MAX_CHANGE = 80.0

MIN_SESSION_VOLUME = 300000
STRONG_SESSION_VOLUME = 1000000
MIN_LAST_CANDLE_VOLUME = 15000

NEAR_HIGH_BUFFER = 0.9965
NEW_HIGH_BUFFER = 1.0010

PRESSURE_RECOVERY_MIN = 0.82
PRESSURE_DRIVE_MIN = 0.02

BREAKOUT_RECOVERY_MIN = 0.88
BREAKOUT_DRIVE_MIN = 0.03

MAX_PULLBACK_FROM_HIGH = 0.035
DEBUG_MODE = True

# ===== RUNTIME STATE =====
last_alert = {}
symbol_state = {}

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
})

# ===== HELPERS =====
def log(msg):
    print(msg, flush=True)

def calc_ema(values, period):
    if len(values) < period:
        return values[-1]

    multiplier = 2 / (period + 1)
    ema = sum(values[:period]) / period

    for value in values[period:]:
        ema = ((value - ema) * multiplier) + ema

    return ema

# ===== TELEGRAM =====
def send_message(text, chat_id=None):
    target_chat_id = str(chat_id or CHAT_ID).strip()

    if not BOT_TOKEN or not target_chat_id:
        log("Missing BOT_TOKEN or CHAT_ID")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        response = session.post(
            url,
            data={"chat_id": target_chat_id, "text": text},
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
            "🚀 البوت الوحش النهائي جاهز\n\n"
            "/status - حالة البوت\n"
            "/watchlist - قائمة الأسهم\n"
            "/test - اختبار\n"
            "/last - آخر الأسهم المرسلة",
            chat_id
        )

    elif cmd == "/status":
        send_message(
            "✅ البوت يعمل\n"
            f"📡 عدد الأسهم: {len(WATCHLIST)}\n"
            f"⏱️ الفحص كل: {SCAN_INTERVAL} ثانية\n"
            f"🧊 التبريد: {ALERT_COOLDOWN // 60} دقيقة",
            chat_id
        )

    elif cmd == "/watchlist":
        send_message("📊 القائمة:\n" + "\n".join(WATCHLIST), chat_id)

    elif cmd == "/test":
        send_message("🔥 الاختبار ناجح", chat_id)

    elif cmd == "/last":
        if not last_alert:
            send_message("📭 لا يوجد تنبيهات مرسلة بعد", chat_id)
        else:
            lines = []
            now = time.time()
            for symbol, ts in sorted(last_alert.items(), key=lambda x: x[1], reverse=True)[:10]:
                minutes = int((now - ts) / 60)
                lines.append(f"{symbol} - قبل {minutes} دقيقة")
            send_message("🕘 آخر التنبيهات:\n" + "\n".join(lines), chat_id)

    else:
        send_message("📩 الأمر غير معروف", chat_id)

# ===== FINNHUB =====
def finnhub_get(path, params):
    if not FINNHUB_API_KEY:
        log("Missing FINNHUB_API_KEY")
        return None

    base = f"https://finnhub.io/api/v1/{path}"
    payload = dict(params)
    payload["token"] = FINNHUB_API_KEY

    try:
        response = session.get(base, params=payload, timeout=20)

        if response.status_code != 200:
            log(f"Finnhub {path} status error: {response.status_code}")
            return None

        return response.json()

    except Exception as e:
        log(f"Finnhub {path} error: {e}")
        return None

def get_quote(symbol):
    data = finnhub_get("quote", {"symbol": symbol})
    if not data:
        return None

    price = data.get("c")
    change = data.get("dp")
    day_high = data.get("h")
    day_low = data.get("l")
    prev_close = data.get("pc")
    open_price = data.get("o")

    if price in (None, 0) or change is None or prev_close in (None, 0):
        return None

    return {
        "symbol": symbol,
        "price": float(price),
        "change": float(change),
        "day_high": float(day_high) if day_high not in (None, 0) else None,
        "day_low": float(day_low) if day_low not in (None, 0) else None,
        "prev_close": float(prev_close),
        "open_price": float(open_price) if open_price not in (None, 0) else None,
    }

def get_intraday_metrics(symbol):
    now_ts = int(time.time())
    start_ts = now_ts - (60 * 60 * 12)

    data = finnhub_get(
        "stock/candle",
        {
            "symbol": symbol,
            "resolution": "1",
            "from": start_ts,
            "to": now_ts
        }
    )

    if not data or data.get("s") != "ok":
        return None

    closes = data.get("c") or []
    highs = data.get("h") or []
    lows = data.get("l") or []
    volumes = data.get("v") or []
    timestamps = data.get("t") or []

    if not closes or not volumes or len(closes) < 10:
        return None

    valid = []
    for i in range(len(closes)):
        c = closes[i]
        h = highs[i] if i < len(highs) else c
        l = lows[i] if i < len(lows) else c
        v = volumes[i] if i < len(volumes) else 0
        t = timestamps[i] if i < len(timestamps) else 0

        if c is None or h is None or l is None or v is None:
            continue

        valid.append((int(t), float(h), float(l), float(c), float(v)))

    if len(valid) < 10:
        return None

    closes_only = [x[3] for x in valid]
    volumes_only = [x[4] for x in valid]

    typical_price_volume_sum = 0.0
    volume_sum = 0.0

    for _, h, l, c, v in valid:
        tp = (h + l + c) / 3.0
        typical_price_volume_sum += tp * v
        volume_sum += v

    if volume_sum <= 0:
        return None

    vwap = typical_price_volume_sum / volume_sum
    ema9 = calc_ema(closes_only, 9)
    last_candle_volume = volumes_only[-1]
    prev_candle_volume = volumes_only[-2] if len(volumes_only) >= 2 else 0.0
    avg_last_10_volume = sum(volumes_only[-10:]) / min(10, len(volumes_only))
    session_volume = volume_sum

    return {
        "vwap": float(vwap),
        "ema9": float(ema9),
        "session_volume": float(session_volume),
        "last_candle_volume": float(last_candle_volume),
        "prev_candle_volume": float(prev_candle_volume),
        "avg_last_10_volume": float(avg_last_10_volume),
        "latest_close": float(closes_only[-1]),
    }

# ===== FILTERS =====
def quick_prefilter(q):
    price = q["price"]
    change = q["change"]
    day_high = q["day_high"]
    day_low = q["day_low"]
    prev_close = q["prev_close"]
    open_price = q["open_price"]

    if price < MIN_PRICE or price > MAX_PRICE:
        return False, "price_outside_range"

    if change < MIN_CHANGE or change > MAX_CHANGE:
        return False, "change_outside_range"

    if not day_high or not day_low or not open_price:
        return False, "missing_day_data"

    if price <= prev_close:
        return False, "below_prev_close"

    if price <= open_price:
        return False, "below_open"

    return True, "ok"

# ===== SIGNAL ENGINE =====
def build_signal(symbol, q, m):
    price = q["price"]
    change = q["change"]
    day_high = q["day_high"]
    day_low = q["day_low"]
    open_price = q["open_price"]

    vwap = m["vwap"]
    ema9 = m["ema9"]
    session_volume = m["session_volume"]
    last_candle_volume = m["last_candle_volume"]
    avg_last_10_volume = m["avg_last_10_volume"]

    if session_volume < MIN_SESSION_VOLUME:
        return None, "low_session_volume"

    if last_candle_volume < MIN_LAST_CANDLE_VOLUME:
        return None, "low_last_candle_volume"

    day_range = day_high - day_low
    if day_range <= 0:
        return None, "invalid_day_range"

    recovery_ratio = (price - day_low) / day_range
    open_drive = (price - open_price) / open_price
    near_high = price >= day_high * NEAR_HIGH_BUFFER
    above_vwap = price >= vwap
    above_ema9 = price >= ema9
    pullback_from_high = (day_high - price) / day_high if day_high > 0 else 1.0
    candle_volume_boost = (last_candle_volume / avg_last_10_volume) if avg_last_10_volume > 0 else 0.0

    if recovery_ratio < PRESSURE_RECOVERY_MIN:
        return None, "weak_recovery"

    if open_drive < PRESSURE_DRIVE_MIN:
        return None, "weak_open_drive"

    if pullback_from_high > MAX_PULLBACK_FROM_HIGH:
        return None, "too_far_from_high"

    state = symbol_state.get(symbol, {})
    prev_seen_high = state.get("last_seen_high")
    prev_seen_price = state.get("last_seen_price")
    prev_seen_volume = state.get("last_seen_session_volume")

    breakout_confirmed = (
        near_high
        and above_vwap
        and above_ema9
        and recovery_ratio >= BREAKOUT_RECOVERY_MIN
        and open_drive >= BREAKOUT_DRIVE_MIN
        and session_volume >= STRONG_SESSION_VOLUME
        and candle_volume_boost >= 1.2
        and (
            prev_seen_high is None
            or day_high > prev_seen_high * NEW_HIGH_BUFFER
            or price >= prev_seen_high * NEW_HIGH_BUFFER
        )
    )

    pressure_setup = (
        not breakout_confirmed
        and near_high
        and above_vwap
        and recovery_ratio >= 0.86
        and open_drive >= 0.025
        and session_volume >= MIN_SESSION_VOLUME
    )

    if not breakout_confirmed and not pressure_setup:
        return None, "no_setup"

    if prev_seen_price is not None and prev_seen_volume is not None:
        price_growth = (price - prev_seen_price) / prev_seen_price if prev_seen_price > 0 else 0.0
        volume_growth = session_volume - prev_seen_volume

        if pressure_setup and price_growth < -0.004:
            return None, "pressure_fading"

        if breakout_confirmed and volume_growth < 0:
            return None, "breakout_volume_fading"

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

    if session_volume >= MIN_SESSION_VOLUME:
        score += 1
        reasons.append("سيولة مؤكدة")

    if session_volume >= STRONG_SESSION_VOLUME:
        score += 1
        reasons.append("سيولة قوية")

    if recovery_ratio >= 0.90:
        score += 1
        reasons.append("سيطرة مشترين")

    if open_drive >= 0.04:
        score += 1
        reasons.append("اندفاع من الافتتاح")

    if above_vwap:
        score += 1
        reasons.append("فوق VWAP")

    if above_ema9:
        score += 1
        reasons.append("فوق EMA9")

    if candle_volume_boost >= 1.5:
        score += 1
        reasons.append("فوليوم لحظي قوي")

    if breakout_confirmed:
        score += 2
        reasons.append("اختراق مؤكد")
        signal_type = "اختراق مؤكد"
        min_score_required = 8
    else:
        score += 1
        reasons.append("ضغط قبل الاختراق")
        signal_type = "ضغط قوي قبل الاختراق"
        min_score_required = 7

    if score < min_score_required:
        return None, f"score_too_low_{score}"

    entry = round(price, 2)
    stop = round(max(vwap, entry * 0.96), 2)
    if stop >= entry:
        stop = round(entry * 0.97, 2)

    target1 = round(entry * 1.04, 2)
    target2 = round(entry * 1.08, 2)
    target3 = round(entry * 1.12, 2)

    reasons_text = " - ".join(reasons[:6])

    message = (
        f"🚨 {signal_type}\n\n"
        f"📊 السهم: {symbol}\n"
        f"⭐ التقييم: {score}/12\n\n"
        f"💰 الدخول: {entry}\n"
        f"🛑 وقف الخسارة: {stop}\n\n"
        f"🎯 الهدف 1: {target1}\n"
        f"🎯 الهدف 2: {target2}\n"
        f"🎯 الهدف 3: {target3}\n\n"
        f"⚡ التغير: {round(change, 2)}%\n"
        f"💧 سيولة الجلسة: {int(session_volume):,}\n"
        f"🕯️ فوليوم آخر دقيقة: {int(last_candle_volume):,}\n"
        f"📍 قمة اليوم: {round(day_high, 2)}\n"
        f"📍 قاع اليوم: {round(day_low, 2)}\n"
        f"📍 الافتتاح: {round(open_price, 2)}\n"
        f"📈 VWAP: {round(vwap, 4)}\n"
        f"📉 EMA9: {round(ema9, 4)}\n\n"
        f"✅ الأسباب: {reasons_text}"
    )

    return message, "ok"

def update_symbol_state(symbol, q, m=None):
    state = {
        "last_seen_high": q.get("day_high"),
        "last_seen_price": q.get("price"),
        "updated_at": time.time(),
    }

    if m:
        state["last_seen_session_volume"] = m.get("session_volume")
        state["last_seen_vwap"] = m.get("vwap")
        state["last_seen_ema9"] = m.get("ema9")

    symbol_state[symbol] = state

# ===== BOT =====
def market_bot():
    log("🔥 BEAST BOT STARTED")

    if BOT_TOKEN and CHAT_ID:
        send_message("🔥 البوت الوحش النهائي شغال")

    while True:
        try:
            log("📊 scanning beast mode...")

            for symbol in WATCHLIST:
                q = get_quote(symbol)

                if not q:
                    log(f"{symbol} rejected: no_quote")
                    time.sleep(PER_SYMBOL_DELAY)
                    continue

                ok, quick_reason = quick_prefilter(q)
                if not ok:
                    if DEBUG_MODE:
                        log(f"{symbol} rejected: {quick_reason}")
                    update_symbol_state(symbol, q)
                    time.sleep(PER_SYMBOL_DELAY)
                    continue

                m = get_intraday_metrics(symbol)
                if not m:
                    if DEBUG_MODE:
                        log(f"{symbol} rejected: no_intraday_metrics")
                    update_symbol_state(symbol, q)
                    time.sleep(PER_SYMBOL_DELAY)
                    continue

                signal, reason = build_signal(symbol, q, m)

                if signal:
                    last_time = last_alert.get(symbol, 0)
                    now_ts = time.time()

                    if now_ts - last_time > ALERT_COOLDOWN:
                        sent = send_message(signal)
                        if sent:
                            last_alert[symbol] = now_ts
                            log(f"sent: {symbol}")
                    else:
                        if DEBUG_MODE:
                            remain = int((ALERT_COOLDOWN - (now_ts - last_time)) / 60)
                            log(f"{symbol} rejected: cooldown_{remain}m")
                else:
                    if DEBUG_MODE:
                        log(f"{symbol} rejected: {reason}")

                update_symbol_state(symbol, q, m)
                time.sleep(PER_SYMBOL_DELAY)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            log(f"market_bot error: {e}")
            time.sleep(10)

# ===== WEBHOOK =====
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    try:
        data = request.get_json(force=True) or {}
        message = data.get("message", {})
        user = message.get("from")

        if not user:
            return "ok", 200

        user_id = str(user.get("id"))
        if user_id != ALLOWED_USER_ID:
            log(f"🚫 BLOCKED: {user_id}")
            return "ok", 200

        text = message.get("text")
        chat_id = message.get("chat", {}).get("id")

        if text and chat_id:
            handle_command(text, str(chat_id))

        return "ok", 200

    except Exception as e:
        log(f"telegram_webhook error: {e}")
        return "ok", 200

@app.route("/", methods=["GET"])
def home():
    return "OK", 200

# ===== RUN =====
if __name__ == "__main__":
    log("🔥 STARTING BEAST BOT...")
    log(f"BOT_TOKEN: {bool(BOT_TOKEN)}")
    log(f"CHAT_ID: {bool(CHAT_ID)}")
    log(f"FINNHUB: {bool(FINNHUB_API_KEY)}")
    log(f"ALLOWED_USER_ID: {bool(ALLOWED_USER_ID)}")

    threading.Thread(target=market_bot, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
