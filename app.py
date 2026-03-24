from flask import Flask
import requests
import time
import threading
import yfinance as yf
import pandas as pd
import os

app = Flask(__name__)

# =========================
# بياناتك
# =========================
BOT_TOKEN = "8452344889:AAFkEzBOJ5RdWmXAQtxt8s42R_TUWPlrfFo"
CHAT_ID = "912977673"

# =========================
# قائمة الأسهم
# =========================
WATCHLIST = [
    "YYAI", "TPET", "VEEE", "SOWG", "STI",
    "ATPC", "SMSI", "LGVN", "ACXP", "AGRZ",
    "LASE", "DDD", "ALTO", "MOBX", "IOVA",
    "PRSO", "EDSA", "JEM", "DXST", "ASNS",
    "SMWB", "BSM", "SND", "BOF", "SOUN",
    "CPIX", "NIO", "VSA", "MYO", "MNDR", "FIEE"
]

# =========================
# إعدادات البوت
# =========================
CHECK_INTERVAL_SECONDS = 12          # سرعة الفحص
COOLDOWN_SECONDS = 1800              # منع تكرار نفس السهم 30 دقيقة
MIN_LIQUIDITY = 150000               # أقل سيولة بالدولار في آخر دقيقة
MIN_RVOL = 2.0                       # أقل RVOL
MIN_PRICE_CHANGE_5M = 1.2            # أقل تغير خلال آخر 5 دقائق %
BREAKOUT_LOOKBACK = 20               # اختراق أعلى هاي آخر 20 شمعة
NEAR_BREAKOUT_BUFFER = 0.995         # قريب من الاختراق حتى قبل الانفجار

# الربح/الخسارة
STOP_LOSS_PCT = 0.04                 # 4%
TARGET1_PCT = 0.04                   # 4%
TARGET2_PCT = 0.07                   # 7%
TARGET3_PCT = 0.10                   # 10%

# =========================
# متغيرات داخلية
# =========================
sent_start = False
last_sent = {}

# =========================
# Telegram
# =========================
def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message
    }
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}", flush=True)

# =========================
# Flask route
# =========================
@app.route("/", methods=["GET", "POST"])
def home():
    return "Pro Trading Bot is running"

# =========================
# أدوات مساعدة
# =========================
def format_money(value: float) -> str:
    if value >= 1_000_000:
        return f"{value/1_000_000:.2f}M$"
    if value >= 1_000:
        return f"{value/1_000:.2f}K$"
    return f"{value:.2f}$"

def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def get_data(symbol: str, interval: str, period: str = "1d") -> pd.DataFrame:
    try:
        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=False,
            threads=False,
            prepost=True
        )
        if df is None or df.empty:
            return pd.DataFrame()

        df = flatten_columns(df)
        df = df.dropna().copy()
        return df
    except Exception as e:
        print(f"Data error {symbol} {interval}: {e}", flush=True)
        return pd.DataFrame()

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # متوسطات
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()

    # متوسط الحجم و RVOL
    df["AVG_VOL20"] = df["Volume"].rolling(20).mean()
    df["RVOL"] = df["Volume"] / df["AVG_VOL20"]

    # VWAP
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    cumulative_tpv = (typical_price * df["Volume"]).cumsum()
    cumulative_vol = df["Volume"].cumsum()
    df["VWAP"] = cumulative_tpv / cumulative_vol.replace(0, pd.NA)

    return df

