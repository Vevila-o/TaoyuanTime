# TaoyuanTime-intergrate1 啟動方法

本資料夾已可獨立運作，不需要依賴原本 `TaoyuanTime` 專案。預設資料庫在：

```text
C:\Users\k9404\Desktop\TaoyuanTime-intergrate1\Database\db.sqlite3
```

## 1. 進入專案

```powershell
cd C:\Users\k9404\Desktop\TaoyuanTime-intergrate1
```

## 2. 安裝套件

```powershell
pip install -r requirements.txt
```

如果已經在同一台電腦裝過本專案套件，通常可以略過。

## 3. 環境設定

正式機密設定放在：

```text
C:\Users\k9404\Desktop\TaoyuanTime-intergrate1\.env
```

目前 `.env` 已同步必要 LINE / Django / AI 設定，不放 Gemini / Google API key。不要把 `.env` 提交到 Git。AI 預設給另一台電腦使用雲端直連：`LOCAL=not`、`AI_BASE_URL=`、`AI_PROVIDER_ORDER=local,openai`。程式會因 `LOCAL=not` 直接跳過本地端並使用 OpenAI cloud，不會等待本地端 timeout。若要啟用本地端模型，改成 `LOCAL=true` 並設定 `AI_BASE_URL=http://100.107.195.9:8080/v1`。

範例檔在：

```text
.env.example
```

注意：通常不要設定 `TAOYUANTIME_DB_PATH`，讓系統自動使用本資料夾自己的 `Database\db.sqlite3`。只有要改用其他 DB 時才設定。
建議保留：

```env
LINE_DISABLE_PROXY=true
```

這會在 Django 啟動時清掉系統 proxy 環境變數，避免 LINE SDK、OpenAI API 或本地 AI request 被 Windows/公司/學校 proxy 影響。除非另一台電腦必須透過 proxy 才能連外網，否則維持 `true`。

`AI_MAX_TOKENS=1024` 對目前用途足夠：LINE 查詢計畫、AI Tag JSON、短摘要與一般 OCR JSON 都是短輸出。若未來 OCR 海報文字很多、摘要要更長，或模型常因輸出被截斷造成 JSON parse 失敗，再調高到 `2048` 或 `4096`。

## 4. 基本檢查

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
```

正常狀態應該是：

```text
System check identified no issues
No changes detected
No planned migration operations
```

若 `migrate --plan` 顯示有待套用 migration，執行：

```powershell
python manage.py migrate
```

## 5. 啟動後台

```powershell
python manage.py runserver 127.0.0.1:8000
https://bc0f-211-23-197-194.ngrok-free.app/callback
```

瀏覽器開：

```text
http://127.0.0.1:8000/dashboard/
```

常用後台頁面：

- `http://127.0.0.1:8000/dashboard/`
- `http://127.0.0.1:8000/operations/`
- `http://127.0.0.1:8000/operations/jobs/`
- `http://127.0.0.1:8000/activityList/`
- `http://127.0.0.1:8000/tagReview/`
- `http://127.0.0.1:8000/push`
- `http://127.0.0.1:8000/User`
- `http://127.0.0.1:8000/crawlJobs/`
- `http://127.0.0.1:8000/activityChanges/`
- `http://127.0.0.1:8000/lineQuerySimulator/`

## 6. LINE webhook

本機開 server：

```powershell
python manage.py runserver 0.0.0.0:8000
```

開 ngrok：

```powershell
ngrok http 8000
```

把 ngrok 網址填入 `.env`：

```env
PUBLIC_BASE_URL=https://你的-ngrok-domain.ngrok-free.app
LINE_WEBHOOK_PATH=/callback/
```

LINE Developers webhook URL 設為：

```text
https://你的-ngrok-domain.ngrok-free.app/callback
```

也支援：

- `/callback/`
- `/webhook`
- `/webhook/`

提醒：用瀏覽器或假 POST 打 `/callback` 回 400 或 403 是正常的，真 LINE webhook 需要 LINE signature。

## 7. 管理員日常更新活動

如果你是管理員、不會任何指令，日常更新活動只需要：

