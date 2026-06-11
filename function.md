# 功能清單

## myapp/views.py — LINE Bot Webhook 入口與訊息處理

| 函數 | 說明 |
|------|------|
| `callback` | LINE Webhook 入口，接收並驗證所有 LINE 事件 |
| `dispatch_line_event` | 事件分派器，依事件類型（追蹤/Postback/文字/位置）決定處理方式 |
| `handle_postback_event` | 處理 LINE Postback 事件 |
| `handle_text_message` | 處理 LINE 文字訊息事件 |
| `handle_citizen_card_postback` | 處理市民卡相關 Postback（顯示條碼、綁定確認、請求位置） |
| `handle_citizen_card_text` | 處理市民卡相關文字指令（查詢市民卡、輸入卡號綁定、固定市民卡特約優惠卡片） |
| `build_citizen_store_message` | 建立中原附近 4 筆固定市民卡特約優惠 LINE Flex 訊息 |
| `build_citizen_store_carousel` | 建立市民卡特約優惠輪播 Flex 結構 |
| `build_citizen_store_bubble` | 建立單一市民卡特約優惠 Flex Bubble |
| `fetch_display_name` | 取得 LINE 使用者顯示名稱 |
| `handle_location` | 處理位置訊息，保留附近特約商店搜尋並使用同一套 Flex 卡片樣式 |
| `get_preference_flex_message` | 產生偏好設定 Flex Message（全版標籤選擇） |
| `generate_activity_carousel` | 產生活動卡片輪播訊息 |
| `generate_subscription_carousel` | 產生訂閱活動輪播訊息 |
| `generate_barcode_image` | 產生市民卡條碼圖片並回傳可公開存取的 URL |
| `push_activity_to_interested_users` | 推播新活動給符合推薦條件的用戶 |
| `track_activity` | 追蹤活動詳情點擊行為並重導向至官方頁 |
| `track_calendar` | 追蹤加入行事曆動作並重導向至 Google Calendar |
| `track_maps` | 追蹤導航動作並重導向至 Google Maps |
| `user_from_tracking_request` | 從追蹤請求的查詢參數取得使用者 |

---

## myapp/service.py — 活動查詢與推薦服務

| 函數 | 說明 |
|------|------|
| `recommend_activities_for_user` | 依使用者偏好標籤推薦活動（最多 limit 筆） |
| `search_activities_by_conditions` | 多條件搜尋活動（地區、標籤、費用、時間） |
| `get_public_items` | 取得公開且有官方詳情頁的活動 |
| `get_ai_ready_activities` | 取得適合 AI 處理（ai_ready=True）的活動 |
| `get_recommendation_ready_activities` | 取得可進入推薦池（recommendation_ready=True）的活動 |
| `log_user_action` | 記錄使用者互動至 ActionLog |
| `get_due_subscriptions` | 取得即將需要在 window_hours 小時內發送提醒的訂閱 |
| `get_line_card_payload` | 取得 LINE 卡片格式的活動資料（需 line_ready=True） |
| `calculate_distance` | 用 Haversine 公式計算兩地理座標之間的距離（公里） |

---

## myapp/line_services.py — LINE 訊息建構與搜尋邏輯

### 使用者管理
| 函數 | 說明 |
|------|------|
| `get_or_create_line_user` | 取得或建立 LINE 使用者的 UserProfile |
| `build_preference_message` | 建立偏好設定 Flex Message（標籤選擇＋推播頻率） |
| `push_interval_button` | 建立推播頻率設定按鈕元件 |

### 標籤與偏好
| 函數 | 說明 |
|------|------|
| `find_active_tag` | 查找有效的 Tag 資料（含地區後綴容錯） |
| `toggle_preference_tag` | 新增或移除使用者偏好標籤 |
| `preferred_tag_sets` | 取得使用者偏好標籤依類型分組的集合 |
| `activity_region_match` | 判斷活動是否符合使用者的偏好地區 |

