
桃園 AI 智慧活動資訊服務系統 — 資料庫交接文件

目錄
- 系統設計目標
- 資料表用途
- Activity 欄位說明
- Tag 固定標籤池設計
- 前端/LINE 同學需使用欄位
- AI 同學需使用欄位
- 後端查詢/推薦說明
- 爬蟲匯入流程
- 避免 AI 任意新增標籤
- migrate 與 seed 指令
- 如何執行 crawl 與測試 services

1. 系統資料庫設計目標
- 簡潔、可交付的大學生專題級資料庫設計，使用 Django + SQLite。
- 支援爬蟲匯入、後台審核、LINE 卡片顯示、使用者偏好與訂閱提醒。
- Tag 為固定池（region/activity_type/audience/cost/discount），AI 只能從池中選標籤。

2. 各資料表用途
- `SourceWebsite`: 管理爬蟲來源網站（name/url/source_type/is_active/note），方便追蹤來源。
- `Tag`: 固定標籤池，分 `tag_type` 管理（地區、活動類型、對象、費用、優惠）。
- `Activity`: 主要活動資料表，從爬蟲匯入後預設 `status='draft'`，管理員可上架（`active`）。
- `UserProfile`: LINE 使用者資料與偏好標籤（ManyToMany）。
- `Subscription`: 使用者訂閱個別活動的提醒設定。
- `ActionLog`: 使用者互動紀錄（瀏覽、感興趣、訂閱等），用於分析與推薦。

3. `Activity` 欄位重點說明
- `title` (char)
- `description` (text)
- `raw_content` (text) - 原始爬蟲內容
- `source_agency`, `source_website`, `source_url`
- `location`, `district`
- `start_date`, `end_date` (DateTime)
- `image_url`
- `is_free`, `requires_registration`, `fee_description`, `registration_info`
- `has_citizen_card_discount`, `citizen_card_note`
- `ai_summary`, `ai_confidence`
- `tags` (ManyToMany -> Tag)
- `status`：`active` / `inactive` / `draft`

4. Tag 池設計（固定）
- `tag_type`:
  - `region`: 桃園、中壢、平鎮、八德、龜山、蘆竹、大溪、龍潭、楊梅、大園、新屋、觀音、復興
  - `activity_type`: 展覽、講座、市集、表演、音樂、親子、戶外、導覽、手作、電影、動漫、運動、寵物、美食、節慶、農遊、閱讀、客家、藝文、青年
  - `audience`: 親子、學生、青年、長輩、一般、情侶、毛孩
  - `cost`: 免費、付費、需報名、免預約、金額未提供
  - `discount`: 市民卡、特約優惠、無優惠、優惠未提供

5. 前端 / LINE 需要的欄位
- 卡片（必需）：`title`, `description`（或 summary）、`start_date`, `end_date`, `location`, `district`, `image_url`, `source_agency`, `source_url`, `tags`, `is_free`, `requires_registration`。
- 詳細頁（可選）：`raw_content`, `registration_info`, `fee_description`, `citizen_card_note`。

6. AI 同學需要的欄位
- 檢索/推薦：`title`, `description`, `tags`, `district`, `start_date`, `end_date`, `is_free`, `status`。
- 分類輸入：`raw_content`, `description`。AI 標籤輸出請對照 `Tag` 表名，若有不存在的 tag，請回傳給後台人工審核。

7. 後端查詢/推薦簡要
- 推薦：以 `UserProfile.preferred_tags` 為主，選取 `Activity` 中 `status='active'` 且未過期的活動，依匹配標籤數與開始時間排序，最多回傳 3 筆。
- 搜尋：支援 `district`, `tag_names`, `is_free`, `start_date`, `end_date`。

8. 爬蟲匯入流程
- 爬蟲產生統一格式 dict，呼叫 `import_activities_from_crawler` 會把資料轉成 `Activity`，預設 `status='draft'`，避免自動上架。
- 匯入會用 `source_url` 判斷重複，已存在則跳過。

