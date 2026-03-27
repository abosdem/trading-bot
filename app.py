import os
import time
import threading
import requests
from flask import Flask, request

app = Flask(__name__)

# ===== ENV =====
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("CHAT_ID") or "").strip()
TWELVEDATA_API_KEY = (os.getenv("TWELVEDATA_API_KEY") or "").strip()
ALLOWED_USER_ID = (os.getenv("ALLOWED_USER_ID") or "912977673").strip()

# ===== WATCHLIST =====
WATCHLIST = [
    "VEEE",
    "ATPC",
    "STI",
    "SND",
    "VSA",
]

# ===== SETTINGS =====
ALERT_COOLDOWN = 60 * 60
SCAN_INTERVAL = 180
PER_SYMBOL_DELAY = 4.0
CACHE_TTL = 75
API_BACKOFF_SECONDS = 15 * 60

TIME_SERIES_INTERVAL = "1min"
TIME_SERIES_OUTPUTSIZE = 15

MIN_PRICE = 0.50
MAX_PRICE = 20.0

# خففناها عشان ما يفوت الحركة
MIN_CHANGE_PCT = 1.0
MIN_SESSION_VOLUME = 40000
MIN_LAST_CANDLE_VOLUME = 2500

PRESSURE_NEAR_HIGH_BUFFER = 0.985
BREAKOUT_NEAR_HIGH_BUFFER = 0.996

PRESSURE_RECOVERY_MIN = 0.75
BREAKOUT_RECOVERY_MIN = 0.84

MIN_RVOL_PRESSURE = 0.90
MIN_RVOL_BREAKOUT = 1.15
MIN_RVOL_LOW_FLOAT = 0.60

MAX_PULLBACK_FROM_HIGH = 0.08

DEBUG_MODE = True

# ===== STATE =====
last_alert = {}
symbol_cache = {}
provider_backoff_until = 0

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
})

# ===== HELPERS =====
def log(msg):
    print(msg, flush=True)

def safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default

def now_ts():
    return time.time()

def provider_in_backoff():
    return now_ts() < provider_backoff_until

def set_provider_backoff(seconds, reason="provider_backoff"):
    global provider_backoff_until
    provider_backoff_until = max(provider_backoff_until, now_ts() + seconds)
    log(f"⏸️ provider backoff {seconds}s | reason={reason}")

def calc_ema(values, period):
    if not values:
        return 0.0

    if len(values) < period:
        return sum(values) / len(values)

    multiplier = 2 / (period + 1)
    ema = sum(values[:period]) / period

    for value in values[period:]:
        ema = ((value - ema) * multiplier) + ema

    return ema

def calc_vwap(rows):
    total_pv = 0.0
    total_v = 0.0

    for row in rows:
        h = row["high"]
        l = row["low"]
        c = row["close"]
        v = row["volume"]

        typical_price = (h + l + c) / 3.0
        total_pv += typical_price * v
        total_v += v

    if total_v <= 0:
        return 0.0

    return total_pv / total_v

# ===== TELEGRAM =====
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
            f"📊 المصدر: Twelve Data",
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

# ===== DATA =====
def parse_time_series_rows(values):
    rows = []

    for item in values:
        o = safe_float(item.get("open"))
        h = safe_float(item.get("high"))
        l = safe_float(item.get("low"))
        c = safe_float(item.get("close"))
        v = safe_float(item.get("volume"), 0.0)
        dt = item.get("datetime")

        if None in (o, h, l, c) or dt is None:
            continue

        rows.append({
            "datetime": dt,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v
        })

    return rows

