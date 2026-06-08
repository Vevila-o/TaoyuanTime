# TaoyuanTime 快完成品交接版

這個資料夾是 `TaoyuanTime-intergrate1` 的獨立可執行版本，已把主專案目前具備的 Django 後台、LINE Bot、活動資料、爬蟲管線、AI tag / summary / OCR、自然語言活動查詢、推播與追蹤功能移植進來。

如果只想啟動與驗收，先看：

- `START_HERE_INTERGRATE1.md`
- `MIGRATION_PLAN.md`

## 目前狀態

- 可獨立運作，不依賴原本 `TaoyuanTime` 專案目錄。
- Django 專案入口是 `manage.py`。
- 主要 App 放在 `Database/events`，資料庫是 `Database/db.sqlite3`。
- `.env` 只放本機，不提交 Git。
- `.env.example` 是預設雲端 OpenAI API 模式，不預設連本地模型。
- 爬蟲輸出與活動資料保留在 `scraping/data/`，方便換電腦後不用重新爬。

## 快速啟動

```powershell
cd C:\Users\k9404\Desktop\TaoyuanTime-intergrate1
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py runserver 0.0.0.0:8000
```

開啟後台：

```text
http://127.0.0.1:8000/dashboard/
```

LINE webhook 預設路徑：

```text
/callback/
```

ngrok 指到本機 8000 時，LINE Developers webhook 填：

```text
https://你的-ngrok-domain/callback/
```

## ENV 重點

請從 `.env.example` 複製成 `.env`，再填自己的 LINE 與 OpenAI 金鑰。

雲端 API 預設模式：

```env
LOCAL=not
AI_LOCAL_ENABLED=not
AI_BASE_URL=
AI_PROVIDER_ORDER=local,openai
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
AI_MAX_TOKENS=1024
```

目前邏輯是：只要 `LOCAL` 或 `AI_LOCAL_ENABLED` 任一個是 `not` / `false` / `0` / `no` / `off`，或 `AI_BASE_URL` 是空白 / `not`，就會直接跳過本地模型，用 OpenAI 雲端 API，不會等本地 timeout。

若要改回本地模型優先：

```env
LOCAL=true
AI_LOCAL_ENABLED=true
AI_BASE_URL=http://100.107.195.9:11434/v1
AI_PROVIDER_ORDER=local,openai
```

`LINE_DISABLE_PROXY=true` 建議保留，避免 LINE SDK 或 AI requests 被系統 proxy 影響。

`AI_MAX_TOKENS=1024` 對 LINE 查詢 JSON、AI tag JSON、短摘要與一般 OCR 已足夠；如果 OCR 文字很長或 AI 回傳 JSON 被截斷，再調成 2048 或 4096。

## 主要功能

- 後台活動管理、儀表板、標籤審核、使用者管理、推播 campaign。
- LINE Bot：偏好設定、推薦活動、已訂閱活動、訂閱/取消訂閱、詳細資訊、導航、加入行事曆。
- DB-grounded 自然語言活動查詢，不編造資料庫不存在的活動。
- AI tag / AI summary / OCR，可用本地 OpenAI-compatible API 或 OpenAI fallback。
- 爬蟲 pipeline 與既有活動 JSON 匯入。
- 活動異動通知、訂閱提醒、推薦推播。

## 常用指令

檢查 Django：

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate
```

匯入既有活動 JSON：

```powershell
python manage.py import_crawler_json --input scraping\data\output\activities_all.json --activate
```

小批次爬蟲測試，不匯入：

```powershell
python manage.py run_crawler_pipeline --no-import --no-assets --skip-dynamic --source travel_openapi --primary-limit 1 --secondary-limit 1 --max-runtime 1
```

正式爬蟲並匯入：

```powershell
python manage.py run_crawler_pipeline --activate --skip-dynamic --primary-limit 20 --secondary-limit 20 --max-runtime 10
```

完整更新建議走後台 `/crawlJobs/` 的「一鍵完整更新」。這條流程會建立 `CrawlJob`，並由既有 queued job 執行：爬蟲、匯入、過期下架、AI Tag、搜尋語意、AI 摘要與 OCR。若後台只建立 queued job、沒有自動背景程序，可手動跑：

```powershell
python manage.py run_queued_crawl_jobs --limit 1
```

只清掉 dashboard 的「過期仍上架」：

```powershell
python manage.py archive_expired_activities
python manage.py archive_expired_activities --apply
```

任務卡住時，到 `/crawlJobs/` 把 running 任務標記中斷/失敗，再重新建立或重跑 queued job。停止目前終端機中的 Django 或爬蟲可按 `Ctrl + C`。

AI 摘要：

```powershell
python manage.py generate_activity_summaries --limit 100
```

AI tag：

```powershell
python manage.py ai_tag_activities --limit 100 --create-suggestions
python manage.py ai_tag_activities --limit 100 --apply --skip-tagged-success
```

推薦推播 dry-run：

```powershell
python manage.py push_recommendations --dry-run
```

訂閱提醒：

```powershell
python manage.py push_activity_reminders --window-hours 24
```

活動異動通知 dry-run：

```powershell
python manage.py push_activity_change_notifications --dry-run
```

## 主要 URL

```text
/dashboard/
/operations/
/operations/jobs/
/activityList/
/tagReview/
/push
/User
/crawlJobs/
/activityChanges/
/callback/
/track/calendar/<activity_id>/
/track/maps/<activity_id>/
```

假 POST `/callback/` 回 403 是正常的，代表 LINE signature 驗證有啟動；真 LINE webhook 簽章正確時才會 200。

## 最小驗收

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py push_recommendations --dry-run
python manage.py push_activity_change_notifications --dry-run
```

後台 smoke：

- `/dashboard/`
- `/operations/`
- `/operations/jobs/`
- `/activityList/`
- `/tagReview/`
- `/push`
- `/User`

LINE 實機至少測：

- `偏好設定`
- `推薦活動`
- `已訂閱活動`
- 詳細資訊
- 導航
- 加入行事曆
- 訂閱 / 取消訂閱

## Git 注意

- `.env` 不提交。
- `Database/db.sqlite3` 會提交，讓這份快完成品換電腦後仍有活動資料可用。
- `scraping/data/` 會提交，避免組員重新爬資料。
- 目前建議分支：`codex/near-complete-build`。
