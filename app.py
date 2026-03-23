from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")


def send_telegram_message(text, chat_id=None):
    target_chat_id = chat_id if chat_id else CHAT_ID
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": target_chat_id,
        "text": text
    }
    response = requests.post(url, json=payload, timeout=15)
    return response.json()


@app.route("/", methods=["GET"])
def home():
    return "Bot is running", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)

        # 1) إذا كانت رسالة من تيليجرام
        if "message" in data:
            chat_id = data["message"]["chat"]["id"]
            user_text = data["message"].get("text", "")

            if user_text == "/start":
                reply = "أهلًا، البوت شغال بنجاح ✅"
            else:
                reply = f"وصلتني رسالتك: {user_text}"

            telegram_result = send_telegram_message(reply, chat_id=chat_id)

            return jsonify({
                "status": "telegram_message_received",
                "received": data,
                "telegram": telegram_result
            }), 200

        # 2) إذا كانت بيانات من TradingView
        ticker = data.get("ticker", "غير معروف")
        price = data.get("price", "غير متوفر")
        volume = data.get("volume", "غير متوفر")
        event_time = data.get("time", "غير متوفر")
        signal = data.get("signal", "تنبيه")

        message = (
            f"🚨 {signal}\n\n"
            f"📊 السهم: {ticker}\n"
            f"💰 السعر: {price}\n"
            f"📈 الحجم: {volume}\n"
            f"🕒 الوقت: {event_time}"
        )

        telegram_result = send_telegram_message(message)

        return jsonify({
            "status": "tradingview_received",
            "received": data,
            "telegram": telegram_result
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