### 活動推薦
| 函數 | 說明 |
|------|------|
| `get_recommended_activities` | 取得推薦活動（含去重、輪替、AI 重排序） |
| `get_active_subscribed_activities` | 取得使用者有效且尚未結束的訂閱活動 |
| `equivalent_subscription_for_activity` | 查找使用者對相同業務活動的訂閱 |
| `subscribed_business_keys` | 取得使用者已訂閱活動的業務鍵集合 |
| `exclude_subscribed_equivalent_activities` | 排除使用者已訂閱的相同活動 |
| `recent_seen_business_keys` | 取得使用者最近 12 小時內看過的活動業務鍵 |
| `rotate_recently_seen_activities` | 將近期已看過的活動排到推薦清單後面 |
| `recent_pushed_business_keys` | 取得最近 14 天內已推播過的活動業務鍵 |
| `exclude_recently_pushed_activities` | 排除近期已推播過的活動 |
| `exploration_candidates` | 取得探索候選活動（使用者未見過且未訂閱） |
| `blend_exploration_activity` | 在推薦清單末尾注入一個探索活動 |
| `subscribed_activity_score` | 計算已訂閱活動的分數懲罰（-25） |
| `recent_seen_penalty` | 計算近期已看活動的分數懲罰（-18） |
| `rank_activities_for_user` | 依使用者偏好標籤、互動行為對活動排序 |
| `recent_action_counts` | 取得使用者近 30 天互動行為的加權分數 |
| `rerank_activities_with_ai` | 用 AI 重新排序活動候選清單 |

### 意圖分類
| 函數 | 說明 |
|------|------|
| `handle_line_text_message` | 處理 LINE 文字訊息的主流程（含指令偵測與搜尋） |
| `handle_more_results_text` | 處理使用者要求「查看更多」的文字指令 |
| `handle_refined_search_text` | 處理使用者搜尋精煉的文字指令 |
| `classify_line_intent` | 用 AI 分類使用者訊息意圖 |
| `normalize_line_intent` | 驗證並標準化意圖字串 |
| `rule_classify_line_intent` | 用規則快速分類使用者意圖（不呼叫 AI） |
| `is_activity_query` | 判斷訊息是否為活動查詢 |
| `high_confidence_activity_query` | 判斷是否為高確信度活動查詢（不需 AI 確認） |
| `is_lifestyle_activity_query` | 判斷是否為生活情境活動查詢（帶小孩/雨天/約會） |
| `has_child_lifestyle_intent` | 判斷訊息是否有帶小孩出門的活動意圖 |
| `has_rainy_lifestyle_intent` | 判斷訊息是否有雨天活動意圖 |
| `has_date_lifestyle_intent` | 判斷訊息是否有約會活動意圖 |
| `looks_like_refinement` | 判斷訊息是否為針對上一輪結果的搜尋精煉 |
| `contains_known_tag` | 判斷文字是否包含已知的有效標籤 |

### 搜尋與條件處理
| 函數 | 說明 |
|------|------|
| `search_activities_for_line` | LINE 活動搜尋主流程（含 AI 條件提取、放寬策略） |
| `extract_conditions_from_message` | 用 AI 從訊息中提取結構化查詢條件 |
| `rule_extract_conditions` | 用規則從訊息提取查詢條件（AI 的備援） |
| `normalize_ai_conditions` | 標準化並驗證 AI 提取的查詢條件 |
| `query_activities_by_conditions` | 依結構化條件查詢活動資料庫 |
| `score_activities_for_search_plan` | 依查詢計畫對活動進行語意評分 |
| `relaxed_search_activities` | 漸進式放寬條件搜尋活動（找不到時自動降級） |
| `allow_recommendation_fallback` | 判斷搜尋無結果時是否允許推薦活動 fallback |
| `strict_district_requested` | 判斷查詢是否嚴格要求特定地區 |
| `strict_topic_terms` | 取得查詢中的嚴格主題詞彙 |
| `force_no_result_query` | 判斷是否為不可能在本地找到結果的查詢（如「潛水」） |
| `merge_search_conditions` | 合併基底查詢條件與新的精煉條件 |
| `combine_context_query` | 合併上一輪和本輪查詢字串 |
| `apply_nearby_preference` | 若使用者要求附近且有偏好地區，套用到條件 |
| `semantic_terms_from_conditions` | 從條件中提取所有語意詞彙 |
| `activity_search_blob` | 產生活動搜尋用的全文本（標題＋摘要＋標籤＋Profile） |
| `clean_query_keyword` | 清理查詢關鍵字（移除停用詞） |
| `is_simple_district_query` | 判斷是否為純地區查詢（不含其他條件） |
| `clean_semantic_terms` | 清理語意詞彙清單（移除停用詞） |
| `normalize_relax_order` | 標準化條件放寬順序清單 |
| `applicable_relax_order` | 過濾出實際有值可以放寬的條件順序 |
| `infer_relax_order` | 依條件內容自動推斷放寬順序 |
| `merge_query_terms` | 合併多個詞彙清單並去重（保持順序） |
| `search_activities_by_rules` | 用規則型條件搜尋活動 |

