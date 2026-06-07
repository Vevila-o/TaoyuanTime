# TaoyuanTime 與 Database 融合操作報告

日期：2026-05-27  
工作目錄：`C:\Users\k9404\Desktop\scraping`  
主要 commit：

- `e138f28 chore: snapshot before database integration`
- `15a5991 feat: import crawler data into shared activity database`

## 1. 本次融合目標

本次融合的核心目標是把組員提供的兩份資料整合成可以共同運作的 MVP：

1. `TaoyuanTime-main/TaoyuanTime-main/`
   - 角色：後台管理系統骨架。
   - 原本有登入、儀表板、活動管理、推播管理、使用者管理等頁面。
   - 但活動列表、新增、編輯頁面大多仍是靜態 HTML 或未接資料庫。

2. `Database/`
   - 角色：正式活動資料庫與 Django `events` app。
   - 包含較完整的 `Activity`、`Tag`、`SourceWebsite`、`UserProfile`、`Subscription`、`ActionLog`。
   - 欄位能支援爬蟲匯入、LINE 卡片、AI 搜尋、推薦、品質分層。

3. `data/output/activities_public.json`
   - 角色：現有爬蟲產出的可公開活動資料。
   - 本次已把這份 JSON 匯入 `Database.events.Activity`。

整合策略：

- 以 `Database.events.Activity` 作為正式活動資料表。
- `TaoyuanTime-main` 不再用自己原本的簡化 `admin_app.Activtiy` 作為主要活動資料來源。
- 讓 `TaoyuanTime-main` 的活動管理頁讀取 `Database/db.sqlite3` 裡的 `events_activity`。

## 2. 為什麼不用 TaoyuanTime 原本的 `admin_app.Activtiy`

`TaoyuanTime-main` 原本的 model 位於：

`TaoyuanTime-main/TaoyuanTime-main/admin_app/models.py`

原本 class 名稱是：

```python
class Activtiy(models.Model):
```

注意：這裡拼字是 `Activtiy`，不是 `Activity`。

原本欄位只有：

- `title`
- `description`
- `location`
- `start_date`
- `end_date`
- `status`
- `created_at`
- `updated_at`

這個資料表只適合非常簡單的活動管理，不足以支援目前專題需要的功能：

- 無法保存來源網站。
- 無法保存官方詳情頁。
- 無法保存圖片 URL。
- 無法保存地區欄位。
- 無法保存費用狀態。
- 無法保存是否需報名。
- 無法保存 AI 摘要與 AI 信心分數。
- 無法保存推薦旗標。
- 無法保存 LINE-ready 狀態。
- 無法保存資料品質分數與警告。
- 無法保存固定 Tag 池關聯。

因此本次融合選擇 `Database.events.Activity` 作為正式活動資料表。

## 3. 融合前資料狀態

融合前我先檢查兩個專案與資料庫：

### 3.1 `TaoyuanTime-main`

主要發現：

- `admin_app.views.activityList()` 只做 `render()`。
- `activityList.html` 表格裡是靜態假資料，例如 `活動1`。
- `TaoyuanTime-main/TaoyuanTime-main/db.sqlite3` 裡有 `admin_app_activtiy` 表。
- `admin_app_activtiy` 當時是 0 筆。
- Django `python manage.py check` 通過。

### 3.2 `Database`

主要發現：

- `Database/events/models.py` 有完整的 `events.Activity`。
- `Database/events/services.py` 已經有推薦、搜尋、LINE payload 等 service。
- `Database/events/admin.py` 已經把 `Activity`、`Tag`、`SourceWebsite` 等註冊到 Django Admin。
- `Database/db.sqlite3` 當時有：
  - `Activity = 210`
  - `Tag = 49`
  - `SourceWebsite = 13`
  - `UserProfile = 1`
- Django `python manage.py check` 通過。

### 3.3 現有爬蟲輸出

主要輸出位於：

`data/output/activities_public.json`

這份 JSON 當時有 22 筆可公開活動資料，欄位包含：

