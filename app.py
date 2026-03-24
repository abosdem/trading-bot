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
CHECK_INTERVAL_SECONDS = 20
COOLDOWN_SECONDS = 2700          # 45 دقيقة
MIN_LIQUIDITY = 120000           # أقل سيولة بالدولار
MIN_RVOL = 1.8
MIN_PRICE_CHANGE_5M = 1.0
BREAKOUT_LOOKBACK = 20
NEAR_BREAKOUT_BUFFER = 0.995
MIN_SCORE = 6

# إدارة الصفقة
STOP_LOSS_PCT = 0.04
TARGET1_PCT = 0.04
TARGET2_PCT = 0.07
TARGET3_PCT = 0.10

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
# Route
# =========================
@app.route("/", methods=["GET", "POST"])
def home():
    return "Elite Trading Bot Running"

# =========================
# Helpers
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

        numeric_cols = ["Open", "High", "Low", "Close", "Volume"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna()
        return df

    except Exception as e:
        print(f"Data error {symbol} {interval}: {e}", flush=True)
        return pd.DataFrame()

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()

    df["AVG_VOL20"] = df["Volume"].rolling(20).mean()
    df["RVOL"] = df["Volume"] / df["AVG_VOL20"]

    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    cumulative_tpv = (typical_price * df["Volume"]).cumsum()
    cumulative_vol = df["Volume"].cumsum().replace(0, pd.NA)
    df["VWAP"] = cumulative_tpv / cumulative_vol

    return df

# =========================
# منطق الإشارة
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

        # ===== السعر الحالي =====
        price = float(last1["Close"])
        open1 = float(last1["Open"])
        high1 = float(last1["High"])
        low1 = float(last1["Low"])

        if price <= 0:
            return None

        # ===== تغير آخر 5 دقائق =====
        prev_5m_price = float(df1["Close"].iloc[-6]) if len(df1) >= 6 else price
        if prev_5m_price <= 0:
            return None

        price_change_5m = ((price - prev_5m_price) / prev_5m_price) * 100

        # تجاهل الإشارات إذا التغير صفر أو سالب أو NaN
        if pd.isna(price_change_5m) or price_change_5m <= 0:
            return None

        # ===== EMA =====
        ema9 = float(last1["EMA9"])
        ema20 = float(last1["EMA20"])
        ema50 = float(last1["EMA50"])

        close5 = float(last5["Close"])
        ema20_5 = float(last5["EMA20"])

        close15 = float(last15["Close"])
        ema20_15 = float(last15["EMA20"])

        # ===== VWAP =====
        if pd.isna(last1["VWAP"]):
            return None
        vwap = float(last1["VWAP"])

        # ===== السيولة =====
        avg_1m_vol_5bars = df1["Volume"].tail(5).mean()

        if pd.isna(avg_1m_vol_5bars) or avg_1m_vol_5bars <= 0:
            return None

        liquidity = price * float(avg_1m_vol_5bars)

        if pd.isna(liquidity) or liquidity <= 0:
            return None

        # ===== RVOL =====
        if pd.isna(last1["RVOL"]):
            return None

        rvol = float(last1["RVOL"])

        if rvol <= 0:
            return None

        # ===== اختراق =====
        breakout_window = df5["High"].iloc[-BREAKOUT_LOOKBACK:-1]

        if breakout_window.empty:
            return None

        breakout_level = float(breakout_window.max())
        breakout_now = price > breakout_level
        near_breakout = price >= breakout_level * NEAR_BREAKOUT_BUFFER

        # ===== اتجاه =====
        trend_1m = price > ema9 > ema20
        trend_5m = close5 > ema20_5
        trend_15m = close15 > ema20_15
        above_vwap = price > vwap
        ema_stack = ema9 > ema20 > ema50

        # ===== زخم =====
        strong_candle = (price > open1) and ((price - low1) >= (high1 - price))
        volume_ok = liquidity >= MIN_LIQUIDITY
        rvol_ok = rvol >= MIN_RVOL
        momentum_ok = price_change_5m >= MIN_PRICE_CHANGE_5M

        # إذا القيم الأساسية ضعيفة، تجاهل فورًا
        if not volume_ok:
            return None
        if not rvol_ok:
            return None
        if not momentum_ok:
            return None

        # ===== نظام نقاط =====
        score = 0
        reasons = []

        if near_breakout:
            score += 2
            reasons.append("قريب من الاختراق")

        if breakout_now:
            score += 2
            reasons.append("اختراق مؤكد")

        if trend_1m:
            score += 1
            reasons.append("اتجاه 1m")

        if trend_5m:
            score += 1
            reasons.append("اتجاه 5m")

        if trend_15m:
            score += 1
            reasons.append("اتجاه 15m")

        if above_vwap:
            score += 1
            reasons.append("فوق VWAP")

        if ema_stack:
            score += 1
            reasons.append("EMA stack")

        if volume_ok:
            score += 1
            reasons.append("سيولة قوية")

        if rvol_ok:
            score += 1
            reasons.append("RVOL قوي")

        if momentum_ok:
            score += 1
            reasons.append("زخم 5m")

        if strong_candle:
            score += 1
            reasons.append("شمعة قوية")

        if score < MIN_SCORE:
            return None

        signal_type = "قبل الانفجار" if near_breakout and not breakout_now else "اختراق مؤكد"

        entry = round(price, 2)
        stop = round(entry * (1 - STOP_LOSS_PCT), 2)
        target1 = round(entry * (1 + TARGET1_PCT), 2)
        target2 = round(entry * (1 + TARGET2_PCT), 2)
        target3 = round(entry * (1 + TARGET3_PCT), 2)

        reasons_text = " - ".join(reasons[:5])

        message = f"""🚨 إشارة نخبة

📊 السهم: {symbol}
🧠 النوع: {signal_type}
⭐ التقييم: {score}/11

💰 الدخول: {entry}
🛑 الوقف: {stop}

🎯 الهدف 1: {target1}
🎯 الهدف 2: {target2}
🎯 الهدف 3: {target3}

💧 السيولة: {format_money(liquidity)}
📈 RVOL: {rvol:.2f}
⚡ تغير 5 دقائق: {price_change_5m:.2f}%
📍 مستوى الاختراق: {breakout_level:.2f}

✅ أهم الأسباب:
{reasons_text}
"""
        return message

    except Exception as e:
        print(f"Signal error {symbol}: {e}", flush=True)
        return None

# =========================
# Bot loop
# =========================
def bot_loop():
    global sent_start

    if not sent_start:
        send_telegram("🚀 بوت النخبة بدأ يفحص السوق")
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

            time.sleep(CHECK_INTERVAL_SECONDS)

        except Exception as e:
            print(f"Loop error: {e}", flush=True)
            time.sleep(CHECK_INTERVAL_SECONDS)

# =========================
# Run
# =========================
if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
