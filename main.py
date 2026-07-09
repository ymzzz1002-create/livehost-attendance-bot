import os
import json
import threading
from datetime import datetime, timedelta
from flask import Flask, request
import requests
import gspread
from google.oauth2.service_account import Credentials

TOKEN = os.getenv("BOT_TOKEN", "").strip()
SHEET_ID = os.getenv("SHEET_ID", "").strip()
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", "8"))
ADMIN_IDS = [x.strip() for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

SHEET_NAME = "打卡紀錄"
HEADERS = ["日期", "主播", "Telegram ID", "上班時間", "下班時間", "工時", "狀態"]

app = Flask(__name__)
lock = threading.Lock()


def now_tw():
    return datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)


def today_str():
    return now_tw().strftime("%Y/%m/%d")


def month_str():
    return now_tw().strftime("%Y/%m")


def time_str():
    return now_tw().strftime("%H:%M")


def tg_api(method, payload):
    if not TOKEN:
        print("BOT_TOKEN is missing")
        return None
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    try:
        r = requests.post(url, json=payload, timeout=15)
        print(method, r.status_code, r.text[:300])
        return r.json()
    except Exception as e:
        print("Telegram API error:", e)
        return None


def send_message(chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = keyboard
    return tg_api("sendMessage", payload)


def answer_callback(callback_id):
    return tg_api("answerCallbackQuery", {"callback_query_id": callback_id})


def menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🟢 上班打卡", "callback_data": "clock_in"}],
            [{"text": "🔴 下班打卡", "callback_data": "clock_out"}],
            [
                {"text": "📊 今日統計", "callback_data": "today_report"},
                {"text": "📅 本月統計", "callback_data": "month_report"},
            ],
        ]
    }


def get_user_name(user):
    first = user.get("first_name", "") or ""
    last = user.get("last_name", "") or ""
    username = user.get("username", "") or ""
    name = (first + last).strip()
    return name or username or "未知主播"


def is_admin(user_id):
    if not ADMIN_IDS:
        return True
    return str(user_id) in ADMIN_IDS


def get_sheet():
    if not SHEET_ID or not GOOGLE_CREDENTIALS_JSON:
        raise RuntimeError("SHEET_ID or GOOGLE_CREDENTIALS_JSON is missing")

    info = json.loads(GOOGLE_CREDENTIALS_JSON)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    client = gspread.authorize(creds)
    ss = client.open_by_key(SHEET_ID)

    try:
        ws = ss.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=SHEET_NAME, rows=1000, cols=len(HEADERS))
        ws.append_row(HEADERS)

    values = ws.get_all_values()
    if not values:
        ws.append_row(HEADERS)
    elif values[0] != HEADERS:
        ws.update("A1:G1", [HEADERS])

    return ws


def all_rows(ws):
    values = ws.get_all_values()
    if len(values) <= 1:
        return []
    rows = []
    for idx, row in enumerate(values[1:], start=2):
        row = row + [""] * (len(HEADERS) - len(row))
        rows.append({"sheet_row": idx, **dict(zip(HEADERS, row[:len(HEADERS)]))})
    return rows