1. 確認 Django server 已啟動。
2. 打開 `http://127.0.0.1:8000/crawlJobs/`。
3. 按「一鍵完整更新」或建立完整更新任務。
4. 進任務詳情看進度與結果。

完整更新會做：爬蟲、匯入、過期活動自動下架、OCR、AI repair+tag、安全補欄位、readiness 重算、搜尋語意、AI 摘要與官方連結檢查。它不會定時自己跑；要更新時手動按後台即可。

資料保存原則：

- 過期活動只會從 `active` 改成 `inactive`，不會刪掉活動資料。
- 訂閱、互動、異動紀錄會保留，方便查歷史與追蹤。
- `scraping\data\assets\`、`scraping\data\raw_html\`、`scraping\data\debug_cases\` 目前沒有自動過期刪除機制，除非手動刪，否則會保留。
- `scraping\data\output\activities_all.json`、`health_report.json` 等最新輸出檔會被下一次爬蟲覆寫；這是更新最新狀態，不是清歷史。若要保存每一次爬蟲快照，需另外備份。

## 8. 常用資料與 AI 指令

展示用中原市民卡特約優惠：

```powershell
python manage.py seed_zhongyuan_citizen_stores --apply --skip-checks
```

這會寫入 4 筆固定 `Store` 資料。LINE 使用者傳「附近的市民卡特約商店」時，會直接收到這 4 張優惠卡片，不需要分享位置。

匯入既有 JSON dry-run：

```powershell
python manage.py import_crawler_json --input scraping\data\output\activities_all.json --dry-run --activate
```

正式匯入既有 JSON：

```powershell
python manage.py import_crawler_json --input scraping\data\output\activities_all.json --activate
```

小批次爬蟲，不匯入：

```powershell
python manage.py run_crawler_pipeline --no-import --no-assets --skip-dynamic --source travel_openapi --primary-limit 1 --secondary-limit 1 --max-runtime 1
```

正式爬蟲並匯入：

```powershell
python manage.py run_crawler_pipeline --activate --skip-dynamic --primary-limit 20 --secondary-limit 20 --max-runtime 10
```

完整更新建議優先走後台：

1. 開 `http://127.0.0.1:8000/crawlJobs/`
2. 使用「一鍵完整更新」或建立爬蟲任務
3. 若任務只進 queued、沒有自動開始，執行：

```powershell
python manage.py run_queued_crawl_jobs --limit 1
```

完整更新流程會做：爬蟲、匯入、過期活動自動下架、OCR、AI repair+tag、安全補欄位、readiness 重算、搜尋語意、AI 摘要與官方連結檢查。它不會定時自己跑；需要你手動按後台或手動執行 command。

缺漏補救原則：

- OCR 先跑，讓海報文字可以進入後續 AI repair+tag 的上下文。
- AI repair+tag 不只上標籤，也會嘗試補活動日期、地點、地區、報名資訊、報名網址與費用類型。
- 自動補欄位只補空欄位，不覆蓋既有值；人工確認要覆蓋時，從後台編輯或用專案指令處理。
- 後台完整更新會優先處理 active、未排除、未過期、且有缺漏欄位的活動；已經直接爬到完整資料的活動不會被重複 repair。
- 官方連結檢查會把 HTTP 404/410 等失效活動標成 `dead_official_link` 並排除公開推薦；若之後修正官方連結，再跑檢查可清掉這個系統排除原因。

只建立/處理 queued job 的情況：

```powershell
python manage.py run_queued_crawl_jobs --limit 1
```

如果知道特定 job id：

```powershell
python manage.py run_queued_crawl_jobs --job-id <job_id>
```

只想清掉 dashboard 的「過期仍上架」：

```powershell
python manage.py archive_expired_activities
```

## 9. LINE AI 對話測試重點

測試活動對話時，不要只看第幾輪，要看本句是否切換狀態。

必測案例：

```text
幫我找中原的活動
中壢的
幫我找活動
```

正確行為：最後一句是泛用重新搜尋或一般推薦，不應沿用中原 / 中壢，不應把 `last_query` 串成「幫我找中原的活動，中壢的，幫我找活動」。

