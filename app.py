from flask import Flask
import threading
import time

app = Flask(__name__)

# ===== البوت =====
def bot_loop():
    while True:
        print("🔥 البوت شغال ويفحص السوق...")
        time.sleep(60)

# ===== الصفحة (عشان Render ما يوقفه) =====
@app.route("/")
def home():
    return "Trading Bot Running"

# ===== تشغيل الاثنين =====
if __name__ == "__main__":
    t = threading.Thread(target=bot_loop)
    t.start()
    app.run(host="0.0.0.0", port=10000)
