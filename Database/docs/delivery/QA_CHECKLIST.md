# QA CHECKLIST — 交接檢查清單

請在交接前依下列項目確認：

1. 檔案完整性
   - `manage.py`、`config/`、`events/`、`db.sqlite3`、`requirements.txt`、`schema.sql`、`README_RUN.md`、`events/README_DB.md`、`handover_package.md`、`frontend_fields.md`、`ai_fields.md` 均存在。

2. 資料庫檢查
   - Activity >= 100
   - Tag > 0
   - SourceWebsite >= 13
   - UserProfile >= 1
   - 可執行 `python scripts/check_db.py` 驗證

3. 可執行性
   - 在乾淨環境（虛擬環境）安裝 `requirements.txt` 後，能執行 `makemigrations` / `migrate` / `seed_initial_data`。

4. 文件完整性
   - `docs/delivery/INDEX.md`, `QUICK_START.md`, `QA_CHECKLIST.md`, `ER_REFERENCE.md` 存在且易讀。

5. 交付包檢查
   - 產生 `tyaihub_final_delivery_pack.zip` 並確認 zip 中不包含 `.venv/`、`__pycache__/`、`.vscode/` 等雜檔。
