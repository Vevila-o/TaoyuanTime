# AI 欄位與使用說明

AI 搜尋會使用的欄位：
- `title`, `description`, `raw_content`, `tags`, `district`, `start_date`, `end_date`, `is_free`, `status`

AI 推薦會使用的欄位：
- 使用者偏好：`UserProfile.preferred_tags`
- 活動候選：`Activity`（過濾 `status='active'` 且未過期）
- 欄位作為特徵：`tags`, `district`, `activity_type`（tag）、`audience`（tag）、時間範圍

Tag 設計與使用：
- `Tag` 為固定池（`tag_type` 包括 region/activity_type/audience/cost/discount），AI 不直接新增 tag。
- 若 AI 輸出新標籤，請後端比對 `Tag.objects.filter(name__in=ai_tags)`，只接受存在於資料庫中的標籤；缺失的標籤應送人工審核流程。

避免 AI 幻覺（practical tips）：
- 不讓 AI 直接寫入資料庫；AI 的建議只作為「候選」，由後端與人工審核確認。
- 提供給 AI 的範例必須包含 `Tag` 白名單，且回傳的標籤需完全對應 `Tag.name`。
- 如需自動匹配，使用模糊比對但記錄匹配信心（`ai_confidence`），低信心需人工介入。
