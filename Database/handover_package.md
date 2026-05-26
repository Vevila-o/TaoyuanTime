# 交接清單 — 桃園 AI 智慧活動資訊服務系統

快速說明：此專案為 Django + SQLite 的最小可執行版本，包含 `events` app、爬蟲範例、初始 seed 指令與管理後台設定。

- 前端拿什麼：
  - 卡片欄位：`title`, `description`（或 `ai_summary`）, `start_date`, `end_date`, `location`, `district`, `image_url`, `source_url`, `tags`, `is_free`, `requires_registration`。

- 後端拿什麼：
  - 完整 `Activity`、`Tag`、`SourceWebsite`、`UserProfile`、`Subscription`、`ActionLog`。
  - services.py 裡有 `recommend_activities_for_user`、`search_activities_by_conditions`、`get_line_card_payload` 等功能。

- AI 同學拿什麼：
  - 可使用 `raw_content`, `description` 作為輸入；AI 標籤輸出僅回傳標籤名稱串列，後端負責比對 `Tag` 表並回傳需要人工審核的候選標籤。

- `db.sqlite3` 怎麼產生：
  - 執行 `python manage.py migrate` 會在專案根目錄建立 `db.sqlite3`。

- 如何重新 seed：
  - 執行 `python manage.py seed_initial_data`，會建立固定 `Tag`、`SourceWebsite` 以及 100 筆 mock `Activity`。

- 如何測試推薦與搜尋：
  - 進入 shell：
    ```
    python manage.py shell
    from events.models import UserProfile
    from events.services import recommend_activities_for_user, search_activities_by_conditions
    u = UserProfile.objects.first()
    recommend_activities_for_user(u)
    search_activities_by_conditions(district='桃園', tag_names=['音樂'], is_free=True)
    ```

其他：
- 管理後台：`/admin/`，可管理所有資料表。
- 爬蟲：執行 `python manage.py crawl_activities` 會執行三個範例 crawler，並匯入為 `draft` 狀態。
資料庫交接包說明（簡潔）

目標：提供給組員可立即上手的資料庫交接包（models、admin、service、seed、crawler、schema 參考、使用說明）。

要交給前端：
- `events/services.py`（使用 `get_line_card_payload(activity)` 取得給 LINE 的 payload）
- `events/models.py`（Activity 欄位參考）
- `events/README_DB.md`（欄位說明與使用範例）

要交給 AI 同學：
- `events/models.py`（主要欄位：`raw_content`, `description`, `tags`, `district`, `start_date`, `end_date`, `is_free`）
- `events/README_DB.md`（AI 欄位與標籤說明）

要交給後端同學：
- `events/models.py`, `events/admin.py`, `events/services.py`
- `events/management/commands/seed_initial_data.py`（初始化資料）、`events/management/commands/crawl_activities.py`（爬蟲匯入）
- `events/crawlers/`（爬蟲雛形與 importer）

前端使用的 service function：
- `get_line_card_payload(activity)`：回傳 dict 給 LINE 卡片呈現

AI 同學欄位（分類/搜尋）推薦：
- 輸入：`raw_content`, `description`
- 回傳比對：使用 `Tag` 表（`name`）做映射，後端只接受存在的 Tag
- 搜尋字段：`title`, `description`, `tags`, `district`, `start_date`, `end_date`, `is_free`

後端同學操作說明（簡短）：
- 新增活動：透過 admin 或 `Activity.objects.create(...)`，上架前請設定 `status='active'`。
- 查詢活動：使用 `events.services.search_activities_by_conditions(...)` 或直接用 ORM 範例：
  `Activity.objects.filter(status='active', district__icontains='桃園').order_by('start_date')`
- 記錄互動：使用 `events.services.log_user_action(user, action_type, activity, metadata)`。

包含檔案清單（建議一併交付）：
- events/models.py
- events/admin.py
- events/services.py
- events/management/commands/seed_initial_data.py
- events/management/commands/crawl_activities.py
- events/crawlers/
- events/README_DB.md
- schema.sql
- (若生成) db.sqlite3

補充：migrate 與本機驗證步驟請參考 `events/README_DB.md`。

## 資料庫檢查結果（開發者驗證）

- Activity = 210
- Tag = 49
- SourceWebsite = 13
- UserProfile = 1

- is_activity=True = 200
- is_activity=False = 10
- recommendation_ready=True = 200
- line_ready=True = 200