- `source_name`
- `source_key`
- `source_url`
- `title`
- `official_detail_url`
- `status`
- `item_type`
- `is_activity`
- `is_public_item`
- `date_start`
- `date_end`
- `location`
- `district`
- `description`
- `raw_content`
- `fee_type`
- `is_free`
- `poster_url`
- `quality_score`
- `quality_level`
- `line_ready`
- `ai_ready`
- `recommendation_ready`

這份資料比 `TaoyuanTime-main` 原本的活動表完整很多，因此適合匯入 `Database.events.Activity`。

## 4. 快照 commit

依照你的要求，我在開始融合前先建立快照。

執行流程：

```powershell
git status --short
git add -A
git commit -m "chore: snapshot before database integration"
```

過程中第一次 `git add -A` 被 `.git/index.lock` 權限限制擋下，因此改用升權方式執行。

建立 commit：

```text
e138f28 chore: snapshot before database integration
```

這個 commit 的用途是保存融合前完整狀態，方便日後如果融合方向有問題，可以回頭比較。

## 5. 新增 JSON 匯入指令

新增檔案：

`Database/events/management/commands/import_crawler_json.py`

用途：

把現有爬蟲輸出的 JSON 匯入 `Database.events.Activity`。

### 5.1 使用方式

實際匯入：

```powershell
cd C:\Users\k9404\Desktop\scraping\Database
python manage.py import_crawler_json --input ..\data\output\activities_public.json
```

只檢查，不寫入：

```powershell
python manage.py import_crawler_json --input ..\data\output\activities_public.json --dry-run
```

也可以匯入推薦池輸出：

```powershell
python manage.py import_crawler_json --input ..\data\output\activities_recommendation_ready.json
```

### 5.2 匯入策略

匯入時以 `source_url` 作為判斷依據：

- 如果 `source_url` 不存在於 `events_activity`，就新增。
- 如果 `source_url` 已存在，就更新該筆活動。
- 如果該筆資料沒有 `source_url` 或 `official_detail_url`，就略過。

這樣重跑匯入指令時不會重複新增資料。

### 5.3 欄位映射

爬蟲 JSON 與 Django model 欄位不完全同名，因此新增了 mapping。

主要映射如下：

| JSON 欄位 | 匯入到 `Activity` 欄位 |
|---|---|
| `title` | `title` |
| `clean_description` / `description` | `description` |
| `raw_content` | `raw_content` |
| `source_name` | `source_agency` |
| `source_url` | `source_url` |
| `official_detail_url` | `official_detail_url` |
| `location` / `location_text` | `location` |
| `district` | `district` |
| `date_start` / `start_date` | `start_date` |
| `date_end` / `end_date` | `end_date` |
| `poster_url` / `image_url` | `image_url` |
| `fee_text` / `fee_description` | `fee_description` |
| `fee_type` | `fee_type` |
| `is_free` | `is_free` |
| `registration_method` / `registration_url` | `registration_info` |
| `status` | `status` |
| `item_type` / `content_type` | `item_type` |
| `is_activity` | `is_activity` |
| `is_public_item` | `is_public_item` |
| `line_ready` / `line_card_ready` | `line_ready` |
| `ai_ready` | `ai_ready` |
| `recommendation_ready` | `recommendation_ready` |
| `source_key` | `source_key` |
| `quality_score` | `quality_score` |
| `quality_level` | `quality_level` |
| `quality_warnings` | `quality_warnings` |
| `exclude_from_recommendation_reason` | `exclude_from_recommendation_reason` |

### 5.4 日期處理

新增 `parse_event_datetime()`：

- 可處理 `datetime`。
- 可處理 ISO datetime 字串。
- 可處理只有日期的字串，例如 `2026-06-07`。
- 如果是開始日期，補成當天 `00:00:00`。
- 如果是結束日期，補成當天 `23:59:59.999999`。
- 若 datetime 是 naive，會套用 Django 目前 timezone。

