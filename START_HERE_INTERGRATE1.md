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

## 7. 常用資料與 AI 指令

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

## 8. 推播與提醒

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

## 9. 驗收 smoke

LINE 自然語言與 tracking 回歸：

```powershell
python manage.py smoke_extreme_line_flow
```

主要頁面 smoke 可用 Django test client：

```powershell
python manage.py shell -c "from django.test import Client; c=Client(); urls=['/dashboard/','/operations/','/operations/jobs/','/activityList/','/tagReview/','/push','/User','/crawlJobs/','/activityChanges/','/lineQuerySimulator/']; [print(u, c.get(u).status_code) for u in urls]"
```

## 10. 注意事項

- `.env` 不提交。
- `Database\db.sqlite3` 是本資料夾獨立 DB。
- `scraping\data\output\activities_all.json` 是匯入資料來源之一。
- LINE 沒反應時，先看 Django server 是否收到 `/callback`，再看 ngrok 與 LINE Developers webhook URL。
- 改 ngrok domain 後，要同步更新 `.env` 的 `PUBLIC_BASE_URL` 與 LINE Developers webhook URL。
- AI 服務選擇規則：`LOCAL=not/false/0/no/off` 或 `AI_BASE_URL` 空白/`not` 時，直接使用 OpenAI cloud；`LOCAL=true` 且 `AI_BASE_URL` 有值時，才會先試本地端再 fallback。AI 對話、AI Tag、AI 摘要與 OCR 都共用這套規則。



