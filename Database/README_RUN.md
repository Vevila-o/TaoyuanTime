README — 執行說明（給組員）

系統簡介
本專案為「桃園 AI 智慧活動資訊服務系統」之 POC 版本。
系統目標是整合桃園市政府各局處活動資訊，並透過 LINE Bot 提供活動探索、AI 搜尋、活動推薦、活動提醒與訂閱功能。
目前後端採用 Django + SQLite，並使用固定 Tag 池作為 AI 搜尋與推薦的資料基礎。

以下說明以「組員第一次接手也能看懂」為目標，使用繁體中文。

1) 專案用途
- 本專案為「桃園 AI 智慧活動資訊服務系統」最小可執行版本。
- 提供活動資料庫、爬蟲範例、管理後台、以及供前端/AI 使用的欄位與服務函式。

2) 技術架構
- 後端：Django
- 資料庫：SQLite（db.sqlite3）
- App：`events`
- 爬蟲：位於 `events/crawlers/`（範例爬蟲，不會自動上架活動）

3) 如何安裝（以 Windows PowerShell 為例）
- 建議建立虛擬環境：
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt

4) 如何啟動（前置）
- 確認已安裝 requirements.txt 內套件。
- 若要重新產生資料庫或清理，請參考下方「重新 migrate」與「重新 seed」步驟。

5) 如何重新 migrate
- 刪除現有 db（若要重置）：Remove-Item .\db.sqlite3 -ErrorAction SilentlyContinue
- 產生 migration：python manage.py makemigrations events
- 套用 migration：python manage.py migrate

6) 如何重新 seed
- 執行：python manage.py seed_initial_data

7) 如何啟動 Django server
- 執行：python manage.py runserver
- 管理後台： http://127.0.0.1:8000/admin/

8) 如何查看資料庫（快速檢查）
- 已包含 check_db.py（專案根目錄），可執行檢查：
  C:/.../python.exe check_db.py
  範例輸出：Activity=100, Tag=49, SourceWebsite=13

9) 如何執行 crawler
- 執行：python manage.py crawl_activities
- 會依序執行三個範例爬蟲，並回傳每個來源 created/skipped 統計值

10) 如何匯入正式爬蟲輸出 JSON
- 從本 workspace 根目錄的爬蟲輸出匯入公開活動：
  python manage.py import_crawler_json --input ..\data\output\activities_public.json
- 先檢查、不寫入資料庫：
  python manage.py import_crawler_json --input ..\data\output\activities_public.json --dry-run
- 也可改用推薦池輸出：
  python manage.py import_crawler_json --input ..\data\output\activities_recommendation_ready.json
- 匯入會以 `source_url` 判斷既有資料，已存在則更新，不存在則新增；匯入後會同步固定 Tag 池中的地區、費用與明確活動類型標籤。

11) 專案資料夾說明（重點）
- `events/`：主要 Django app，包含 models、admin、services、crawlers、management commands
- `config/`：Django settings、urls、wsgi
- `db.sqlite3`：SQLite 資料庫（已包含 seed 結果）
- `requirements.txt`：專案依賴
- `schema.sql`：資料表參考 SQL
- `handover_package.md`、`README_DB.md`：交接與資料庫說明

12) 目前資料庫檢查結果（開發者已驗證）
- Activity = 232
- Tag = 49
- SourceWebsite = 17

若你在執行上遇到系統 Python 受管理（PEP 668）限制，請務必在專案資料夾建立虛擬環境並安裝依賴，再執行上面命令。
