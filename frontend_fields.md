# 前端欄位說明

LINE 卡片使用欄位：
- `title`
- `description` 或 `ai_summary`（顯示摘要）
- `start_date`, `end_date`
- `location`, `district`
- `image_url`
- `source_url`
- `tags`（陣列，顯示為標籤）
- `is_free`, `requires_registration`

活動列表使用欄位：
- `title`, `start_date`, `district`, `location`, `image_url`, `tags`, `is_free`

推播使用欄位：
- `title`, `start_date`, `location`, `source_url`, `tags`

註記：前端若需更多欄位（例如 `raw_content` 或 `registration_info`）可由詳細頁面 API 提供。