# =========================
# منطق الإشارة الاحترافي
# =========================
def check_signal(symbol: str):
    df1 = get_data(symbol, "1m")
    df5 = get_data(symbol, "5m")
    df15 = get_data(symbol, "15m")

    if df1.empty or df5.empty or df15.empty:
        return None

    if len(df1) < 30 or len(df5) < 30 or len(df15) < 30:
        return None

    try:
        df1 = add_indicators(df1)
        df5 = add_indicators(df5)
        df15 = add_indicators(df15)

        last1 = df1.iloc[-1]
        last5 = df5.iloc[-1]
        last15 = df15.iloc[-1]

        # أسعار أساسية
        price = float(last1["Close"])
        prev_5m_price = float(df1["Close"].iloc[-6]) if len(df1) >= 6 else price
        price_change_5m = ((price - prev_5m_price) / prev_5m_price) * 100 if prev_5m_price else 0

        # اتجاه
        trend_1m = price > float(last1["EMA9"]) > float(last1["EMA20"])
        trend_5m = float(last5["Close"]) > float(last5["EMA20"])
        trend_15m = float(last15["Close"]) > float(last15["EMA20"])

        # فوق VWAP
        above_vwap = price > float(last1["VWAP"])

        # سيولة
        volume_1m = float(last1["Volume"])
        liquidity = price * volume_1m

        # RVOL
        rvol = float(last1["RVOL"]) if pd.notna(last1["RVOL"]) else 0.0

        # اختراق أو قريب من الاختراق
        breakout_level = float(df5["High"].iloc[-BREAKOUT_LOOKBACK:-1].max())
        breakout_now = price > breakout_level
        near_breakout = price >= breakout_level * NEAR_BREAKOUT_BUFFER

        # زخم مبكر
        ema_stack = float(last1["EMA9"]) > float(last1["EMA20"]) > float(last1["EMA50"])
        strong_candle = (
            float(last1["Close"]) > float(last1["Open"]) and
            (float(last1["Close"]) - float(last1["Low"])) > (float(last1["High"]) - float(last1["Close"]))
        )

        # فلتر احترافي
        pre_explosion_setup = (
            near_breakout and
            price_change_5m >= MIN_PRICE_CHANGE_5M and
            liquidity >= MIN_LIQUIDITY and
            rvol >= MIN_RVOL and
            trend_1m and
            trend_5m and
            trend_15m and
            above_vwap and
            ema_stack
        )

        confirmed_breakout = (
            breakout_now and
            liquidity >= MIN_LIQUIDITY and
            rvol >= MIN_RVOL and
            trend_1m and
            trend_5m and
            trend_15m and
            above_vwap and
            strong_candle
        )

        if not (pre_explosion_setup or confirmed_breakout):
            return None

        signal_type = "قبل الانفجار" if pre_explosion_setup and not breakout_now else "اختراق مؤكد"

        # إدارة الصفقة
        entry = round(price, 2)
        stop = round(entry * (1 - STOP_LOSS_PCT), 2)
        target1 = round(entry * (1 + TARGET1_PCT), 2)
        target2 = round(entry * (1 + TARGET2_PCT), 2)
        target3 = round(entry * (1 + TARGET3_PCT), 2)

        # نص فني
        message = f"""🚨 إشارة احترافية

📊 السهم: {symbol}
🧠 النوع: {signal_type}

💰 الدخول: {entry}
🛑 وقف الخسارة: {stop}

🎯 الهدف 1: {target1}
🎯 الهدف 2: {target2}
🎯 الهدف 3: {target3}

💧 السيولة: {format_money(liquidity)}
📈 RVOL: {rvol:.2f}
⚡ تغير 5 دقائق: {price_change_5m:.2f}%
📍 مستوى الاختراق: {breakout_level:.2f}

✅ الشروط:
- فوق VWAP
- فوق EMA 9 / 20 / 50
- سيولة قوية
- زخم صاعد
- تأكيد 5m و 15m
"""
        return message

    except Exception as e:
        print(f"Signal error {symbol}: {e}", flush=True)
        return None

# =========================
# حلقة البوت
# =========================
def bot_loop():
    global sent_start

    if not sent_start:
        send_telegram("🚀 البوت الاحترافي بدأ يفحص السوق")
        sent_start = True

    while True:
        try:
            now_ts = time.time()

            for symbol in WATCHLIST:
                signal = check_signal(symbol)

                if signal:
                    last_time = last_sent.get(symbol, 0)
                    if now_ts - last_time > COOLDOWN_SECONDS:
                        send_telegram(signal)
                        last_sent[symbol] = now_ts
                        print(f"Signal sent: {symbol}", flush=True)

            print("🔥 يفحص السوق...", flush=True)
            time.sleep(CHECK_INTERVAL_SECONDS)

        except Exception as e:
            print(f"Loop error: {e}", flush=True)
            time.sleep(CHECK_INTERVAL_SECONDS)

# =========================
# تشغيل
# =========================
if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