def get_time_series(symbol):
    global symbol_cache

    if not TWELVEDATA_API_KEY:
        log("Missing TWELVEDATA_API_KEY")
        return None

    if provider_in_backoff():
        log(f"{symbol} skipped: provider_backoff")
        return None

    cached = symbol_cache.get(symbol)
    current = now_ts()

    if cached and (current - cached["ts"] < CACHE_TTL):
        return cached["rows"]

    try:
        response = session.get(
            "https://api.twelvedata.com/time_series",
            params={
                "symbol": symbol,
                "interval": TIME_SERIES_INTERVAL,
                "outputsize": TIME_SERIES_OUTPUTSIZE,
                "order": "ASC",
                "timezone": "Exchange",
                "apikey": TWELVEDATA_API_KEY
            },
            timeout=20
        )

        if response.status_code == 429:
            set_provider_backoff(API_BACKOFF_SECONDS, "http_429")
            return None

        if response.status_code != 200:
            log(f"Twelve Data status error {symbol}: {response.status_code}")
            set_provider_backoff(180, f"http_{response.status_code}")
            return None

        data = response.json()

        if isinstance(data, dict) and data.get("status") == "error":
            msg = str(data.get("message") or "").lower()
            log(f"Twelve Data api error {symbol}: {msg}")

            if "limit" in msg or "credit" in msg or "frequency" in msg or "api" in msg:
                set_provider_backoff(API_BACKOFF_SECONDS, "api_limit")
            else:
                set_provider_backoff(180, "api_error")
            return None

        values = data.get("values")
        if not values or not isinstance(values, list):
            return None

        rows = parse_time_series_rows(values)
        if len(rows) < 12:
            return None

        symbol_cache[symbol] = {
            "ts": current,
            "rows": rows
        }

        return rows

    except Exception as e:
        log(f"Twelve Data request error {symbol}: {e}")
        set_provider_backoff(180, "request_exception")
        return None

def get_intraday_metrics(symbol):
    rows = get_time_series(symbol)
    if not rows:
        return None

    closes = [r["close"] for r in rows]
    highs = [r["high"] for r in rows]
    lows = [r["low"] for r in rows]
    opens = [r["open"] for r in rows]
    volumes = [r["volume"] for r in rows]

    price = closes[-1]
    open_price = opens[0]
    day_high = max(highs)
    day_low = min(lows)
    recent_low = min(lows[-8:]) if len(lows) >= 8 else min(lows)

    session_volume = sum(volumes)
    last_candle_volume = volumes[-1]
    avg_last_10_volume = sum(volumes[-10:]) / min(10, len(volumes))

    ema9 = calc_ema(closes, 9)
    ema20 = calc_ema(closes, 20)
    vwap = calc_vwap(rows)

    # التعديل المهم: نحسب التغير من القاع القريب
    change_pct = ((price - recent_low) / recent_low) * 100 if recent_low > 0 else 0.0

    rvol = (last_candle_volume / avg_last_10_volume) if avg_last_10_volume > 0 else 0.0
    prev_high = max(highs[:-1]) if len(highs) > 1 else day_high

    return {
        "price": price,
        "change_pct": change_pct,
        "day_high": day_high,
        "day_low": day_low,
        "recent_low": recent_low,
        "open_price": open_price,
        "session_volume": session_volume,
        "last_candle_volume": last_candle_volume,
        "avg_last_10_volume": avg_last_10_volume,
        "rvol": rvol,
        "vwap": vwap,
        "ema9": ema9,
        "ema20": ema20,
        "prev_high": prev_high
    }

