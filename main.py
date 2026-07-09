import os
import requests
from datetime import datetime, timedelta, date
from flask import Flask, request

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().replace("/rest/v1", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

WEBHOOK_URL = "https://livehost-attendance-bot.onrender.com"
TIMEZONE_OFFSET = 8

app = Flask(__name__)
SUPABASE_REST = f"{SUPABASE_URL}/rest/v1/attendance"


def now_tw():
    return datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)


def today_tw():
    return now_tw().date().isoformat()


def sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def tg_send(chat_id, text, keyboard=True):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}

    if keyboard:
        data["reply_markup"] = {
            "inline_keyboard": [
                [
                    {"text": "🟢 上班", "callback_data": "check_in"},
                    {"text": "🔴 下班", "callback_data": "check_out"}
                ],
                [
                    {"text": "📅 今日統計", "callback_data": "today_stats"},
                    {"text": "📆 本月統計", "callback_data": "month_stats"}
                ]
            ]
        }

    requests.post(url, json=data, timeout=15)


def tg_answer_callback(callback_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
    requests.post(url, json={"callback_query_id": callback_id}, timeout=15)


def get_name(user):
    return user.get("first_name") or user.get("username") or "未知人員"


def sb_get(params):
    r = requests.get(SUPABASE_REST, headers=sb_headers(), params=params, timeout=20)
    try:
        return r.json()
    except Exception:
        return []


def sb_insert(data):
    r = requests.post(SUPABASE_REST, headers=sb_headers(), json=data, timeout=20)
    try:
        return r.json()
    except Exception:
        return []


def sb_patch(row_id, data):
    url = f"{SUPABASE_REST}?id=eq.{row_id}"
    r = requests.patch(url, headers=sb_headers(), json=data, timeout=20)
    try:
        return r.json()
    except Exception:
        return []


def parse_db_time(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)
    except Exception:
        return None


def check_in(chat_id, user):
    user_id = str(user["id"])
    user_name = get_name(user)
    work_date = today_tw()
    now = now_tw()

    rows = sb_get({
        "user_id": f"eq.{user_id}",
        "work_date": f"eq.{work_date}",
        "check_out": "is.null",
        "select": "*"
    })

    if rows:
        tg_send(chat_id, "⚠️ 你今天已經上班打卡了，不能重複打卡。")
        return

    result = sb_insert({
        "user_id": user_id,
        "user_name": user_name,
        "work_date": work_date,
        "check_in": now.isoformat(),
        "check_out": None,
        "work_hours": 0,
        "status": "上班"
    })

    tg_send(
        chat_id,
        f"🟢 上班打卡成功\n\n"
        f"👤 {user_name}\n"
        f"⏰ {now.strftime('%Y-%m-%d %H:%M:%S')}"
    )


def check_out(chat_id, user):
    user_id = str(user["id"])
    user_name = get_name(user)
    work_date = today_tw()
    now = now_tw()

    rows = sb_get({
        "user_id": f"eq.{user_id}",
        "work_date": f"eq.{work_date}",
        "check_out": "is.null",
        "select": "*",
        "order": "check_in.desc",
        "limit": "1"
    })

    if not rows:
        tg_send(chat_id, "⚠️ 找不到今天尚未下班的上班紀錄。\n\n請先按「今日統計」確認今天是否有上班紀錄。")
        return

    row = rows[0]
    check_in_time = parse_db_time(row.get("check_in"))

    if not check_in_time:
        tg_send(chat_id, "⚠️ 這筆上班紀錄時間異常，請檢查資料表。")
        return

    work_hours = round((now - check_in_time).total_seconds() / 3600, 2)

    sb_patch(row["id"], {
        "check_out": now.isoformat(),
        "work_hours": work_hours,
        "status": "下班"
    })

    tg_send(
        chat_id,
        f"🔴 下班打卡成功\n\n"
        f"👤 {user_name}\n"
        f"⏰ 下班時間：{now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🕒 今日工時：{work_hours} 小時"
    )


def today_stats(chat_id, user):
    user_id = str(user["id"])
    work_date = today_tw()

    rows = sb_get({
        "user_id": f"eq.{user_id}",
        "work_date": f"eq.{work_date}",
        "select": "*",
        "order": "check_in.asc"
    })

    if not rows:
        tg_send(chat_id, "📅 今日統計\n\n今天還沒有打卡紀錄。")
        return

    text = "📅 今日統計\n\n"
    total = 0

    for row in rows:
        ci = row.get("check_in")
        co = row.get("check_out")
        hours = row.get("work_hours") or 0
        total += float(hours)

        ci_txt = ci[11:16] if ci else "--:--"
        co_txt = co[11:16] if co else "尚未下班"

        text += f"🟢 {ci_txt} ～ 🔴 {co_txt}"
        if hours:
            text += f"（{hours} 小時）"
        text += "\n"

    text += f"\n🕒 今日總工時：{round(total, 2)} 小時"
    tg_send(chat_id, text)


def month_stats(chat_id, user):
    user_id = str(user["id"])
    now = now_tw()

    first_day = date(now.year, now.month, 1).isoformat()

    rows = sb_get({
        "user_id": f"eq.{user_id}",
        "work_date": f"gte.{first_day}",
        "select": "*",
        "order": "work_date.asc"
    })

    rows = [
        row for row in rows
        if str(row.get("work_date", "")).startswith(f"{now.year}-{now.month:02d}")
    ]

    if not rows:
        tg_send(chat_id, "📆 本月統計\n\n本月還沒有打卡紀錄。")
        return

    total_hours = 0
    work_days = set()
    detail = ""

    for row in rows:
        work_days.add(row["work_date"])
        hours = row.get("work_hours") or 0
        total_hours += float(hours)

        ci = row.get("check_in")
        co = row.get("check_out")

        ci_txt = ci[11:16] if ci else "--:--"
        co_txt = co[11:16] if co else "尚未下班"

        detail += f"{row['work_date']}　{ci_txt}～{co_txt}"
        if hours:
            detail += f"（{hours} 小時）"
        detail += "\n"

    avg = round(total_hours / len(work_days), 2) if work_days else 0

    text = (
        f"📆 本月統計\n\n"
        f"🗓 出勤天數：{len(work_days)} 天\n"
        f"🕒 本月總工時：{round(total_hours, 2)} 小時\n"
        f"📈 平均每日工時：{avg} 小時\n\n"
        f"本月明細：\n{detail}"
    )

    tg_send(chat_id, text)


@app.route("/", methods=["GET"])
def home():
    return "Bot is running"


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json() or {}

    if "callback_query" in update:
        callback = update["callback_query"]
        tg_answer_callback(callback["id"])

        data = callback["data"]
        user = callback["from"]
        chat_id = callback["message"]["chat"]["id"]

        if data == "check_in":
            check_in(chat_id, user)
        elif data == "check_out":
            check_out(chat_id, user)
        elif data == "today_stats":
            today_stats(chat_id, user)
        elif data == "month_stats":
            month_stats(chat_id, user)

    elif "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        tg_send(chat_id, "請選擇打卡功能：")

    return "ok"


@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    r = requests.get(url, params={"url": f"{WEBHOOK_URL}/webhook"}, timeout=20)
    return r.text


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