這樣能避免只有日期的活動被匯入成空值。

### 5.5 品質等級處理

爬蟲 pipeline 裡的 `quality_level` 有可能是：

- `usable`
- `ready`

但 `Database.events.Activity` 原本只接受：

- `high`
- `medium`
- `low`
- `rejected`

因此匯入時做了保守轉換：

- `usable` / `ready` 轉成 `high`
- 分數大於等於 85 轉成 `high`
- 分數大於等於 60 轉成 `medium`
- 其餘轉成 `low`
- 無法判斷時預設 `medium`

### 5.6 Tag 推斷

匯入時會使用既有固定 Tag 池，不會新增任意 tag。

推斷規則：

1. 如果 JSON 有 `tags`，只接受已存在於 `Tag` 表的 tag。
2. 如果 `district` 對得上 `region` tag，加入地區 tag。
3. 如果有報名資訊，加入 `需報名` tag。
4. 根據 `fee_type` / `is_free` 加入：
   - `免費`
   - `付費`
   - `金額未提供`
5. 如果標題或描述中明確出現活動類型 tag 名稱，例如 `展覽`、`市集`、`音樂`，就加入該活動類型 tag。

這裡刻意只做保守推斷，避免 AI 或程式亂產生分類。

## 6. 補上 `ticket_free` fee type

爬蟲資料中有一種費用類型：

```text
ticket_free
```

意思比較接近「免費但需索票」或「票券免費」。

原本 `Activity.FEE_TYPE_CHOICES` 只有：

```python
('free', 'free')
('paid', 'paid')
('unknown', 'unknown')
```

這會造成資料值和 model choices 不一致。

因此修改：

`Database/events/models.py`

加入：

```python
('ticket_free', 'ticket_free')
```

並把欄位長度從：

```python
max_length=10
```

改成：

```python
max_length=16
```

新增 migration：

`Database/events/migrations/0003_activity_ticket_free.py`

套用 migration：

```powershell
cd C:\Users\k9404\Desktop\scraping\Database
python manage.py migrate
```

結果：

```text
Applying events.0003_activity_ticket_free... OK
```

## 7. 實際匯入爬蟲資料

先 dry-run：

```powershell
python manage.py import_crawler_json --input ..\data\output\activities_public.json --dry-run
```

結果：

```text
DRY RUN: total=22, created=22, updated=0, skipped=0
```

實際匯入：

```powershell
python manage.py import_crawler_json --input ..\data\output\activities_public.json
```

結果：

```text
IMPORTED: total=22, created=22, updated=0, skipped=0
```

匯入後資料庫狀態：

```text
Activity = 232
SourceWebsite = 17
```

再次 dry-run 驗證可重跑：

```text
DRY RUN: total=22, created=0, updated=22, skipped=0
```

代表匯入指令具備 idempotent 特性：重跑不會重複新增 22 筆，而是更新已存在資料。

## 8. 讓 TaoyuanTime 使用 Database 的正式資料庫

修改檔案：

`TaoyuanTime-main/TaoyuanTime-main/IMintergrateSys/settings.py`

### 8.1 加入 `Database/` 到 Python path

新增：

```python
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = BASE_DIR.parent.parent
DATABASE_PROJECT_DIR = WORKSPACE_DIR / 'Database'

if DATABASE_PROJECT_DIR.exists():
    sys.path.insert(0, str(DATABASE_PROJECT_DIR))
```

目的：

讓 `TaoyuanTime-main` 可以 import `Database/events` 這個 Django app。

### 8.2 加入 `events` app

在 `INSTALLED_APPS` 加入：

```python
'events',
```

目的：

讓 TaoyuanTime 的 Django 專案能使用 `events.Activity` model。

### 8.3 共用 `Database/db.sqlite3`

原本：

```python
'NAME': BASE_DIR / 'db.sqlite3'
```

改成：

```python
'NAME': DATABASE_PROJECT_DIR / 'db.sqlite3'
```

目的：

