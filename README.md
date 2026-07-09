# 直播主打卡 Telegram Bot

## 功能
- 上班打卡
- 下班打卡
- 今日統計
- 本月統計
- 防重複打卡
- 自動計算工時
- Google Sheets 紀錄
- Telegram 群組可用

## Google Sheets 欄位
建立一份 Google 試算表，分頁名稱要叫：

打卡紀錄

第一列欄位：

日期｜主播｜Telegram ID｜上班時間｜下班時間｜工時｜狀態

## Render 環境變數
在 Render 的 Environment 裡新增：

BOT_TOKEN = Telegram Bot Token

SHEET_ID = Google Sheets 網址中 `/d/` 後面那串 ID

GOOGLE_CREDENTIALS_JSON = Google Service Account JSON 整包內容

ADMIN_IDS = 管理員 Telegram ID，多個用逗號分隔。若空白，所有人都能看統計。

TIMEZONE_OFFSET = 8

## Render 設定
Build Command:
pip install -r requirements.txt

Start Command:
python main.py

## Telegram Webhook
Render 部署完成後，取得網址，例如：

https://xxxx.onrender.com

打開瀏覽器：

https://api.telegram.org/bot你的TOKEN/setWebhook?url=https://xxxx.onrender.com/webhook

成功會看到：
{"ok":true,"result":true,"description":"Webhook was set"}

## 使用
在 Telegram 群組輸入：

/start

或指令：
/checkin
/checkout
/today
/month
