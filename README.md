# TaoyuanTime LINE Bot 整合系統

LINE Bot 活動推薦系統，整合 Django 後台、爬蟲 pipeline、AI 標籤/摘要/OCR、自然語言活動查詢、推播與追蹤功能。

參考文件：

- `START_HERE_INTERGRATE1.md` — 啟動與驗收指南

## 檔案架構

```
IMintergrateSys/
├── manage.py                        # Django 入口
├── requirements.txt                 # 套件清單
├── crawler_main.py                  # 爬蟲 CLI 入口（獨立執行）
├── .env.example                     # 環境變數範本
│
├── IMintergrateSys/                 # Django 專案設定
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
│
├── Database/events/                 # 核心 App（資料模型、服務、AI、爬蟲）
│   ├── models.py                    # 所有資料模型（Activity, UserProfile, Tag...）
│   ├── services.py                  # 活動查詢、推薦、訂閱服務
│   ├── ai_providers.py              # AI API 呼叫（OpenAI / 本地模型）
│   ├── ai_tagger.py                 # AI 自動標籤邏輯
│   ├── push_services.py             # 推播服務（推薦、提醒、異動通知）
│   ├── operation_jobs.py            # 後台操作任務（爬蟲、AI 批次）
│   ├── search_profiles.py           # 活動搜尋語意 Profile
│   ├── crawlers/                    # 爬蟲模組（culture, library, tycg）
│   └── management/commands/         # Django 管理指令（ai_tag, push, crawl...）
│
├── myapp/                           # LINE Bot App
│   ├── views.py                     # Webhook 入口、事件分派
│   ├── line_services.py             # LINE 訊息建構、搜尋、推薦邏輯
│   ├── service.py                   # 活動查詢輔助服務
│   └── models.py                    # LINE App 模型（目前空）
│
├── admin_app/                       # 後台管理 App
│   ├── views.py                     # 後台所有頁面 View
│   ├── diagnostics.py               # 活動健康度診斷工具
│   └── models.py                    # legacy Activity model（migration 相容用）
│
├── pipeline/                        # 爬蟲資料處理 Pipeline
│   ├── normalize_text.py            # 文字標準化
│   ├── classify_content.py          # 內容分類
│   ├── extract_dates.py             # 日期提取
│   ├── extract_location.py          # 地點提取
│   ├── extract_fee.py               # 費用提取
│   ├── asset_extractor.py           # 圖片資產提取
│   ├── asset_downloader.py          # 圖片下載
│   ├── ocr_client.py                # OCR 文字辨識
│   ├── quality_score.py             # 活動品質評分
│   ├── line_card_readiness.py       # LINE 卡片適用性檢查
│   ├── ai_readiness.py              # AI 處理適用性檢查
│   ├── dedupe.py                    # 活動去重
│   └── save_json.py / save_sqlite.py
│
├── scrapers/                        # 爬蟲來源模組
│   ├── base_scraper.py              # 爬蟲基底類別
│   ├── tycg.py / culture.py / youth.py / ...
│   ├── travel_openapi.py / travel_taoyuan.py
│   └── scripts/                     # 輔助腳本（health report, OCR...）
│
├── config/                          # 設定檔
│   ├── sources.yaml                 # 爬蟲來源設定
│   ├── districts.yaml               # 地區對應表
│   └── keywords.yaml                # 關鍵字設定
│
├── templates/                       # HTML 模板（後台頁面）
│   ├── dashboard.html
│   ├── activityList.html / activityAdd.html / activityEdit.html
│   ├── operations.html / operationJobs.html
│   ├── crawlJobs.html / crawlJobDetail.html
│   ├── tagReview.html / pushManagement.html
│   ├── userManagement.html / userDetail.html
│   └── lineQuerySimulator.html
│
├── static/                          # 靜態資源
│   ├── css/                         # 各頁面樣式
│   └── img/line/                    # LINE 卡片備用圖片
│
├── scraping/data/                   # 爬蟲輸出資料（已提交，供初始匯入用）
│   └── output/activities_all.json   # 最新完整活動 JSON
│
├── tests/                           # 單元測試
│   └── test_*.py
│
└── Database/db.sqlite3              # SQLite 資料庫（已提交）
```

