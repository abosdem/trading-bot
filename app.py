import os
import time
import threading
import requests
from bs4 import BeautifulSoup
from flask import Flask

app = Flask(__name__)

BOT_TOKEN = os.environ.get("8452344889:AAFkEzBOJ5RdWmXAQtxt8s42R_TUWPlrfFo")
CHAT_ID = os.environ.get("912977673")

sent = {}

def send(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except:
        pass

def get_stocks():
    url = "https://finviz.com/screener.ashx?v=111&f=geo_usa,sh_price_u10,sh_avgvol_o500,sh_relvol_o2"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(r.text, "lxml")

    rows = soup.select("table.table-light tr")[1:]

    stocks = []
    for row in rows[:10]:
        cols = row.find_all("td")
        if len(cols) < 10:
            continue

        symbol = cols[1].text
        price = float(cols[8].text)
        change = float(cols[9].text.replace("%", ""))
        volume = int(cols[10].text.replace(",", ""))

        stocks.append((symbol, price, change, volume))

    return stocks

def run_bot():
    print("🔥 BOT WORKING", flush=True)

    while True:
        try:
            stocks = get_stocks()
            print("📊 OK", flush=True)

            for s in stocks:
                symbol, price, change, volume = s

                if change > 3 and volume > 500000:
                    if time.time() - sent.get(symbol, 0) > 3600:
                        msg = f"""🚀 فرصة قوية

📊 {symbol}
💰 {price}
⚡ {change}%
📈 Volume: {volume}
"""
                        send(msg)
                        sent[symbol] = time.time()

            time.sleep(180)

        except Exception as e:
            print(f"ERROR: {e}", flush=True)
            time.sleep(60)

@app.route("/")
def home():
    return "OK"

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