9. 如何避免 AI 亂產生標籤
- 不讓 AI 直接寫入 `Tag` 表；AI 回傳的標籤名稱由後端比對 `Tag.objects.filter(name__in=ai_tags)`，只接受存在的標籤，若有 missing 則記錄並標示人工審核。

10. migrate 與 seed 指令
安裝套件：請見下方

建立 migration 與套用：
```
python manage.py makemigrations events
python manage.py migrate
```

執行初始 seed（建立 Tag、SourceWebsite、100 筆 mock 活動）：
```
python manage.py seed_initial_data
```

11. 執行爬蟲
```
python manage.py crawl_activities
```

12. 在 Django shell 測試 services
```
python manage.py shell
>>> from events.models import UserProfile
>>> from events.services import recommend_activities_for_user, search_activities_by_conditions, get_line_card_payload
>>> u = UserProfile.objects.first()
>>> recommend_activities_for_user(u)
>>> search_activities_by_conditions(district='桃園', tag_names=['音樂'], is_free=True)
>>> from events.models import Activity
>>> a = Activity.objects.filter(status='active').first()
>>> get_line_card_payload(a)
```

13. 其他說明
- 若要把爬蟲匯入改為自動上架，請在匯入流程或管理後台加上審核流程；目前預設匯入為 `draft`。

## 資料表關聯概念

本系統以 Activity 作為核心資料表。

- Activity 與 Tag 為 ManyToMany 關係
- UserProfile 與 Tag 為 ManyToMany 關係
- Subscription 記錄使用者訂閱哪些活動
- ActionLog 記錄使用者點擊、訂閱、怎麼去、加入行事曆等互動行為
- SourceWebsite 記錄活動資料來源網站

推薦系統主要參考：
- 使用者偏好 Tag
- 活動 Tag
- 使用者 ActionLog 互動紀錄

## 固定 Tag 池設計原因

本系統不讓 AI 自由生成 Tag，
而是採用固定 Tag 池設計。

原因包括：
1. 避免 AI 產生不一致分類
2. 提升搜尋與推薦穩定性
3. 降低後台管理成本
4. 方便後續統計分析
5. 避免同義詞造成資料混亂

## 資料品質分層設計

為了避免爬蟲匯入的非活動內容（例如公告、回顧或資源頁）被誤用於推播、AI 摘要或推薦，系統將資料品質與可用性拆分為多個欄位：

- `status`：僅代表資料是否上架（active/inactive/draft），不等同於可被推薦或公開。
- `item_type`：資料類型（activity/announcement/recap/place_or_resource），輔助分類。
- `is_activity`：布林值，明確指出此筆是否為真正活動。
- `is_public_item`：是否允許公開查詢與列出。
- `line_ready`：是否可用於生成 LINE 卡片（前端顯示）。
- `ai_ready`：是否可交由 AI 做摘要或問答使用。
- `recommendation_ready`：是否允許進入推薦池。
- `quality_score` / `quality_level` / `quality_warnings`：資料品質評分、分級與警告訊息。
- `exclude_from_recommendation_reason`：若不進推薦池，記錄理由以供後續審查。

實務上：
- 後台可保留公告、回顧、資源頁等資料供查閱，但前台服務（LINE 推播、AI、推薦）會以 readiness flags 與 quality level 做過濾。
- 在匯入流程中會嘗試填入 `official_detail_url` 與 `source_key`，以利後續驗證與分類。

此設計可以降低 AI 幻覺與不當推播的風險，並提供後台人工審核與追蹤的依據。

## 資料庫檢查結果（開發者驗證）

- Activity = 210
- Tag = 49
- SourceWebsite = 13
- UserProfile = 1

- is_activity=True = 200
- is_activity=False = 10
- recommendation_ready=True = 200
- line_ready=True = 200

註：資料庫已套用 migration `0002_activity_quality`，並包含活動與非活動測試資料（用於驗證過濾與推薦行為）。