# ===== SIGNAL ENGINE =====
def build_signal(symbol, m):
    price = m["price"]
    change_pct = m["change_pct"]
    day_high = m["day_high"]
    day_low = m["day_low"]
    recent_low = m["recent_low"]
    open_price = m["open_price"]
    session_volume = m["session_volume"]
    last_candle_volume = m["last_candle_volume"]
    rvol = m["rvol"]
    vwap = m["vwap"]
    ema9 = m["ema9"]
    ema20 = m["ema20"]
    prev_high = m["prev_high"]

    if DEBUG_MODE:
        log(
            f"{symbol} metrics | "
            f"price={price:.2f} change={change_pct:.2f}% recent_low={recent_low:.2f} "
            f"session_vol={int(session_volume)} last_vol={int(last_candle_volume)} "
            f"rvol={rvol:.2f} day_high={day_high:.2f} vwap={vwap:.2f} "
            f"ema9={ema9:.2f} ema20={ema20:.2f}"
        )

    if price < MIN_PRICE or price > MAX_PRICE:
        return None, "price_outside_range"

    if change_pct < MIN_CHANGE_PCT:
        return None, "change_too_low"

    if last_candle_volume < MIN_LAST_CANDLE_VOLUME:
        return None, "low_last_candle_volume"

    day_range = day_high - day_low
    if day_range <= 0:
        return None, "invalid_day_range"

    recovery_ratio = (price - day_low) / day_range
    pullback_from_high = (day_high - price) / day_high if day_high > 0 else 1.0

    above_vwap = price >= vwap
    above_ema9 = price >= ema9
    above_ema20 = price >= ema20

    pressure_near_high = price >= day_high * PRESSURE_NEAR_HIGH_BUFFER
    breakout_near_high = price >= day_high * BREAKOUT_NEAR_HIGH_BUFFER

    low_liquidity = session_volume < MIN_SESSION_VOLUME

    if recovery_ratio < PRESSURE_RECOVERY_MIN:
        return None, "weak_recovery"

    if pullback_from_high > MAX_PULLBACK_FROM_HIGH:
        return None, "too_far_from_high"

    breakout_confirmed = (
        price >= prev_high
        and breakout_near_high
        and above_vwap
        and above_ema9
        and above_ema20
        and recovery_ratio >= BREAKOUT_RECOVERY_MIN
        and rvol >= MIN_RVOL_BREAKOUT
        and not low_liquidity
    )

    pressure_setup = (
        not breakout_confirmed
        and pressure_near_high
        and above_vwap
        and above_ema9
        and recovery_ratio >= 0.80
        and rvol >= MIN_RVOL_PRESSURE
    )

    low_float_momentum = (
        low_liquidity
        and change_pct >= 5.0
        and rvol >= MIN_RVOL_LOW_FLOAT
        and above_vwap
        and recovery_ratio >= 0.80
    )

    if not breakout_confirmed and not pressure_setup and not low_float_momentum:
        if low_liquidity:
            return None, "low_liquidity_no_momentum"
        return None, "no_setup"

    score = 0
    reasons = []

    if change_pct >= 1:
        score += 1
        reasons.append("زخم")

    if change_pct >= 3:
        score += 1
        reasons.append("زخم قوي")

    if change_pct >= 6:
        score += 1
        reasons.append("اندفاع")

    if session_volume >= MIN_SESSION_VOLUME:
        score += 1
        reasons.append("سيولة مقبولة")

    if session_volume >= 300000:
        score += 1
        reasons.append("سيولة قوية")

    if recovery_ratio >= 0.90:
        score += 1
        reasons.append("سيطرة مشترين")

    if above_vwap:
        score += 1
        reasons.append("فوق VWAP")

    if above_ema9:
        score += 1
        reasons.append("فوق EMA9")

    if above_ema20:
        score += 1
        reasons.append("فوق EMA20")

    if rvol >= 1.00:
        score += 1
        reasons.append("فوليوم لحظي جيد")

    if rvol >= 1.50:
        score += 1
        reasons.append("فوليوم لحظي قوي")

    if breakout_confirmed:
        score += 2
        reasons.append("اختراق مؤكد")
        signal_type = "اختراق مؤكد"
        min_score_required = 6

    elif low_float_momentum:
        score += 2
        reasons.append("سهم خفيف متحرك")
        signal_type = "مضاربة قوية (سهم خفيف)"
        min_score_required = 5

    else:
        score += 1
        reasons.append("ضغط قبل الاختراق")
        signal_type = "ضغط قوي قبل الاختراق"
        min_score_required = 5

    if score < min_score_required:
        return None, f"score_too_low_{score}"

    entry = round(price, 2)

    stop_candidates = [v for v in [vwap, ema9, ema20, entry * 0.97] if isinstance(v, (int, float)) and v > 0]
    stop = round(min(stop_candidates), 2) if stop_candidates else round(entry * 0.97, 2)

    if stop <= 0 or stop >= entry:
        stop = round(entry * 0.97, 2)

    target1 = round(entry * 1.04, 2)
    target2 = round(entry * 1.08, 2)
    target3 = round(entry * 1.12, 2)

    reasons_text = " - ".join(reasons[:6])

    message = (
        f"🚨 {signal_type}\n\n"
        f"📊 السهم: {symbol}\n"
        f"⭐ التقييم: {score}/13\n\n"
        f"💰 الدخول: {entry}\n"
        f"🛑 وقف الخسارة: {stop}\n\n"
        f"🎯 الهدف 1: {target1}\n"
        f"🎯 الهدف 2: {target2}\n"
        f"🎯 الهدف 3: {target3}\n\n"
        f"⚡ التغير: {round(change_pct, 2)}%\n"
        f"💧 سيولة الجلسة: {int(session_volume):,}\n"
        f"🕯️ فوليوم آخر دقيقة: {int(last_candle_volume):,}\n"
        f"📈 RVOL: {round(rvol, 2)}\n"
        f"📍 قمة الجلسة: {round(day_high, 2)}\n"
        f"📍 قاع الجلسة: {round(day_low, 2)}\n"
        f"📍 القاع القريب: {round(recent_low, 2)}\n"
        f"📍 الافتتاح: {round(open_price, 2)}\n"
        f"📈 VWAP: {round(vwap, 4)}\n"
        f"📉 EMA9: {round(ema9, 4)}\n"
        f"📉 EMA20: {round(ema20, 4)}\n\n"
        f"✅ الأسباب: {reasons_text}"
    )

    return message, "ok"

