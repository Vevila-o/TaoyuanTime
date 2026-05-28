# QUICK START — 最短跑通流程

1. 建立並啟用虛擬環境

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. 安裝依賴

   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

3. （可選）若要重置資料庫

   ```powershell
   Remove-Item .\db.sqlite3 -ErrorAction SilentlyContinue
   python manage.py makemigrations events
   python manage.py migrate
   ```

4. 執行 seed（建立 Tag / SourceWebsite / 100 筆 Activity / 測試 UserProfile）

   ```powershell
   python manage.py seed_initial_data
   ```

5. 啟動 Django server

   ```powershell
   python manage.py runserver
   # 管理後台： http://127.0.0.1:8000/admin/
   ```

6. 簡易檢查（可執行 `check_db.py`）

   ```powershell
   python check_db.py
   # 預期輸出：Activity=100, Tag=49, SourceWebsite=13, UserProfile>=1
   ```
