# TaoyuanTime 政府活動管理系統

## 📋 專案概述

IMintergrateSys 是一個整合 LINE Bot 與後台管理系統的政府活動管理平台。該系統提供一個完整的後台管理界面，用於管理政府活動，包括活動的新增、編輯、發佈以及推播通知功能。

**開始日期：** 2026年5月21日

---

## 🎯 核心功能

### 1. 用戶認證與授權
- **登入頁面** (`/`) - 用戶身份驗證入口
- 當前版本暫不包含登入控制邏輯

### 2. 儀表板 (`/dashboard/`)
- 後台管理首頁
- 系統概覽和快速操作入口

### 3. 活動管理
#### 活動列表 (`/activityList/`)
- 展示所有活動
- 按狀態篩選（草稿、已上架、已下架）
- 快速操作按鈕

#### 新增活動 (`/activityList/activityAdd/`)
- 建立新的活動
- 填寫活動基本資訊

#### 編輯活動 (`/activityList/Edit/<id>/`)
- 修改現有活動資訊
- 更新活動狀態

### 4. 推播管理 (`/push`)
- 管理推播通知
- 支援 LINE Bot 推播功能

### 5. 用戶管理 (`/User`)
- 管理系統用戶
- 權限分配

---

## 📁 項目結構

```
IMintergrateSys/
├── IMintergrateSys/              # Django 項目配置
│   ├── __init__.py
│   ├── settings.py               # Django 設置
│   ├── urls.py                   # 主 URL 路由
│   ├── asgi.py
│   └── wsgi.py
│
├── admin_app/                    # 後台管理應用
│   ├── migrations/               # 數據庫遷移文件
│   │   └── 0001_initial.py
│   ├── service/                  # 業務邏輯層
│   ├── models.py                 # 數據模型
│   ├── views.py                  # 視圖函數
│   ├── admin.py                  # Django Admin 配置
│   ├── apps.py
│   └── __init__.py
│
├── myapp/                        # LINE Bot 相關應用
│   ├── migrations/
│   ├── service/                  # 業務邏輯層
│   ├── models.py
│   ├── views.py
│   ├── admin.py
│   ├── apps.py
│   ├── tests.py
│   └── __init__.py
│
├── templates/                    # HTML 模板
│   ├── login.html                # 登入頁面
│   ├── dashboard.html            # 儀表板
│   ├── activityList.html         # 活動列表
│   ├── activityAdd.html          # 新增活動
│   ├── activityEdit.html         # 編輯活動
│   ├── pushManagement.html       # 推播管理
│   └── userManagement.html       # 用戶管理
│
├── static/                       # 靜態文件
│   └── css/
│       ├── login.css
│       ├── dashboard.css
│       ├── activityList.css
│       ├── activityAdd.css
│       ├── activityEdit.css
│       ├── pushManagement.css
│       └── userManagement.css
│
├── db.sqlite3                    # SQLite 數據庫
├── manage.py                     # Django 管理命令
├── need.md                       # 需求文檔
├── record.md                     # 開發筆記
└── README.md                     # 本文檔
```

---

## 📊 數據模型

### Activity 模型（admin_app.models）

管理平台的核心數據模型，存儲政府活動信息：

| 字段 | 類型 | 說明 |
|------|------|------|
| title | CharField | 活動名稱（最大200字符） |
| description | TextField | 活動說明 |
| location | CharField | 活動地點 |
| start_date | DateTimeField | 開始時間 |
| end_date | DateTimeField | 結束時間 |
| status | CharField | 狀態：`draft`（草稿）、`inactive`（已下架）、`active`（已上架） |
| created_at | DateTimeField | 建立時間（自動記錄） |
| updated_at | DateTimeField | 更新時間（自動更新） |

**狀態轉移流程：**
```
草稿 (draft) → 已上架 (active) ← ↔ → 已下架 (inactive)
```

---

## 🔗 URL 路由配置