讓 TaoyuanTime 後台與 Database 專案使用同一個 SQLite 資料庫。

目前共用資料庫位置：

```text
C:\Users\k9404\Desktop\scraping\Database\db.sqlite3
```

## 9. 套用 TaoyuanTime 的 `admin_app` migration

因為 TaoyuanTime 改用 `Database/db.sqlite3`，所以共用 DB 內也需要記錄 `admin_app` 的 migration 狀態。

執行：

```powershell
cd C:\Users\k9404\Desktop\scraping\TaoyuanTime-main\TaoyuanTime-main
python manage.py migrate admin_app
```

第一次遇到：

```text
attempt to write a readonly database
```

原因：

- TaoyuanTime 專案工作目錄在 `TaoyuanTime-main/TaoyuanTime-main`
- 但 DB 被改到 sibling 目錄 `Database/db.sqlite3`
- sandbox 對跨目錄 SQLite 寫入較保守

處理：

- 使用升權重跑同一個 migration。

結果：

```text
Applying admin_app.0001_initial... OK
```

注意：

這個 migration 只是讓 `admin_app` 的舊表在共用 DB 中有 migration 紀錄，不代表我們改回使用 `admin_app_activtiy`。正式活動資料仍然是 `events_activity`。

## 10. 修改活動列表讀 `events.Activity`

修改檔案：

`TaoyuanTime-main/TaoyuanTime-main/admin_app/views.py`

### 10.1 原本

```python
def activityList(request):
  return render(request, 'activityList.html')
```

原本只 render HTML，不查資料。

### 10.2 修改後

新增：

```python
from events.models import Activity
```

活動列表查詢：

```python
activities = Activity.objects.select_related('source_website').order_by('-start_date', '-created_at')
```

支援三個 query string：

- `q`：活動名稱搜尋
- `status`：狀態篩選
- `district`：地區篩選

篩選規則：

```python
if keyword:
  activities = activities.filter(title__icontains=keyword)
if status != 'all':
  activities = activities.filter(status=status)
if district != 'all':
  activities = activities.filter(district=district)
```

地區下拉選單來源：

```python
districts = (
  Activity.objects
  .exclude(district='')
  .values_list('district', flat=True)
  .distinct()
  .order_by('district')
)
```

目前限制最多顯示 100 筆：

```python
'activities': activities[:100]
```

這是 MVP 的保守做法，避免一次渲染太多資料。

## 11. 修改活動列表模板

修改檔案：

`TaoyuanTime-main/TaoyuanTime-main/templates/activityList.html`

### 11.1 搜尋列

原本搜尋列只是靜態 input/select。

修改後變成 GET form：

```html
<form class="filter-bar" method="get">
```

活動名稱搜尋：

```html
<input type="text" class='filter-input' name="q" value="{{ selected_keyword }}" placeholder='搜尋活動名稱...'>
```

狀態篩選：

```html
<select name="status" class="filter-select" onchange="this.form.submit()">
```

地區篩選：

```html
<select name="district" class="filter-select" onchange="this.form.submit()">
```

### 11.2 表格資料

原本假資料：

```text
活動1
中壢區
2026/05/27
```

改成 Django template loop：

```django
{% for activity in activities %}
```

活動名稱：

- 如果有 `source_url`，顯示成可點連結。
- 如果沒有 `source_url`，顯示純文字。

日期：

```django
{{ activity.start_date|date:"Y/m/d H:i"|default:"-" }}
{{ activity.end_date|date:"Y/m/d H:i"|default:"-" }}
```

狀態：

- `active` 顯示「上架中」
- `inactive` 顯示「已下架」
- 其他顯示「草稿」

無資料時顯示：

```text
目前沒有符合條件的活動
```

## 12. 驗證結果

### 12.1 Database check

執行：

```powershell
cd C:\Users\k9404\Desktop\scraping\Database
python manage.py check
```

結果：

```text
System check identified no issues (0 silenced).
```

### 12.2 TaoyuanTime check

