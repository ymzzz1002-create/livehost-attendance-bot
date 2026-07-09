import os
import json
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

DATA_FILE = "attendance.json"
TZ = timezone(timedelta(hours=8))


def now():
    return datetime.now(TZ)


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fmt_duration(seconds):
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}小時{minutes}分"


def get_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 我要上班", callback_data="clock_in"),
            InlineKeyboardButton("🏠 我要下班", callback_data="clock_out"),
        ],
        [
            InlineKeyboardButton("📋 今日狀態", callback_data="today_status"),
            InlineKeyboardButton("📊 本月統計", callback_data="month_status"),
        ]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 飛機群打卡系統\n\n請選擇要執行的操作：",
        reply_markup=get_keyboard()
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = load_data()
    user = query.from_user
    user_id = str(user.id)
    user_name = user.full_name
    today = now().strftime("%Y-%m-%d")
    action = query.data

    if action == "clock_in":
        data.setdefault(user_id, {
            "name": user_name,
            "records": {}
        })

        data[user_id]["name"] = user_name
        data[user_id]["records"].setdefault(today, {
            "clock_in": None,
            "clock_out": None,
            "total_seconds": 0
        })

        record = data[user_id]["records"][today]

        if record["clock_in"] and not record["clock_out"]:
            await query.message.reply_text(f"⚠️ {user_name} 你今天已經上班中了。")
            return

        record["clock_in"] = now().isoformat()
        record["clock_out"] = None
        save_data(data)

        await query.message.reply_text(
            f"✅ {user_name} 已上班\n時間：{now().strftime('%H:%M')}"
        )

    elif action == "clock_out":
        if user_id not in data or today not in data[user_id].get("records", {}):
            await query.message.reply_text(f"⚠️ {user_name} 你今天還沒有按上班。")
            return

        record = data[user_id]["records"][today]

        if not record.get("clock_in"):
            await query.message.reply_text(f"⚠️ {user_name} 你今天還沒有按上班。")
            return

        if record.get("clock_out"):
            await query.message.reply_text(f"⚠️ {user_name} 你今天已經下班了。")
            return

        clock_in_time = datetime.fromisoformat(record["clock_in"])
        clock_out_time = now()
        work_seconds = (clock_out_time - clock_in_time).total_seconds()

        record["clock_out"] = clock_out_time.isoformat()
        record["total_seconds"] = int(record.get("total_seconds", 0) + work_seconds)
        save_data(data)

        await query.message.reply_text(
            f"🏠 {user_name} 已下班\n"
            f"時間：{clock_out_time.strftime('%H:%M')}\n"
            f"今日工時：{fmt_duration(record['total_seconds'])}"
        )

    elif action == "today_status":
        lines = [f"📋 今日狀態｜{today}\n"]
        has_record = False

        for _, user_data in data.items():
            name = user_data.get("name", "未知成員")
            record = user_data.get("records", {}).get(today)

            if not record:
                continue

            has_record = True
            clock_in = record.get("clock_in")
            clock_out = record.get("clock_out")
            total_seconds = int(record.get("total_seconds", 0))

            if clock_in and not clock_out:
                clock_in_time = datetime.fromisoformat(clock_in)
                work_text = fmt_duration((now() - clock_in_time).total_seconds())
                status = "🟢 上班中"
                out_text = "尚未下班"
            elif clock_in and clock_out:
                work_text = fmt_duration(total_seconds)
                status = "✅ 已下班"
                out_text = datetime.fromisoformat(clock_out).strftime("%H:%M")
            else:
                continue

            in_text = datetime.fromisoformat(clock_in).strftime("%H:%M")

            lines.append(
                f"👤 {name}\n"
                f"狀態：{status}\n"
                f"上班：{in_text}\n"
                f"下班：{out_text}\n"
                f"今日工時：{work_text}\n"
            )

        if not has_record:
            lines.append("目前今天還沒有人按上班。")

        await query.message.reply_text("\n".join(lines))

    elif action == "month_status":
        current_month = now().strftime("%Y-%m")
        lines = [f"📊 本月統計｜{current_month}\n"]
        has_record = False

        for _, user_data in data.items():
            name = user_data.get("name", "未知成員")
            records = user_data.get("records", {})

            total_seconds = 0
            work_days = 0

            for date, record in records.items():
                if not date.startswith(current_month):
                    continue

                day_seconds = int(record.get("total_seconds", 0))

                if record.get("clock_in") and not record.get("clock_out"):
                    clock_in_time = datetime.fromisoformat(record["clock_in"])
                    day_seconds += int((now() - clock_in_time).total_seconds())

                if record.get("clock_in"):
                    work_days += 1

                total_seconds += day_seconds

            if work_days > 0:
                has_record = True
                lines.append(
                    f"👤 {name}\n"
                    f"出勤天數：{work_days}天\n"
                    f"本月工時：{fmt_duration(total_seconds)}\n"
                )

        if not has_record:
            lines.append("目前本月還沒有任何出勤紀錄。")

        await query.message.reply_text("\n".join(lines))


def main():
    if not TOKEN:
        raise ValueError("請先設定 TELEGRAM_BOT_TOKEN")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("飛機打卡機器人已啟動")
    app.run_polling()


if __name__ == "__main__":
    main()