# ===== BOT =====
def should_send_symbol(symbol):
    current = now_ts()
    last_ts = last_alert.get(symbol, 0)
    return (current - last_ts) > ALERT_COOLDOWN

def market_bot():
    log("🔥 BEAST BOT STARTED")

    if BOT_TOKEN and CHAT_ID:
        send_message("🔥 البوت الخاص شغال")

    while True:
        try:
            if provider_in_backoff():
                remain = int(provider_backoff_until - now_ts())
                log(f"⏸️ paused {remain}s لحماية المفتاح")
                time.sleep(max(15, remain))
                continue

            log("📊 scanning beast mode...")

            for symbol in WATCHLIST:
                try:
                    metrics = get_intraday_metrics(symbol)

                    if not metrics:
                        if DEBUG_MODE:
                            log(f"{symbol} rejected: no_intraday_metrics")
                        time.sleep(PER_SYMBOL_DELAY)
                        continue

                    signal, reason = build_signal(symbol, metrics)

                    if signal:
                        if should_send_symbol(symbol):
                            sent = send_message(signal)
                            if sent:
                                last_alert[symbol] = now_ts()
                                log(f"sent: {symbol}")
                        else:
                            if DEBUG_MODE:
                                remain = int((ALERT_COOLDOWN - (now_ts() - last_alert.get(symbol, 0))) / 60)
                                log(f"{symbol} rejected: cooldown_{remain}m")
                    else:
                        if DEBUG_MODE:
                            log(f"{symbol} rejected: {reason}")

                    time.sleep(PER_SYMBOL_DELAY)

                except Exception as symbol_error:
                    log(f"symbol loop error {symbol}: {symbol_error}")
                    time.sleep(5)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            log(f"market_bot error: {e}")
            time.sleep(15)

# ===== WEBHOOK =====
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

# ===== RUN =====
if __name__ == "__main__":
    log("🔥 STARTING PRIVATE BOT...")
    log(f"BOT_TOKEN loaded: {bool(BOT_TOKEN)}")
    log(f"CHAT_ID loaded: {bool(CHAT_ID)}")
    log(f"TWELVEDATA_API_KEY loaded: {bool(TWELVEDATA_API_KEY)}")
    log(f"ALLOWED_USER_ID loaded: {bool(ALLOWED_USER_ID)}")

    threading.Thread(target=market_bot, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