執行：

```powershell
cd C:\Users\k9404\Desktop\scraping\TaoyuanTime-main\TaoyuanTime-main
python manage.py check
```

結果：

```text
System check identified no issues (0 silenced).
```

### 12.3 活動列表頁測試

使用 Django test client 測 `/activityList/`：

結果：

```text
200
```

並確認：

- 頁面包含正式活動名稱，例如 `大溪圖書館閱讀講座`
- 頁面不再包含舊假資料 `活動1`

### 12.4 本機 server

本機開發服務曾啟動在：

```text
http://127.0.0.1:8001/activityList/
```

測試結果：

```text
HTTP 200
```

你提供的截圖中，活動管理頁已顯示正式活動資料列，這代表 TaoyuanTime 後台已成功讀到 `Database.events.Activity`。

## 13. 本次 commit 內容

融合實作 commit：

```text
15a5991 feat: import crawler data into shared activity database
```

包含 8 個檔案：

1. `Database/README_RUN.md`
   - 補上 JSON 匯入指令說明。
   - 更新資料庫檢查數字。

2. `Database/db.sqlite3`
   - 實際匯入 22 筆爬蟲活動。
   - 套用 `events.0003` migration。
   - 套用 `admin_app.0001` migration。

3. `Database/events/management/commands/import_crawler_json.py`
   - 新增 JSON 匯入 command。

4. `Database/events/migrations/0003_activity_ticket_free.py`
   - 新增 `ticket_free` fee type migration。

5. `Database/events/models.py`
   - `fee_type` 增加 `ticket_free`。
   - `fee_type.max_length` 從 10 改為 16。

6. `TaoyuanTime-main/TaoyuanTime-main/IMintergrateSys/settings.py`
   - 加入 `Database/` import path。
   - 加入 `events` app。
   - DB 改指向 `Database/db.sqlite3`。

7. `TaoyuanTime-main/TaoyuanTime-main/admin_app/views.py`
   - 活動列表改讀 `events.Activity`。
   - 加入搜尋、狀態、地區篩選。

8. `TaoyuanTime-main/TaoyuanTime-main/templates/activityList.html`
   - 活動列表改成動態資料。
   - 移除假資料。
   - 加入篩選 form。

## 14. 目前工作樹注意事項

融合 commit 後，工作樹只剩下兩個未追蹤 log：

```text
TaoyuanTime-main/TaoyuanTime-main/server.err.log
TaoyuanTime-main/TaoyuanTime-main/server.log
```

原因：

- 本機 Django server 正在使用這兩個 log。
- 它們沒有被納入 commit。
- 如果 server 停掉後可以刪除。

## 15. 組員設計的資料庫是否有缺漏

結論：

`Database` 的設計對大學生專題 MVP 來說已經夠用，而且比 TaoyuanTime 原本的 `admin_app.Activtiy` 完整很多。不過如果要支援正式 LINE 推薦、AI 搜尋、後台審核、推播排程與長期維運，目前仍有一些缺漏。

下面依嚴重程度整理。

## 16. 高優先缺漏

### 16.1 `Activity.source_url` 沒有資料庫唯一約束

目前 importer 用這段避免重複：

```python
Activity.objects.filter(source_url=source_url).first()
```

問題：

- 這只是應用層檢查。
- 資料庫本身沒有 `unique=True`。
- 如果未來多人同時匯入、或兩個 process 同時跑，有機會重複新增。

建議：

```python
source_url = models.URLField(max_length=1000, blank=True, unique=True)
```

或更穩健：

新增唯一鍵：

```text
source_key + external_id
```

因為有些來源 URL 可能改版，但官方 ID 不變。

### 16.2 缺少來源端原始 ID

目前有：

- `source_key`
- `source_url`
- `official_detail_url`

但缺少：

- `external_id`
- `source_item_id`
- `api_id`

問題：

- 例如桃園觀光 OpenAPI 可能有活動 ID。
- URL 改版時，無法穩定追蹤同一活動。
- 去重只能依賴 URL。

