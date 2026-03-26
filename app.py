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
    "VEEE","SOWG","STI","ATPC","SMSI","LGVN","ACXP","AGRZ","LASE","DDD",
    "ALTO","MOBX","IOVA","PRSO","EDSA","YYAI","JEM","DXST","ASNS","SMWB",
    "TPET","BSM","SND","BOF","SOUN","CPIX","NIO","VSA","MYO","MNDR","FIEE"
]

# ===== SETTINGS =====
ALERT_COOLDOWN = 30 * 60
SCAN_INTERVAL = 40
PER_SYMBOL_DELAY = 1.1

MIN_PRICE = 0.5
MAX_PRICE = 20.0

MIN_CHANGE = 1.5  # 🔥 مهم

MIN_SESSION_VOLUME = 300000
STRONG_SESSION_VOLUME = 1000000
MIN_LAST_CANDLE_VOLUME = 15000

NEAR_HIGH_BUFFER = 0.996
DEBUG = True

last_alert = {}
symbol_state = {}

session = requests.Session()

# ===== TELEGRAM =====
def send_message(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        session.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

# ===== API =====
def get_quote(symbol):
    try:
        r = session.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": symbol, "token": FINNHUB_API_KEY},
            timeout=10
        )
        d = r.json()

        if not d.get("c"):
            return None

        return {
            "price": d["c"],
            "change": d["dp"],
            "high": d["h"],
            "low": d["l"],
            "open": d["o"],
            "prev": d["pc"]
        }
    except:
        return None

def get_candles(symbol):
    try:
        now = int(time.time())
        r = session.get(
            "https://finnhub.io/api/v1/stock/candle",
            params={
                "symbol": symbol,
                "resolution": "1",
                "from": now - 3600 * 6,
                "to": now,
                "token": FINNHUB_API_KEY
            },
            timeout=10
        )
        d = r.json()

        if d.get("s") != "ok":
            return None

        closes = d["c"]
        highs = d["h"]
        lows = d["l"]
        volumes = d["v"]

        if len(closes) < 10:
            return None

        # VWAP
        total_pv = 0
        total_v = 0

        for i in range(len(closes)):
            tp = (highs[i] + lows[i] + closes[i]) / 3
            v = volumes[i]
            total_pv += tp * v
            total_v += v

        vwap = total_pv / total_v if total_v else 0

        ema9 = sum(closes[-9:]) / 9
        session_volume = sum(volumes)

        return {
            "vwap": vwap,
            "ema9": ema9,
            "volume": session_volume,
            "last_vol": volumes[-1]
        }

    except:
        return None

# ===== SIGNAL =====
def build_signal(symbol, q, m):

    price = q["price"]
    change = q["change"]

    if price < MIN_PRICE or price > MAX_PRICE:
        return None, "price"

    if change < MIN_CHANGE:
        return None, "change"

    if price <= q["prev"] or price <= q["open"]:
        return None, "weak"

    if m["volume"] < MIN_SESSION_VOLUME:
        return None, "volume"

    if m["last_vol"] < MIN_LAST_CANDLE_VOLUME:
        return None, "last_vol"

    day_range = q["high"] - q["low"]
    if day_range <= 0:
        return None, "range"

    recovery = (price - q["low"]) / day_range

    near_high = price >= q["high"] * NEAR_HIGH_BUFFER

    above_vwap = price >= m["vwap"]
    above_ema = price >= m["ema9"]

    if recovery < 0.8:
        return None, "recovery"

    if not near_high:
        return None, "not_near_high"

    if not above_vwap:
        return None, "below_vwap"

    score = 0
    reasons = []

    if change >= 3:
        score += 2
        reasons.append("زخم")

    if change >= 5:
        score += 1
        reasons.append("اندفاع")

    if m["volume"] >= STRONG_SESSION_VOLUME:
        score += 2
        reasons.append("سيولة قوية")

    if above_ema:
        score += 1
        reasons.append("فوق EMA")

    if recovery > 0.9:
        score += 1
        reasons.append("سيطرة")

    if m["last_vol"] > m["volume"] * 0.05:
        score += 1
        reasons.append("فوليوم لحظي")

    if score < 5:
        return None, "score"

    msg = (
        f"🚨 إشارة قوية\n\n"
        f"📊 {symbol}\n"
        f"⭐ {score}/10\n\n"
        f"💰 {round(price,2)}\n"
        f"🎯 {round(price*1.05,2)} / {round(price*1.1,2)}\n"
        f"🛑 {round(price*0.96,2)}\n\n"
        f"⚡ {round(change,2)}%\n"
        f"💧 {int(m['volume']):,}\n\n"
        f"✅ {' - '.join(reasons)}"
    )

    return msg, "ok"

# ===== BOT =====
def run_bot():
    print("🔥 BOT STARTED")

    while True:
        for s in WATCHLIST:

            q = get_quote(s)
            if not q:
                print(s, "no quote")
                time.sleep(PER_SYMBOL_DELAY)
                continue

            m = get_candles(s)
            if not m:
                print(s, "no candles")
                time.sleep(PER_SYMBOL_DELAY)
                continue

            signal, reason = build_signal(s, q, m)

            if signal:
                now = time.time()
                last = last_alert.get(s, 0)

                if now - last > ALERT_COOLDOWN:
                    send_message(signal)
                    last_alert[s] = now
                    print("sent:", s)
            else:
                if DEBUG:
                    print(s, "rejected:", reason)

            time.sleep(PER_SYMBOL_DELAY)

        time.sleep(SCAN_INTERVAL)

# ===== TELEGRAM WEBHOOK =====
@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.json
    msg = data.get("message", {})
    user = str(msg.get("from", {}).get("id"))

    if user != ALLOWED_USER_ID:
        return "ok"

    text = msg.get("text")

    if text == "/test":
        send_message("🔥 شغال")

    return "ok"

@app.route("/")
def home():
    return "OK"

# ===== RUN =====
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
