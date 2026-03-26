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

# ===== 🔒 SECURITY =====
ALLOWED_USER_ID = "123456789"  # 🔥 حط هنا ID حقك

def is_allowed_user(user_id):
    return str(user_id) == ALLOWED_USER_ID

# ===== WATCHLIST =====
WATCHLIST = [
    "VEEE","SOWG","STI","ATPC","SMSI","LGVN","ACXP",
    "AGRZ","LASE","DDD","ALTO","MOBX","IOVA","PRSO",
    "EDSA","YYAI","JEM","DXST","ASNS","SMWB","TPET",
    "BSM","SND","BOF","SOUN","CPIX","NIO","VSA",
    "MYO","MNDR","FIEE"
]

# ===== SETTINGS =====
ALERT_COOLDOWN = 45 * 60
SCAN_INTERVAL = 90

MIN_PRICE = 0.50
MAX_PRICE = 20.0
MIN_CHANGE = 3.0
MAX_CHANGE = 15.0
MIN_VOLUME = 300000  # 🔥 فلتر السيولة

BREAKOUT_BUFFER = 1.002
NEAR_HIGH_BUFFER = 0.998

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
        session.post(
            url,
            data={"chat_id": target_chat_id, "text": text},
            timeout=15
        )
    except Exception as e:
        print(f"Telegram error: {e}", flush=True)

def handle_command(text, chat_id):
    cmd = (text or "").strip().lower()

    if cmd == "/start":
        send_message(
            "🚀 البوت جاهز\n\n"
            "/status\n/watchlist\n/test",
            chat_id
        )

    elif cmd == "/status":
        send_message("✅ البوت يعمل", chat_id)

    elif cmd == "/watchlist":
        send_message("📊 القائمة:\n" + "\n".join(WATCHLIST), chat_id)

    elif cmd == "/test":
        send_message("🔥 شغال", chat_id)

    else:
        send_message(f"📩 {text}", chat_id)

# ===== FINNHUB =====
def get_quote(symbol):
    if not FINNHUB_API_KEY:
        return None

    url = "https://finnhub.io/api/v1/quote"
    params = {"symbol": symbol, "token": FINNHUB_API_KEY}

    try:
        r = session.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return None

        d = r.json()

        price = d.get("c")
        change = d.get("dp")
        high = d.get("h")
        low = d.get("l")
        prev = d.get("pc")
        open_p = d.get("o")
        volume = d.get("v")

        if price in (None, 0) or change is None or prev in (None, 0):
            return None

        return {
            "price": float(price),
            "change": float(change),
            "day_high": float(high) if high else None,
            "day_low": float(low) if low else None,
            "prev_close": float(prev),
            "open_price": float(open_p) if open_p else None,
            "volume": float(volume) if volume else 0,
        }
    except:
        return None

# ===== SIGNAL =====
def build_signal(symbol, q):
    p = q["price"]
    c = q["change"]
    h = q["day_high"]
    l = q["day_low"]
    prev = q["prev_close"]
    o = q["open_price"]
    volume = q["volume"]

    # فلترة أساسية
    if p < MIN_PRICE or p > MAX_PRICE:
        return None
    if c < MIN_CHANGE or c > MAX_CHANGE:
        return None
    if volume < MIN_VOLUME:
        return None
    if not h or not l or not o:
        return None
    if p <= prev or p <= o:
        return None

    rng = h - l
    if rng <= 0:
        return None

    # ارتداد قوي
    recovery = (p - l) / rng
    if recovery < 0.82:
        return None

    # اندفاع من الافتتاح
    drive = (p - o) / o
    if drive < 0.02:
        return None

    # ===== 🔥 تأكيد الاختراق =====
    breakout = p >= h * 1.003
    breakout_strength = (p - h) / h if h else 0

    if breakout and breakout_strength < 0.002:
        return None

    near = p >= h * NEAR_HIGH_BUFFER

    if not breakout and not near:
        return None

    # فلترة إضافية قوة + سيولة
    if volume < 500000 and c < 5:
        return None

    # ===== SCORING =====
    score = 0
    reasons = []

    if c >= 3:
        score += 2
        reasons.append("زخم قوي")

    if c >= 5:
        score += 1
        reasons.append("اندفاع واضح")

    if breakout:
        score += 3
        reasons.append("اختراق مؤكد")

    if recovery >= 0.9:
        score += 1
        reasons.append("سيطرة مشترين")

    if drive >= 0.04:
        score += 1
        reasons.append("اندفاع من الافتتاح")

    if volume >= 500000:
        score += 1
        reasons.append("سيولة قوية")

    if score < 7:
        return None

    # ===== TARGETS =====
    entry = round(p, 2)
    stop = round(entry * 0.97, 2)
    t1 = round(entry * 1.04, 2)
    t2 = round(entry * 1.08, 2)
    t3 = round(entry * 1.12, 2)

    return (
        f"🚨 إشارة قوية\n\n"
        f"📊 السهم: {symbol}\n"
        f"⭐ التقييم: {score}/10\n\n"
        f"💰 الدخول: {entry}\n"
        f"🛑 وقف الخسارة: {stop}\n\n"
        f"🎯 الهدف1: {t1}\n"
        f"🎯 الهدف2: {t2}\n"
        f"🎯 الهدف3: {t3}\n\n"
        f"⚡ التغير: {round(c,2)}%\n"
        f"💧 السيولة: {int(volume):,}\n"
    )

# ===== BOT =====
def market_bot():
    if BOT_TOKEN and CHAT_ID:
        send_message("🔥 البوت شغال")

    while True:
        try:
            now = time.time()

            for s in WATCHLIST:
                q = get_quote(s)
                if not q:
                    time.sleep(1)
                    continue

                signal = build_signal(s, q)

                if signal:
                    last = last_alert.get(s, 0)
                    if now - last > ALERT_COOLDOWN:
                        send_message(signal)
                        last_alert[s] = now

                time.sleep(1)

            time.sleep(SCAN_INTERVAL)

        except:
            time.sleep(10)

# ===== WEBHOOK =====
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    try:
        data = request.get_json(force=True)
        message = data.get("message", {})

        text = message.get("text")
        chat_id = message.get("chat", {}).get("id")
        user_id = message.get("from", {}).get("id")

        # 🔒 حماية
        if not is_allowed_user(user_id):
            print(f"🚫 BLOCKED: {user_id}", flush=True)
            return "ok", 200

        if text and chat_id:
            handle_command(text, str(chat_id))

        return "ok", 200

    except Exception as e:
        print(e)
        return "ok", 200

@app.route("/", methods=["GET"])
def home():
    return "OK", 200

# ===== RUN =====
if __name__ == "__main__":
    threading.Thread(target=market_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
