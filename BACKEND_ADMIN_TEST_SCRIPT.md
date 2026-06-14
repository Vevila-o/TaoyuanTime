# 後台功能測試腳本

這份給上台前或現場展示前快速檢查後台功能，不需要一次爬大量資料。

## 1. 快速後台 smoke test

```powershell
python manage.py smoke_admin_backend
```

會檢查主要後台頁面是否都能開啟：

- 儀表板
- 營運工具
- 任務進度
- LINE 查詢模擬
- 活動管理與失效連結篩選
- 官方連結待確認篩選
- Tag 審核
- 推播管理
- 使用者管理
- 爬蟲任務
- 活動異動
- 資料 invariant：過期仍上架必須為 0、可 LINE/可推薦活動不可缺 AI 摘要

全部顯示 `PASS` 才適合進入展示。

## 2. Demo 資料準備與回溯

展示前建立固定 demo 資料：

```powershell
python manage.py seed_demo_data --reset
```

這會建立一組可重跑的展示資料，來源都標記為 `source_key=demo`，包含：

- 正常可推薦活動
- 待人工審核活動
- AI 摘要待補活動
- 官方連結待確認活動
- 官方連結失效活動
- 過期自動下架活動
- 圖片 fallback 活動
- Demo LINE 使用者與訂閱
- Tag 待審建議

展示後先 dry-run 確認會刪哪些 demo 資料：

```powershell
python manage.py cleanup_demo_data
```

確認無誤後清除 demo 資料：

```powershell
python manage.py cleanup_demo_data --apply
```

正式資料不靠標題手動辨識，cleanup 只會清掉 `source_key=demo` 的活動與 `demo-` 開頭的 LINE 使用者。

## 3. LINE 對話邏輯 smoke test

```powershell
python manage.py smoke_extreme_line_flow
```

會測口語查詢、追問、無結果、追蹤連結紀錄等 LINE 後端邏輯。

## 4. 現場小批爬蟲測試

後台 UI 路徑：

1. 打開 `/crawlJobs/`
2. 「抓取上限」維持 `1`
3. 來源可選單一來源，也可留空
4. 按「開始完整更新」
5. 到任務詳情確認階段與進度

命令列等價測試：

```powershell
python manage.py run_crawler_pipeline --primary-limit 1 --secondary-limit 1 --max-runtime 30 --skip-dynamic --activate
```

現場主流程建議使用 `seed_demo_data --reset`，真爬蟲 limit=1 當備案或加分展示，避免外站與網路狀況影響展示。

## 5. 單項後台功能測試

```powershell
python manage.py test tests.test_admin_activity_list tests.test_admin_diagnostics tests.test_admin_backend_smoke tests.test_demo_seed_data
```

涵蓋：

- 活動列表有效項目排序
- timeout/error 官方連結會被「官方連結待確認」篩選出來，並排序靠前提醒管理員
- 缺日期或待審核不顯示為上架中
- 失效官方連結會退出公開/推薦池
- 過期 active 活動經 readiness 重算後會自動下架，但資料保留
- Tag 審核只顯示可推 LINE / 可推薦的活動候選
- 後台主要頁面可開啟
- Demo seed/cleanup 可重跑與可回溯

## 6. 上台前資料狀態檢查

目前判斷標準：

- `上架中`：必須有日期、地點、官方頁、未過期、非 dead link、非 manual review
- `待補資料`：缺日期、缺地點、缺官方頁等資料問題
- `待審核`：需要人工確認，不進推薦池
- `官方連結待確認`：timeout/error，不等於失效；保留上架資格，但在活動管理中排序靠前提醒管理員確認
- `官方連結疑似失效`：dead link，會從公開/推薦池排除，修復後再次檢查為 ok 才恢復
- `過期仍上架`：應為 0；完整更新或 readiness 重算會把過期 active 活動改成 inactive，活動資料不刪除
- `Tag 審核`：只顯示 active、未過期、未排除、recommendation ready、有官方頁、非 dead link 的 pending 建議
- `AI 摘要待補`：不應包含可 LINE / 可推薦活動，若 smoke test 顯示缺漏，先跑完整更新或單筆 AI 摘要補齊
- `Demo 摘要待補`：`source_key=demo` 是展示用缺口，後台 smoke invariant 會排除，不代表正式資料異常