建議新增：

```python
external_id = models.CharField(max_length=100, blank=True)
```

並建立：

```text
unique(source_key, external_id)
```

### 16.3 缺少 `scraped_at`、`content_hash`、`last_seen_at`

目前 `Activity` 有：

- `created_at`
- `updated_at`

但這些是資料庫寫入時間，不是爬蟲語意時間。

缺少：

- `scraped_at`：本次爬到這筆資料的時間。
- `first_seen_at`：第一次看見此活動。
- `last_seen_at`：最後一次看見此活動。
- `content_hash`：內容是否變更。

問題：

- 不知道資料是否過時。
- 無法判斷官方頁是否已消失。
- 無法追蹤活動內容是否被官方修改。
- 無法做增量更新報表。

建議：

```python
scraped_at = models.DateTimeField(null=True, blank=True)
first_seen_at = models.DateTimeField(null=True, blank=True)
last_seen_at = models.DateTimeField(null=True, blank=True)
content_hash = models.CharField(max_length=64, blank=True)
```

### 16.4 缺少匯入批次表

目前沒有紀錄每次匯入任務。

缺少類似：

```text
CrawlerRun / ImportRun
```

應記錄：

- run_id
- input file
- started_at
- finished_at
- total items
- created count
- updated count
- skipped count
- failed count
- error message

問題：

- 組員不知道某次匯入是否成功。
- 無法回查哪批資料造成問題。
- 無法在後台顯示爬蟲狀態。

建議新增：

```python
class ImportRun(models.Model):
    run_id = models.CharField(max_length=64, unique=True)
    input_path = models.CharField(max_length=500)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    total_items = models.IntegerField(default=0)
    created_count = models.IntegerField(default=0)
    updated_count = models.IntegerField(default=0)
    skipped_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    status = models.CharField(max_length=32)
    error_message = models.TextField(blank=True)
```

### 16.5 缺少正式推播 Campaign / PushLog 表

現在有 `Subscription` 和 `ActionLog`，但沒有真正的推播管理資料表。

目前推播頁面是靜態 UI，資料庫沒有：

- 推播標題
- 推播內容
- 推播類型
- 預定發送時間
- 發送狀態
- 成功數
- 失敗數
- 目標使用者條件
- 對應活動
- LINE API response

建議新增：

```python
class PushCampaign(models.Model):
    title = models.CharField(max_length=200)
    message = models.TextField()
    activity = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.SET_NULL)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=32, default="draft")
    target_rule = models.JSONField(blank=True, null=True)
    success_count = models.IntegerField(default=0)
    failure_count = models.IntegerField(default=0)
```

以及：

```python
class PushDeliveryLog(models.Model):
    campaign = models.ForeignKey(PushCampaign, on_delete=models.CASCADE)
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    status = models.CharField(max_length=32)
    response = models.JSONField(blank=True, null=True)
    sent_at = models.DateTimeField(null=True, blank=True)
```

## 17. 中優先缺漏

### 17.1 `image_url` 長度可能不足

目前：

```python
image_url = models.URLField(blank=True)
```

Django `URLField` 預設 `max_length=200`。

目前匯入資料的圖片 URL 不長，所以沒問題。但未來官方 CDN、代理圖片、含 query string 的圖片 URL 很容易超過 200。

建議：

```python
image_url = models.URLField(max_length=1000, blank=True)
```

同理：

`SourceWebsite.url` 目前也只有預設長度，建議設為 1000 或 500。

### 17.2 缺少活動圖片/附件表

目前 `Activity` 只有單一 `image_url`。

但爬蟲 pipeline 其實可能抓到多張圖片或附件。正式活動常見：

- 主視覺
- 內文圖片
- PDF 簡章
- 報名附件
- 海報不同尺寸

建議新增：

```python
class ActivityAsset(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="assets")
    asset_url = models.URLField(max_length=1000)
    local_path = models.CharField(max_length=500, blank=True)
    asset_type = models.CharField(max_length=32)
    is_primary = models.BooleanField(default=False)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
```

