# FINAL DELIVERY CHECKLIST

## 最終交付檔案

必交：
- manage.py
- config/
- events/
- db.sqlite3
- requirements.txt
- schema.sql
- README_RUN.md
- events/README_DB.md
- handover_package.md
- frontend_fields.md
- ai_fields.md

不交：
- .venv/
- __pycache__/
- *.pyc
- .vscode/

## 組員使用方式

1. 解壓縮專案
2. 建議建立虛擬環境並安裝套件：
   pip install -r requirements.txt
3. 啟動伺服器：
   python manage.py runserver

## 若要重新建立資料庫

python manage.py migrate
python manage.py seed_initial_data

## 資料庫檢查結果（開發者驗證）

- Activity = 210
- Tag = 49
- SourceWebsite = 13
- UserProfile = 1

- is_activity=True = 200
- is_activity=False = 10
- recommendation_ready=True = 200
- line_ready=True = 200