### 對話狀態
| 函數 | 說明 |
|------|------|
| `save_conversation_state` | 儲存使用者對話狀態（查詢意圖、條件、結果） |
| `get_valid_conversation_state` | 取得尚未過期的使用者對話狀態 |
| `serialize_conditions` | 序列化查詢條件為可儲存的 JSON（日期轉字串） |
| `deserialize_conditions` | 反序列化查詢條件（字串轉日期物件） |

### LINE 訊息建構
| 函數 | 說明 |
|------|------|
| `build_activity_carousel_message` | 建立活動輪播 LINE 訊息（含引言文字） |
| `build_no_result_message` | 建立無查詢結果的提示訊息 |
| `build_query_help_message` | 建立查詢說明訊息 |
| `build_activity_intro_text` | 建立活動介紹引言文字（優先用 AI） |
| `build_activity_intro_text_with_ai` | 用 AI 產生活動介紹引言文字 |
| `normalize_line_intro` | 標準化並截斷 AI 產生的引言文字 |
| `build_activity_carousel` | 建立活動輪播 Flex 結構 |
| `build_activity_bubble` | 建立單一活動 Flex Bubble 卡片 |
| `activity_notice_contents` | 建立活動注意事項（放寬搜尋提示） |
| `compact_activity_summary` | 壓縮活動摘要文字至指定長度 |
| `get_activity_image_url` | 取得活動安全圖片 URL（無效時自動使用備用圖） |
| `is_line_safe_image_url` | 判斷圖片 URL 是否符合 LINE API 要求（HTTPS/ASCII） |
| `is_placeholder_image_url` | 判斷是否為占位圖片 URL |
| `default_remote_image_url` | 依活動 id 取得預設遠端圖片 URL |
| `choose_fallback_image` | 依活動 id 輪流選擇備用圖片 |
| `infer_fallback_image_key` | 依活動標題推斷備用圖片類別 |
| `static_line_image_url` | 取得本地靜態 LINE 圖片的公開 URL |
| `build_tag_badges` | 建立活動標籤徽章清單（含已訂閱、偏好標記） |
| `get_public_card_tags` | 取得活動用於卡片顯示的公開標籤 |
| `tag_badge` | 建立單一標籤徽章 Flex 元件 |
| `info_row` | 建立標籤值橫列 Flex 元件 |
| `format_activity_time` | 格式化活動時間（單行顯示） |
| `format_time_range` | 格式化活動時間範圍（含年份） |

### 訂閱管理
| 函數 | 說明 |
|------|------|
| `handle_activity_postback` | 處理活動相關 Postback 事件（訂閱、取消、導航等） |
| `set_subscription_reminder_days` | 設定訂閱活動的提醒天數 |
| `subscribe_activity` | 建立或重新啟用活動訂閱 |
| `cancel_subscription` | 取消活動訂閱 |
| `build_subscription_success_message` | 建立訂閱成功 Flex Message（含提醒設定） |
| `reminder_button` | 建立提醒天數選擇按鈕 |
| `cancel_subscription_button` | 建立取消訂閱按鈕 |
| `view_more_button` | 建立查看更多活動按鈕 |

### URL 工具
| 函數 | 說明 |
|------|------|
| `activity_detail_url` | 取得活動詳情追蹤 URL（含 line_user_id 參數） |
| `tracked_calendar_url` | 取得行事曆追蹤 URL |
| `tracked_maps_url` | 取得導航追蹤 URL |
| `safe_detail_url` | 取得安全的活動官方詳情 URL |
| `google_maps_url` | 產生 Google Maps 搜尋 URL |
| `google_calendar_url` | 產生 Google Calendar 新增活動 URL |
| `truncate_for_url` | 截斷字串以符合 URL 長度限制 |
| `google_datetime` | 格式化日期時間為 Google Calendar 格式 |

### AI 與工具函數
| 函數 | 說明 |
|------|------|
| `call_ai_json` | 呼叫 AI 並回傳解析後的 JSON 物件 |
| `parse_json_object` | 解析可能含 Markdown 包裝的 JSON 字串 |
| `log_ai_processing` | 記錄 AI 處理日誌至 AIProcessingLog |
| `log_card_views` | 批次記錄活動卡片瀏覽行為 |
| `record_action` | 記錄單筆使用者行為至 ActionLog |
| `get_activity_from_postback` | 從 Postback 參數取得活動物件 |
| `parse_positive_int` | 安全解析非負整數 |
| `elapsed_ms` | 計算從起始時間到現在的毫秒數 |

---

## admin_app/views.py — 後台管理介面

