import discord
from discord.ext import commands
from discord import app_commands
import os
import json
from datetime import datetime, timedelta, timezone

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

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


class AttendanceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="我要上班", style=discord.ButtonStyle.success, custom_id="clock_in")
    async def clock_in(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name
        today = now().strftime("%Y-%m-%d")

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
            await interaction.response.send_message(
                f"⚠️ {user_name} 你今天已經上班中了，不用重複按。",
                ephemeral=True
            )
            return

        record["clock_in"] = now().isoformat()
        record["clock_out"] = None

        save_data(data)

        await interaction.response.send_message(
            f"✅ {user_name} 已上班\n時間：{now().strftime('%H:%M')}"
        )

    @discord.ui.button(label="我要下班", style=discord.ButtonStyle.danger, custom_id="clock_out")
    async def clock_out(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name
        today = now().strftime("%Y-%m-%d")

        if user_id not in data or today not in data[user_id]["records"]:
            await interaction.response.send_message(
                f"⚠️ {user_name} 你今天還沒有按上班。",
                ephemeral=True
            )
            return

        record = data[user_id]["records"][today]

        if not record["clock_in"]:
            await interaction.response.send_message(
                f"⚠️ {user_name} 你今天還沒有按上班。",
                ephemeral=True
            )
            return

        if record["clock_out"]:
            await interaction.response.send_message(
                f"⚠️ {user_name} 你今天已經下班了。",
                ephemeral=True
            )
            return

        clock_in_time = datetime.fromisoformat(record["clock_in"])
        clock_out_time = now()

        work_seconds = (clock_out_time - clock_in_time).total_seconds()
        record["clock_out"] = clock_out_time.isoformat()
        record["total_seconds"] = int(record.get("total_seconds", 0) + work_seconds)

        save_data(data)

        await interaction.response.send_message(
            f"🏠 {user_name} 已下班\n"
            f"時間：{clock_out_time.strftime('%H:%M')}\n"
            f"今日工時：{fmt_duration(record['total_seconds'])}"
        )

    @discord.ui.button(label="今日狀態", style=discord.ButtonStyle.primary, custom_id="today_status")
    async def today_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        today = now().strftime("%Y-%m-%d")

        lines = [f"📋 今日狀態｜{today}\n"]

        has_record = False

        for user_id, user_data in data.items():
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
                current_seconds = (now() - clock_in_time).total_seconds()
                work_text = fmt_duration(current_seconds)
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

        await interaction.response.send_message("\n".join(lines))

    @discord.ui.button(label="本月統計", style=discord.ButtonStyle.secondary, custom_id="month_status")
    async def month_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        current_month = now().strftime("%Y-%m")

        lines = [f"📊 本月統計｜{current_month}\n"]

        has_record = False

        for user_id, user_data in data.items():
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

        await interaction.response.send_message("\n".join(lines))


@bot.event
async def on_ready():
    bot.add_view(AttendanceView())
    try:
        synced = await bot.tree.sync()
        print(f"已同步 {len(synced)} 個指令")
    except Exception as e:
        print(e)

    print(f"機器人已登入：{bot.user}")


@bot.tree.command(name="簽到面板", description="建立上班下班簽到面板")
async def attendance_panel(interaction: discord.Interaction):
    await interaction.response.send_message(
        "📌 簽到系統\n\n請選擇要執行的操作：",
        view=AttendanceView()
    )


bot.run(TOKEN)
