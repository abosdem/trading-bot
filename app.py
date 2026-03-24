from flask import Flask
import threading
import time

app = Flask(__name__)

def bot_loop():
    while True:
        print("🔥 البوت شغال ويفحص السوق...")
        time.sleep(60)

# 🔥 شغل البوت مباشرة
threading.Thread(target=bot_loop).start()

@app.route("/")
def home():
    return "Trading Bot Running"