### 17.3 地區是自由文字，沒有行政區正規化

目前：

```python
district = models.CharField(max_length=100, blank=True)
```

問題：

- 可能出現 `桃園`、`桃園區`、`桃園市桃園區` 三種寫法。
- 搜尋與推薦容易不穩。
- 統計圖會分裂。

建議：

- 建立 `District` 表，或至少建立 choices。
- 匯入時統一存 `桃園` 或 `桃園區`，不要混用。

### 17.4 `is_free` 與 `fee_type` 有語意重疊

目前同時有：

```python
is_free = models.BooleanField(default=False)
fee_type = models.CharField(...)
```

問題：

- `is_free=False` 可能代表「付費」，也可能代表「未知」。
- `ticket_free` 這種情境很難用 boolean 表達。

目前雖然有 `fee_type` 補足，但日後程式可能誤用 `is_free`。

建議：

- 主要判斷用 `fee_type`。
- `is_free` 只當前端快速顯示欄位。
- 或新增文件明確規定：
  - `fee_type=unknown` 時不要只看 `is_free=False` 就判定付費。

### 17.5 缺少報名截止日、報名 URL、名額欄位

目前有：

- `requires_registration`
- `registration_info`

但缺少結構化欄位：

- `registration_url`
- `registration_start_at`
- `registration_end_at`
- `capacity`
- `remaining_capacity`

問題：

- LINE 卡片無法清楚顯示「立即報名」。
- AI 很難回答「哪些活動還能報名」。
- 推薦系統可能推薦已截止報名的活動。

建議新增上述欄位。

### 17.6 缺少主辦單位結構化欄位

目前有：

- `source_agency`
- `source_website`

但主辦單位、協辦單位、承辦單位可能不同。

建議：

```python
organizer = models.CharField(max_length=200, blank=True)
co_organizer = models.CharField(max_length=300, blank=True)
contact_name = models.CharField(max_length=100, blank=True)
contact_phone = models.CharField(max_length=100, blank=True)
```

### 17.7 缺少活動地理座標

目前只有：

- `location`
- `district`

缺少：

- `latitude`
- `longitude`

問題：

- 無法做附近活動推薦。
- 無法串 Google Maps / LINE location bubble。
- 無法做距離排序。

建議新增：

```python
latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
```

### 17.8 缺少多場次設計

現在 `Activity` 只有一組：

- `start_date`
- `end_date`

但實際活動可能有多場次，例如：

- 每週六都有一場
- 一天三個時段
- 展覽期間內有多個導覽場

建議新增：

```python
class ActivitySession(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="sessions")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    capacity = models.IntegerField(null=True, blank=True)
```

## 18. 低優先但建議補強

### 18.1 缺少後台審核歷程

目前 `status` 可以表示：

- `draft`
- `active`
- `inactive`

但沒有記錄：

- 誰上架
- 誰下架
- 何時審核
- 審核意見

建議新增：

```python
reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
reviewed_at = models.DateTimeField(null=True, blank=True)
review_note = models.TextField(blank=True)
```

或建立 `ActivityReviewLog`。

### 18.2 缺少資料版本紀錄

如果官方活動內容變更，目前會直接覆蓋。

問題：

- 無法知道哪裡被改過。
- 若 AI 摘要已產生，無法判斷是否需要重算。

建議新增：

- `ActivityRevision`
- 或至少保存 `content_hash`。

### 18.3 缺少 AI 產出紀錄

目前 `Activity` 有：

- `ai_summary`
- `ai_confidence`

但缺少：

- 使用哪個模型
- prompt 版本
- 生成時間
- AI 原始輸出
- 人工是否確認

建議新增：