## 目前狀態

- 可獨立運作，不依賴其他專案目錄。
- Django 專案入口是 `manage.py`。
- 主要 App 放在 `Database/events`，資料庫是 `Database/db.sqlite3`。
- `.env` 只放本機，不提交 Git。
- `.env.example` 是預設雲端 OpenAI API 模式，不預設連本地模型。
- 爬蟲輸出與活動資料保留在 `scraping/data/`，方便換電腦後不用重新爬。
- 活動過期只會從 `active` 下架成 `inactive`，不會刪資料庫活動、訂閱、互動、異動紀錄。
- `scraping/data/output/activities_all.json`、`health_report.json` 這類「最新輸出檔」可能會被下一次爬蟲覆寫；如果要保留每次快照，需要另外手動備份。

## 快速啟動

```powershell
cd C:\LineRobot\IMintergrateSys
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

只要 `LOCAL` 或 `AI_LOCAL_ENABLED` 任一個是 `not` / `false` / `0` / `no` / `off`，或 `AI_BASE_URL` 是空白 / `not`，就會直接跳過本地模型，用 OpenAI 雲端 API。

若要改回本地模型優先：

```env
LOCAL=true
AI_LOCAL_ENABLED=true
AI_BASE_URL=http://100.107.195.9:11434/v1
AI_PROVIDER_ORDER=local,openai
```

`LINE_DISABLE_PROXY=true` 建議保留，避免 LINE SDK 或 AI requests 被系統 proxy 影響。

`AI_MAX_TOKENS=1024` 對 LINE 查詢 JSON、AI tag JSON、短摘要與一般 OCR 已足夠；如果 AI 回傳 JSON 被截斷，再調成 2048 或 4096。

## 主要功能

- 後台活動管理（新增/編輯/上下架）、儀表板、標籤審核、使用者管理、推播 campaign。
- LINE Bot：偏好設定、推薦活動、已訂閱活動、訂閱/取消訂閱、詳細資訊、導航、加入行事曆。
- DB-grounded 自然語言活動查詢，不編造資料庫不存在的活動。
- AI tag / AI summary / OCR，可用本地 OpenAI-compatible API 或 OpenAI fallback。
- 爬蟲 pipeline 與既有活動 JSON 匯入。
- 手動新增活動（後台 `/activityList/activityAdd/`）。
- 活動異動通知、訂閱提醒、推薦推播。

## 管理員日常更新

日常更新只要做這件事：

1. 啟動 Django server。
2. 打開 `http://127.0.0.1:8000/crawlJobs/`。
3. 按「一鍵完整更新」。
4. 到任務詳情確認狀態是 success 或 partial。

「一鍵完整更新」會處理爬蟲、匯入、過期下架、AI Tag、搜尋語意、AI 摘要與 OCR。過期活動只會下架，不會刪除歷史資料或爬蟲保存檔案。

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

完整更新建議走後台 `/crawlJobs/` 的「一鍵完整更新」。若後台只建立 queued job、沒有自動背景程序，可手動跑：

```powershell
python manage.py run_queued_crawl_jobs --limit 1
```

只清掉 dashboard 的「過期仍上架」：

```powershell
python manage.py archive_expired_activities
python manage.py archive_expired_activities --apply
```

任務卡住時，到 `/crawlJobs/` 把 running 任務標記中斷/失敗，再重新建立或重跑 queued job。

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
/activityList/activityAdd/
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
- `/activityList/activityAdd/`
- `/tagReview/`
- `/push`
- `/User`
- `/crawlJobs/`

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
- `Database/db.sqlite3` 會提交，讓換電腦後仍有活動資料可用。
- `scraping/data/` 會提交，避免組員重新爬資料。
- 目前分支：`codex/near-complete-build`。
