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
ALLOWED_USER_ID = "912977673"

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
MIN_VOLUME = 300000

NEAR_HIGH_BUFFER = 0.998

last_alert = {}

session = requests.Session()

# ===== TELEGRAM =====
def send_message(text, chat_id=None):
    target_chat_id = str(chat_id or CHAT_ID).strip()

    if not BOT_TOKEN or not target_chat_id:
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        session.post(url, data={"chat_id": target_chat_id, "text": text}, timeout=10)
    except:
        pass

def handle_command(text, chat_id):
    cmd = (text or "").lower()

    if cmd == "/start":
        send_message("🚀 البوت جاهز", chat_id)

    elif cmd == "/status":
        send_message("✅ البوت يعمل", chat_id)

    elif cmd == "/watchlist":
        send_message("\n".join(WATCHLIST), chat_id)

    elif cmd == "/test":
        send_message("🔥 شغال", chat_id)

# ===== FINNHUB =====
def get_quote(symbol):
    if not FINNHUB_API_KEY:
        return None

    try:
        r = session.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": symbol, "token": FINNHUB_API_KEY},
            timeout=10
        )

        d = r.json()

        return {
            "price": d.get("c"),
            "change": d.get("dp"),
            "high": d.get("h"),
            "low": d.get("l"),
            "prev": d.get("pc"),
            "open": d.get("o"),
            "volume": d.get("v") or 0,
        }
    except:
        return None

# ===== SIGNAL =====
def build_signal(s, q):
    if not q:
        return None

    p = q["price"]
    c = q["change"]
    h = q["high"]
    l = q["low"]
    o = q["open"]
    v = q["volume"]

    if not p or not c or not h or not l or not o:
        return None

    if p < MIN_PRICE or p > MAX_PRICE:
        return None

    if c < MIN_CHANGE or c > MAX_CHANGE:
        return None

    if v < MIN_VOLUME:
        return None

    if p <= o:
        return None

    if p < h * NEAR_HIGH_BUFFER:
        return None

    return f"🚨 {s}\n💰 {round(p,2)}\n⚡ {round(c,2)}%\n💧 {int(v):,}"

# ===== BOT =====
def market_bot():
    while True:
        try:
            now = time.time()

            for s in WATCHLIST:
                q = get_quote(s)

                signal = build_signal(s, q)

                if signal:
                    last = last_alert.get(s, 0)

                    if now - last > ALERT_COOLDOWN:
                        send_message(signal)
                        last_alert[s] = now

                time.sleep(1)

            time.sleep(SCAN_INTERVAL)

        except:
            time.sleep(5)

# ===== WEBHOOK =====
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    try:
        data = request.get_json()
        message = data.get("message", {})

        user = message.get("from")
        if not user:
            return "ok", 200

        user_id = str(user.get("id"))

        # 🔒 الحماية
        if user_id != ALLOWED_USER_ID:
            return "ok", 200

        text = message.get("text")
        chat_id = message.get("chat", {}).get("id")

        if text and chat_id:
            handle_command(text, str(chat_id))

        return "ok", 200

    except:
        return "ok", 200

@app.route("/", methods=["GET"])
def home():
    return "OK", 200

# ===== RUN =====
if __name__ == "__main__":
    threading.Thread(target=market_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