```text
上一輪看到：中原文創園區《即刻救原3-珍綜再見》
書法展在幹嘛
```

正確行為：`書法展` 是新主體，不能因為有「在幹嘛」就追問上一輪卡片；搜尋結果應以書法展核心詞過濾，避免舊卡片混入。

仍應維持的追問案例：

- `這個活動在幹嘛`
- `第二個在哪裡`
- `免費嗎`
- `要買票嗎`
- `還有嗎`

相關驗證：

```powershell
python manage.py test tests.test_line_semantic_query
python manage.py test tests
python manage.py check
```

先確認 dry-run 列表沒問題，再執行：

```powershell
python manage.py archive_expired_activities --apply
```

低成本更新，只跑爬蟲匯入、不跑圖片資產：

```powershell
python manage.py run_crawler_pipeline --activate --skip-dynamic --no-assets --primary-limit 50 --secondary-limit 50 --max-runtime 15
```

資料已經有 JSON，只重新匯入：

```powershell
python manage.py import_crawler_json --input scraping\data\output\activities_all.json --activate
```

任務卡住處理：

- 先看 `/crawlJobs/` 是否有 running 很久的任務。
- 如果電腦關機、Django server 被停止、網路斷線或 SQLite locked，running 任務不會自己恢復。
- 在 `/crawlJobs/` 把該任務標記中斷/失敗後，再重新建立任務或執行 `python manage.py run_queued_crawl_jobs --limit 1`。
- 若是在終端機手動跑爬蟲，按 `Ctrl + C` 可停止目前程序。

AI 摘要：

```powershell
python manage.py generate_activity_summaries --limit 100
python manage.py generate_activity_summaries --force --limit 100
```

AI Tag：

```powershell
python manage.py ai_tag_activities --limit 100 --create-suggestions
python manage.py ai_tag_activities --limit 100 --apply --skip-tagged-success
```

OCR：

```powershell
python manage.py process_activity_ocr --limit 20
```

## 10. 推播與提醒

推薦推播 dry-run：

```powershell
python manage.py push_recommendations --dry-run
```

正式推薦推播：

```powershell
python manage.py push_recommendations
```

訂閱提醒：

```powershell
python manage.py push_activity_reminders --window-hours 24
```

活動異動通知 dry-run：

```powershell
python manage.py push_activity_change_notifications --dry-run
```

正式活動異動通知：

```powershell
python manage.py push_activity_change_notifications
```

## 11. 驗收 smoke

LINE 自然語言與 tracking 回歸：

```powershell
python manage.py smoke_extreme_line_flow
```

市民卡特約優惠最小驗收：

```powershell
python manage.py seed_zhongyuan_citizen_stores --apply --skip-checks
python manage.py shell -c "from events.models import Store; print(Store.objects.filter(district='中壢').count())"
```

主要頁面 smoke 可用 Django test client：

```powershell
python manage.py shell -c "from django.test import Client; c=Client(); urls=['/dashboard/','/operations/','/operations/jobs/','/activityList/','/tagReview/','/push','/User','/crawlJobs/','/activityChanges/','/lineQuerySimulator/']; [print(u, c.get(u).status_code) for u in urls]"
```

## 12. 注意事項

- `.env` 不提交。
- `Database\db.sqlite3` 是本資料夾獨立 DB。
- `scraping\data\output\activities_all.json` 是匯入資料來源之一。
- LINE 沒反應時，先看 Django server 是否收到 `/callback`，再看 ngrok 與 LINE Developers webhook URL。
- 改 ngrok domain 後，要同步更新 `.env` 的 `PUBLIC_BASE_URL` 與 LINE Developers webhook URL。
- AI 服務選擇規則：`LOCAL=not/false/0/no/off` 或 `AI_BASE_URL` 空白/`not` 時，直接使用 OpenAI cloud；`LOCAL=true` 且 `AI_BASE_URL` 有值時，才會先試本地端再 fallback。AI 對話、AI Tag、AI 摘要與 OCR 都共用這套規則。