| 路徑 | 視圖函數 | 說明 |
|------|---------|------|
| `/` | `login()` | 登入頁面 |
| `/admin/` | Django Admin | Django 後台管理 |
| `/dashboard/` | `dashboard()` | 儀表板首頁 |
| `/activityList/` | `activityList()` | 活動列表 |
| `/activityList/activityAdd/` | `activityAdd()` | 新增活動頁面 |
| `/activityList/Edit/<int:id>/` | `activityEdit(id)` | 編輯活動頁面 |
| `/push` | `pushManagement()` | 推播管理 |
| `/User` | `userManagement()` | 用戶管理 |

---

## 🛠 技術堆棧

| 技術 | 版本 | 用途 |
|------|------|------|
| Django | 5.2.7 | 後端框架 |
| Python | 3.x | 後端語言 |
| SQLite | - | 數據庫 |
| HTML/CSS | - | 前端界面 |
| LINE Bot API | - | 聊天機器人集成 |

---

## 📝 LINE Bot 集成配置

當前 Django 配置中已預設 LINE Bot 的認證信息（位於 `settings.py`）：

```python
LINE_CHANNEL_ACCESS_TOKEN = '...'    # LINE 頻道存取令牌
LINE_CHANNEL_SECRET = '...'          # LINE 頻道密鑰
```

這使得後台管理系統可以直接推送通知到 LINE 用戶。

---

## 🚀 開發指南

### 開發環境設置

1. **安裝依賴**
   ```bash
   pip install django
   ```

2. **應用數據庫遷移**
   ```bash
   python manage.py migrate
   ```

3. **創建超級用戶（可選）**
   ```bash
   python manage.py createsuperuser
   ```

4. **啟動開發服務器**
   ```bash
   python manage.py runserver
   ```

服務器將運行在 `http://127.0.0.1:8000/`

### 模板開發注意事項

⚠️ **重要提醒：** 每個 HTML 模板檔案**必須**在頂部包含以下代碼，以正確加載 CSS 文件：

```html
{% load static %}
```

否則靜態文件（CSS）將無法正常加載。

### 新增頁面流程

每次新增分頁時，需要執行以下步驟：

1. 在 [admin_app/views.py](admin_app/views.py) 中創建視圖函數
2. 在 [IMintergrateSys/urls.py](IMintergrateSys/urls.py) 中配置 URL 路由
3. 在 [templates/](templates/) 中創建對應 HTML 模板
4. 如需樣式，在 [static/css/](static/css/) 中創建 CSS 文件

**示例：**
```python
# views.py
def myNewPage(request):
    return render(request, 'myNewPage.html')

# urls.py
path('myNewPage/', views.myNewPage, name='myNewPage'),

# 模板：templates/myNewPage.html
{% load static %}
<html>
  ...
</html>
```

---

## 📚 當前應用

### admin_app（後台管理應用）
- 主要應用，負責所有後台管理頁面
- 包含活動管理、推播通知、用戶管理等功能
- 視圖函數：7 個路由對應的視圖

### myapp（LINE Bot 應用）
- 用於 LINE Bot 集成
- 當前暫無模型定義，可根據需求擴展

---

## 📖 開發筆記

### 5月21日
- 專案建立

### 5月22日
- **發現：** `admin_app` 後台管理與 LINE Bot 可以進行整合！
- 確認開發方法：
  - `settings.py` 已經設置好模板和靜態文件路徑
  - `views.py` 只需直接返回 HTML 文件
  - 每個新分頁記得在 `views.py` 和 `urls.py` 中添加對應的請求處理
- **CSS 加載問題解決：** HTML 文件頂部務必添加 `{% load static %}`

---

## 🔐 提醒

⚠️ **生產環境注意事項：**

1. `DEBUG = True` 目前開啟，部署前須關閉
2. `SECRET_KEY` 已暴露，生產環境須更改
3. `ALLOWED_HOSTS` 設為 `['*']`，生產環境須限制特定域名
4. 登入控制邏輯尚未實現，生產前須添加身份驗證
5. `LINE_CHNNEL_ACCESS_TOKEN` `LINE_CHANNEL_SECRET` 目前是小慧自己的不是桃園時光，請記得要更改喔

---




**最後更新：** 2026年5月25日
