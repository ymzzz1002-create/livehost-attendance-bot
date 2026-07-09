import os
import requests
from datetime import datetime, timedelta
from flask import Flask, request

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_URL = "https://livehost-attendance-bot.onrender.com"
TIMEZONE_OFFSET = 8

app = Flask(__name__)

records = {}

def now_tw():
    return datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": chat_id,
        "text": text
    })

def get_name(message):
    user = message.get("from", {})
    return user.get("first_name") or user.get("username") or "未知人員"

@app.route("/", methods=["GET"])
def home():
    return "Bot is running"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()
    user_id = message.get("from", {}).get("id")
    name = get_name(message)

    if not chat_id or not text:
        return "ok"

    today = now_tw().strftime("%Y/%m/%d")
    time_now = now_tw().strftime("%H:%M")

    if today not in records:
        records[today] = {}

    if user_id not in records[today]:
        records[today][user_id] = {
            "name": name,
            "上班": "",
            "下班": ""
        }

    if text in ["/start", "開始"]:
        send_message(chat_id, "打卡機器人已啟動\n\n可使用：\n/上班\n/下班\n/今日")
    
    elif text in ["/上班", "上班"]:
        records[today][user_id]["上班"] = time_now
        send_message(chat_id, f"✅ {name} 已於 {time_now} 上班打卡")

    elif text in ["/下班", "下班"]:
        records[today][user_id]["下班"] = time_now
        send_message(chat_id, f"🏁 {name} 已於 {time_now} 下班打卡")

    elif text in ["/今日", "今日"]:
        msg = f"📋 今日打卡紀錄 {today}\n\n"
        for r in records[today].values():
            msg += f"👤 {r['name']}\n"
            msg += f"上班：{r['上班'] or '尚未打卡'}\n"
            msg += f"下班：{r['下班'] or '尚未打卡'}\n\n"
        send_message(chat_id, msg)

    else:
        send_message(chat_id, "請輸入：\n/上班\n/下班\n/今日")

    return "ok"

def set_webhook():
    if BOT_TOKEN:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        requests.post(url, json={
            "url": f"{WEBHOOK_URL}/webhook"
        })

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