def calc_hours(start_time, end_time):
    fmt = "%H:%M"
    start = datetime.strptime(start_time, fmt)
    end = datetime.strptime(end_time, fmt)
    if end < start:
        end += timedelta(days=1)
    diff = end - start
    mins = int(diff.total_seconds() // 60)
    return f"{mins // 60}小時{mins % 60}分"


def parse_hours(text):
    try:
        h = int(text.split("小時")[0])
        m = int(text.split("小時")[1].replace("分", ""))
        return h * 60 + m
    except Exception:
        return 0


def handle_clock_in(chat_id, user):
    ws = get_sheet()
    rows = all_rows(ws)
    uid = str(user["id"])
    name = get_user_name(user)
    date = today_str()
    t = time_str()

    for r in rows:
        if r["日期"] == date and str(r["Telegram ID"]) == uid:
            send_message(chat_id, "⚠️ 你今天已經上班打卡過了，不能重複打卡。")
            return

    ws.append_row([date, name, uid, t, "", "", "直播中"])
    send_message(chat_id, f"✅ 上班打卡成功\n\n👤 {name}\n📅 {date}\n🟢 上班時間：{t}")


def handle_clock_out(chat_id, user):
    ws = get_sheet()
    rows = all_rows(ws)
    uid = str(user["id"])
    name = get_user_name(user)
    date = today_str()
    t = time_str()

    for r in reversed(rows):
        if r["日期"] == date and str(r["Telegram ID"]) == uid:
            if r["下班時間"]:
                send_message(chat_id, "⚠️ 你今天已經下班打卡過了。")
                return

            hours = calc_hours(r["上班時間"], t)
            row_no = r["sheet_row"]
            ws.update(f"E{row_no}:G{row_no}", [[t, hours, "已下班"]])
            send_message(chat_id, f"✅ 下班打卡成功\n\n👤 {name}\n🔴 下班時間：{t}\n⏱ 工時：{hours}")
            return

    send_message(chat_id, "⚠️ 你尚未上班打卡，請先上班打卡。")


def today_report(chat_id):
    ws = get_sheet()
    rows = all_rows(ws)
    date = today_str()
    matched = [r for r in rows if r["日期"] == date]

    if not matched:
        send_message(chat_id, "📊 今日尚無打卡紀錄。")
        return

    text = f"📊 今日直播主打卡統計\n📅 {date}\n\n"
    for r in matched:
        text += f"👤 {r['主播']}\n"
        text += f"🟢 上班：{r['上班時間'] or '未打卡'}\n"
        text += f"🔴 下班：{r['下班時間'] or '尚未下班'}\n"
        text += f"⏱ 工時：{r['工時'] or '直播中'}\n"
        text += f"狀態：{r['狀態'] or ''}\n\n"

    send_message(chat_id, text)


def month_report(chat_id):
    ws = get_sheet()
    rows = all_rows(ws)
    month = month_str()
    summary = {}

    for r in rows:
        if r["日期"].startswith(month) and r["工時"]:
            name = r["主播"]
            summary[name] = summary.get(name, 0) + parse_hours(r["工時"])

    if not summary:
        send_message(chat_id, "📅 本月尚無完整下班紀錄。")
        return

    text = f"📅 本月直播主工時統計\n月份：{month}\n\n"
    for name, mins in sorted(summary.items(), key=lambda x: x[0]):
        text += f"👤 {name}：{mins // 60}小時{mins % 60}分\n"

    send_message(chat_id, text)


@app.get("/")
def health():
    return "livehost attendance bot ok"


@app.post("/webhook")
def webhook():
    data = request.get_json(force=True, silent=True) or {}
    print("update:", json.dumps(data, ensure_ascii=False)[:1000])

    try:
        if "message" in data:
            msg = data["message"]
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "")

            if text.startswith("/start"):
                send_message(chat_id, "🎥 直播主打卡系統\n\n請選擇操作：", menu_keyboard())
            elif text.startswith("/checkin"):
                with lock:
                    handle_clock_in(chat_id, msg["from"])
            elif text.startswith("/checkout"):
                with lock:
                    handle_clock_out(chat_id, msg["from"])
            elif text.startswith("/today"):
                if is_admin(msg["from"]["id"]):
                    today_report(chat_id)
                else:
                    send_message(chat_id, "⚠️ 你沒有權限查看統計。")
            elif text.startswith("/month"):
                if is_admin(msg["from"]["id"]):
                    month_report(chat_id)
                else:
                    send_message(chat_id, "⚠️ 你沒有權限查看統計。")

        if "callback_query" in data:
            q = data["callback_query"]
            answer_callback(q["id"])
            chat_id = q["message"]["chat"]["id"]
            user = q["from"]
            action = q.get("data")

            with lock:
                if action == "clock_in":
                    handle_clock_in(chat_id, user)
                elif action == "clock_out":
                    handle_clock_out(chat_id, user)
                elif action == "today_report":
                    if is_admin(user["id"]):
                        today_report(chat_id)
                    else:
                        send_message(chat_id, "⚠️ 你沒有權限查看統計。")
                elif action == "month_report":
                    if is_admin(user["id"]):
                        month_report(chat_id)
                    else:
                        send_message(chat_id, "⚠️ 你沒有權限查看統計。")

    except Exception as e:
        print("handler error:", repr(e))
        try:
            chat_id = data.get("message", {}).get("chat", {}).get("id") or data.get("callback_query", {}).get("message", {}).get("chat", {}).get("id")
            if chat_id:
                send_message(chat_id, f"⚠️ 系統錯誤：{e}")
        except Exception:
            pass

    return {"ok": True}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