```python
class AISummaryLog(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE)
    model_name = models.CharField(max_length=100)
    prompt_version = models.CharField(max_length=50)
    output = models.TextField()
    confidence = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

### 18.4 `ActionLog` 缺少 session/client context

目前 `ActionLog` 有：

- user
- activity
- action_type
- metadata
- created_at

MVP 可用，但若要分析使用行為，建議補：

- client type
- message id
- session id
- source page
- recommendation batch id

### 18.5 `Subscription` 只能表示一次提醒

目前：

```python
is_notified = models.BooleanField(default=False)
```

問題：

- 只能表示「是否通知過」。
- 無法記錄通知失敗。
- 無法支援多次提醒，例如前 3 天、前 1 天、前 2 小時。

建議：

- `ReminderSchedule`
- `ReminderDeliveryLog`

### 18.6 缺少全文搜尋索引

目前搜尋主要靠：

```python
title__icontains
district__icontains
tags__in
```

SQLite 下資料少可以，但資料變多後會慢。

建議：

- MVP 可先加 indexes。
- 後續可用 SQLite FTS5 或改 PostgreSQL full-text search。

## 19. 安全與部署相關缺漏

雖然這不是純資料庫問題，但融合時有看到幾個會影響交付的地方。

### 19.1 SECRET_KEY 寫死

`TaoyuanTime-main` 的 `settings.py` 有 hardcoded `SECRET_KEY`。

正式部署應改用環境變數。

### 19.2 LINE token 欄位拼字錯誤

目前有：

```python
LINE_CHNNEL_ACCESS_TOKEN = ''
```

`CHANNEL` 拼成 `CHNNEL`。

如果後續串 LINE Bot，這會造成設定讀不到。

### 19.3 `ALLOWED_HOSTS = ['*']`

開發可以，正式部署不建議。

### 19.4 `DEBUG = True`

正式部署要關閉。

## 20. 建議下一階段工作

如果下一步要繼續做，我建議順序如下：

### 階段 1：完成活動後台 CRUD

目前只有列表讀正式資料。

下一步應做：

1. `activityAdd` 寫入 `events.Activity`
2. `activityEdit` 讀取並更新 `events.Activity`
3. 下架按鈕改 `status='inactive'`
4. 新增 CSRF-protected POST form
5. 表單欄位對齊正式資料表

### 階段 2：Dashboard 改讀正式資料

目前 dashboard 截圖仍像是靜態數字。

建議改成：

- 活動總數：`Activity.objects.count()`
- 上架中活動：`status='active'`
- 草稿數：`status='draft'`
- 下架數：`status='inactive'`
- 本月推播次數：等 PushCampaign 做完再接

### 階段 3：推播管理資料表

新增：

- `PushCampaign`
- `PushDeliveryLog`

再讓推播管理頁讀 DB。

### 階段 4：補資料庫唯一鍵與追蹤欄位

最推薦先補：

1. `Activity.source_url` unique 或 `source_key + external_id` unique
2. `external_id`
3. `scraped_at`
4. `first_seen_at`
5. `last_seen_at`
6. `content_hash`
7. `ActivityAsset`

### 階段 5：AI 與推薦資料品質補強

建議補：

- AI summary log
- tag confidence
- manual review flag
- recommendation batch id
- user interaction context

## 21. 總結

本次融合完成的是第一階段資料打通：

- 爬蟲 JSON 已能匯入 `Database.events.Activity`。
- `Database/db.sqlite3` 已成為正式共用資料庫。
- `TaoyuanTime-main` 已能讀 `events.Activity`。
- 活動列表已從靜態假資料改成正式資料。
- 匯入流程可以 dry-run，也可以重跑更新。

目前資料庫設計可以支撐 MVP 展示，但若要成為穩定可維護的系統，最需要補的是：

1. 活動來源唯一識別與唯一鍵。
2. 爬蟲批次與資料追蹤欄位。
3. 推播 campaign / delivery log。
4. 活動附件表。
5. 結構化報名、地點、場次資料。
6. 後台審核與 AI 產出歷程。

短期內，先完成活動新增/編輯/下架接 `events.Activity`，會是最直接、最有感的下一步。
