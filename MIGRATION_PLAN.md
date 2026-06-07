# TaoyuanTime-intergrate1 功能移植計畫

日期：2026-06-07

## 目標

把 `C:\Users\k9404\Desktop\TaoyuanTime` 已完成的功能移植到本資料夾，並保留原始專案較簡單的骨架。原則是最小化達成功能完整，不再堆疊交付文件、過細診斷報表或長期維運工具。

## 移植策略

- 直接以完成版 `db.sqlite3` 取代 `Database\db.sqlite3`，取得完整 schema 與已整理資料。
- `events` app 維持在 `Database\events`，不在根目錄再新增第二份 `events`。
- `settings.py` 保留 `Database` import path，資料庫位置固定指向 `Database\db.sqlite3`。
- LINE、AI、PUBLIC_BASE_URL 等設定改由 `.env` 或環境變數讀取，不寫死 token。
- 後台 template 與路由保留，但只保主流程：活動管理、任務中心、Tag 審核、推播、使用者、爬蟲、異動、LINE 查詢模擬。

## 已移植功能

### LINE Bot

- Follow 建立/更新 `UserProfile`。
- 偏好設定 Flex，支援活動類型、地區、費用/優惠與推播頻率。
- `推薦活動` / `猜你喜歡` / `今日推薦`。
- DB-grounded 自然語言活動查詢，支援語意擴展與上下文延續。
- `還有嗎`、`換一批`、`中壢的呢`、`免費的呢`。
- 活動卡片、詳細資訊 tracking、Google Maps、Google Calendar。
- 訂閱、取消訂閱、已訂閱活動。
- 非活動問題簡短引導，不做開放式閒聊。

### 資料與推薦

- 正式活動模型 `events.Activity`。
- 固定 Tag 池與使用者偏好。
- `ActivitySearchProfile` 支援自然語言搜尋語意。
- `ActionLog` 記錄卡片、訂閱、導航、行事曆、詳細資訊等互動。
- 推薦排除過期、失效連結與不適合前台的活動。

### 後台

- `/dashboard/`：展示活動、使用者、訂閱、互動、推播與任務概況。
- `/activityList/`：活動列表、搜尋、篩選。
- `/activityList/activityAdd/`、`/activityList/Edit/<id>/`：活動新增與編輯。
- `/tagReview/`：AI Tag 建議審核。
- `/operations/`、`/operations/jobs/`：AI Tag、搜尋語意、OCR、摘要、連結檢查任務。
- `/push`：推播 campaign 建立與發送。
- `/User`、`/User/<id>/`：使用者與互動紀錄。
- `/crawlJobs/`：建立與執行爬蟲任務。
- `/activityChanges/`：活動異動通知紀錄。
- `/lineQuerySimulator/`：後台測 LINE 自然語言查詢。

### 指令

保留必要 command：

```powershell
python manage.py import_crawler_json --input scraping\data\output\activities_all.json --dry-run --activate
python manage.py run_crawler_pipeline --activate --skip-dynamic --primary-limit 20 --secondary-limit 20 --max-runtime 10
python manage.py ai_tag_activities --limit 100 --create-suggestions
python manage.py generate_activity_summaries --limit 100
python manage.py process_activity_ocr --limit 20
python manage.py push_recommendations --dry-run
python manage.py push_activity_reminders --window-hours 24
python manage.py push_activity_change_notifications --dry-run
python manage.py smoke_extreme_line_flow
```

## 不追求的項目

- 不做正式資安、部署硬化或多環境設定。
- 不新增過度抽象或未要求的擴充架構。
- 不保留所有交付文件與歷史備忘錄。
- 不把維修型診斷塞滿後台頁面；只保留能展示與操作主流程的資訊。

## 驗收指令

```powershell
cd C:\Users\k9404\Desktop\TaoyuanTime-intergrate1
python manage.py check
python manage.py makemigrations --check --dry-run
python -m py_compile crawler_main.py Database\events\management\commands\*.py
python manage.py import_crawler_json --input scraping\data\output\activities_all.json --dry-run --activate
python manage.py push_recommendations --dry-run
python manage.py push_activity_change_notifications --dry-run
python manage.py smoke_extreme_line_flow
```

後台 smoke URL：

- `/dashboard/`
- `/operations/`
- `/operations/jobs/`
- `/activityList/`
- `/tagReview/`
- `/push`
- `/User`
- `/crawlJobs/`
- `/activityChanges/`
- `/lineQuerySimulator/`

## 備註

本次移植會保留備份於 `backups\migration_*`。如果後續要精簡，可以優先刪減後台診斷文字與不常用維護按鈕，不要先刪 LINE、推薦、訂閱、tracking、AI/OCR/job 的核心模型與 service。
