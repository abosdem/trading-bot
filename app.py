import os
from flask import Flask

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY")

print("BOT_TOKEN:", "OK" if BOT_TOKEN else "MISSING", flush=True)
print("CHAT_ID:", "OK" if CHAT_ID else "MISSING", flush=True)
print("FINNHUB_API_KEY:", "OK" if FINNHUB_API_KEY else "MISSING", flush=True)

@app.route("/", methods=["GET", "POST"])
def home():
    return "OK"

@app.route("/env", methods=["GET"])
def env_check():
    return {
        "BOT_TOKEN": bool(BOT_TOKEN),
        "CHAT_ID": bool(CHAT_ID),
        "FINNHUB_API_KEY": bool(FINNHUB_API_KEY),
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)