| 函數 | 說明 |
|------|------|
| `login` | 登入頁面 |
| `dashboard` | 儀表板首頁（統計數字、熱門活動、Tag 分佈） |
| `queue_operation_job` | 建立並排入後台操作任務 |
| `start_crawl_job_process` | 在背景啟動爬蟲任務子程序 |
| `operations` | 營運工具頁面（手動推播、AI 處理、資料匯入等） |
| `activityList` | 活動列表頁面（含篩選、搜尋、Readiness 診斷） |
| `activityAdd` | 新增活動 |
| `activityEdit` | 編輯活動資料 |
| `activitySetStatus` | 設定活動上架/下架狀態 |
| `activitySetReadiness` | 設定活動 LINE/AI/Recommendation Ready 標記 |
| `activityApplyAiTags` | 對單一活動執行 AI 自動標籤 |
| `tagReview` | 標籤審核頁面（AI 建議標籤列表） |
| `tagSuggestionAction` | 執行標籤審核動作（採納/拒絕） |
| `pushManagement` | 推播管理頁面（Campaign 建立與發送） |
| `userManagement` | 使用者管理頁面 |
| `userDetail` | 使用者詳情頁面（訂閱、行為記錄） |
| `operationJobs` | 後台操作任務列表頁面 |
| `operationJobDetail` | 後台操作任務詳情頁面（進度、日誌） |
| `lineQuerySimulator` | LINE 查詢模擬器（測試搜尋結果與 AI 意圖分類） |
| `crawlJobs` | 爬蟲任務管理頁面 |
| `crawlJobDetail` | 爬蟲任務詳情頁面（子任務進度） |
| `activityChanges` | 活動異動記錄頁面 |
| `activity_form_values` | 解析活動表單提交的資料 |
| `activity_form_context` | 取得活動表單所需的 context 資料（標籤、地區等） |
| `apply_activity_tags` | 套用標籤至活動 |
| `parse_datetime_field` | 安全解析日期時間字串欄位 |
| `parse_manual_overrides` | 解析 manual_overrides JSON 字串欄位 |
| `audit_actor` | 取得當前操作者名稱（用於稽核日誌） |
| `audit` | 記錄管理員操作至 AdminAuditLog |
| `crawler_source_options` | 取得可用爬蟲來源的選項清單 |
| `crawl_preset_options` | 取得爬蟲任務的預設選項設定 |
| `crawl_status_percent` | 計算爬蟲任務整體進度百分比 |
| `crawl_progress_class` | 取得爬蟲進度條的 CSS class |
| `crawl_status_label` | 取得爬蟲狀態的中文標籤 |
| `attach_crawl_progress` | 附加進度資訊到爬蟲任務物件 |
| `crawl_task_progress_percent` | 計算爬蟲子任務進度百分比 |
| `crawl_task_progress_note` | 取得爬蟲子任務進度說明文字 |

---

## Database/events/ai_tagger.py — AI Repair+Tag 與安全補欄位

| 函數 | 說明 |
|------|------|
| `tag_activity` | 對活動建立 compact context，呼叫 AI 產生標籤與 repairs |
| `build_repair_context` | 組合現有欄位、OCR、raw_content、HTML meta/head/main/label 片段，避免餵整頁 HTML |
| `normalize_ai_repairs` | 驗證 AI repair 建議，拒絕低信心、未知欄位、無證據或格式不合法的修補 |
| `apply_safe_repairs` | 只補空欄位並寫入 ActivityChangeLog，套用後重算 readiness |

目前 repair 欄位限於 `start_date`、`end_date`、`location`、`district`、`registration_info`、`registration_url`、`fee_type`。自動套用門檻是 `confidence >= 0.65`，日期必須可解析且結束時間不可早於開始時間；地點會限制長度並排除明顯非桃園或導覽雜訊。

## 管理指令 — OCR → AI Repair+Tag → Readiness

| 指令 | 說明 |
|------|------|
| `process_activity_ocr` | OCR 候選改為 active、未排除、is_activity、有可 OCR 圖片、未 OCR success、未過期，不再要求 recommendation_ready/high |
| `ai_tag_activities --repair-gaps-only` | 只處理缺核心欄位的活動，避免已完整爬到的活動被重複 repair |
| `ai_tag_activities --dry-run --json` | 顯示 repair suggestions 與可套用結果，不寫入 Activity |
| `ai_tag_activities --apply` | 套用 tags、search profile 與安全 repairs，並重算 readiness |
| `run_queued_crawl_jobs` | 後台完整更新順序為 crawler/import → OCR → AI repair+tag → apply safe repairs → recompute readiness → public/search/recommend |
