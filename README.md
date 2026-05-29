# TaoyuanTime 政府活動管理系統

## 📋 專案概述

IMintergrateSys 是一個整合 LINE Bot 與後台管理系統的政府活動管理平台。該系統提供一個完整的後台管理界面，用於管理政府活動，包括活動的新增、編輯、發佈以及推播通知功能。同時整合智能 LINE Bot，為用戶提供活動推薦、訂閱、查詢等功能。

**開始日期：** 2026年5月21日  
**狀態：** 🚀 開發中

---

## 🎯 核心功能

### 1. 後台管理系統

#### 1.1 用戶認證與授權 (`/`)
- **登入頁面** - 用戶身份驗證入口
- POST 方式驗證（簡單非空驗證）
- CSRF 保護已啟用

#### 1.2 儀表板 (`/dashboard/`)
- 後台管理首頁
- 系統概覽和快速操作入口

#### 1.3 活動管理
##### 活動列表 (`/activityList/`)
- 展示所有活動
- 按狀態、地區、關鍵字篩選
- 最多展示 100 筆
- 按最新開始時間排序

##### 新增活動 (`/activityList/activityAdd/`)
- 建立新的活動
- 填寫活動基本資訊

##### 編輯活動 (`/activityList/Edit/<id>/`)
- 修改現有活動資訊
- 更新活動狀態

#### 1.4 推播管理 (`/push`)
- 管理推播通知
- 支援 LINE Bot 推播功能

#### 1.5 用戶管理 (`/User`)
- 管理系統用戶
- 權限分配

### 2. LINE Bot 功能

#### 2.1 用戶關注 (Follow Event)
- 用戶首次關注 Bot 時自動触發
- 自動建立或更新用戶檔案
- 顯示偏好設定 Flex 菜單

#### 2.2 活動推薦系統
- **命令：** 「推薦活動」、「猜你喜歡」、「今日推薦」
- 根據用戶偏好標籤推薦活動
- 最多推薦 3 筆符合的活動
- 卡片式展示含活動詳情

#### 2.3 標籤偏好設定
- 多選方式設定偏好
- 標籤分類：
  - 🎵 活動類型（藝文、市集、戶外、美食、音樂）
  - 👥 適合對象（親子、學生、情侶、寵物）
  - 🎁 優惠類別（免費、市民卡優惠）
- 實時同步推薦結果

#### 2.4 活動訂閱功能
- 點擊活動卡片的「訂閱」按鈕
- 自動記錄訂閱歷史
- 支援 Google 行事曆快速加入
- 提醒前天數自訂（預設 1 天）

#### 2.5 用戶行為追蹤
- 記錄訂閱、搜尋等操作
- 用於優化推薦演算法

---

## 📁 項目結構

```
.
├── Database/                     # 數據庫應用與相關文檔
│   ├── events/                   # 活動事件應用（核心應用）
│   │   ├── migrations/           # 數據庫遷移文件
│   │   │   ├── __init__.py
│   │   │   ├── 0001_initial.py
│   │   │   ├── 0002_activity_quality.py
│   │   │   └── 0003_activity_ticket_free.py
│   │   ├── crawlers/             # 數據爬蟲模塊
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # 爬蟲基類
│   │   │   ├── culture.py        # 文化活動爬蟲
│   │   │   ├── importer.py       # 導入器
│   │   │   ├── library.py        # 圖書館活動爬蟲
│   │   │   └── tycg.py           # 桃園市政府活動爬蟲
│   │   ├── management/           # Django 管理命令
│   │   │   ├── __init__.py
│   │   │   └── commands/
│   │   │       ├── __init__.py
│   │   │       ├── crawl_activities.py
│   │   │       ├── import_crawler_json.py
│   │   │       └── seed_initial_data.py
│   │   ├── __init__.py
│   │   ├── admin.py              # Django Admin 配置（Activity 等）
│   │   ├── apps.py
│   │   ├── models.py             # 數據模型
│   │   ├── services.py           # 業務邏輯層
│   │   └── README_DB.md
│   ├── docs/                     # 文檔資料
│   │   └── delivery/
│   │       ├── ER_REFERENCE.md
│   │       ├── INDEX.md
│   │       ├── QA_CHECKLIST.md
│   │       ├── QUICK_START.md
│   │       └── SUMMARY.md
│   ├── db.sqlite3                # SQLite 數據庫文件
│   ├── schema.sql                # 數據庫架構
│   ├── requirements.txt          # 依賴管理
│   ├── README_DB.md              # 數據庫文檔
│   ├── README_RUN.md             # 運行說明
│   ├── FINAL_DELIVERY_CHECKLIST.md
│   ├── handover_package.md
│   ├── ai_fields.md
│   └── frontend_fields.md
│
├── IMintergrateSys/              # Django 項目配置
│   ├── __init__.py
│   ├── settings.py               # Django 設置（包含 LINE Bot 金鑰）
│   ├── urls.py                   # 主 URL 路由
│   ├── asgi.py
│   └── wsgi.py
│
├── admin_app/                    # 後台管理應用
│   ├── migrations/               # 數據庫遷移文件
│   │   ├── __init__.py
│   │   └── 0001_initial.py
│   ├── service/                  # 業務邏輯層
│   ├── __init__.py
│   ├── admin.py                  # Django Admin（參考）
│   ├── apps.py
│   └── views.py                  # 視圖函數（登入、儀表板、活動管理等）
│
├── myapp/                        # LINE Bot 應用
│   ├── migrations/
│   │   └── __init__.py
│   ├── service/
│   │   └── service.py            # LINE Bot 業務邏輯
│   ├── __init__.py
│   ├── admin.py                  # Django Admin（Activity、Tag 等）
│   ├── apps.py
│   ├── tests.py
│   └── views.py                  # LINE Bot Callback 和事件處理
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
│       ├── pushManagement.css
│       └── userManagement.css
│
├── manage.py                     # Django 管理命令
├── README.md                     # 本文檔
├── record.md                     # 開發筆記
├── database_integration_report.md # 數據庫整合報告
├── project_main_goal_and_line_tracking_notes.md  # 項目目標與追蹤筆記
└── (其他配置文件)
```

---

## 📊 主要數據模型

### Activity（活動）
位於：`Database/events/models.py`

| 字段 | 類型 | 說明 |
|------|------|------|
| title | CharField | 活動名稱 |
| description | TextField | 活動說明 |
| location | CharField | 活動地點 |
| district | CharField | 行政區域 |
| start_date | DateTimeField | 開始時間 |
| end_date | DateTimeField | 結束時間 |
| status | CharField | 狀態：`active`（已上架）、`inactive`（已下架）、`draft`（草稿） |
| is_free | BooleanField | 是否免費 |
| tags | ManyToManyField | 活動標籤 |
| created_at | DateTimeField | 建立時間 |
| updated_at | DateTimeField | 更新時間 |

### UserProfile（用戶檔案）
| 字段 | 類型 | 說明 |
|------|------|------|
| line_user_id | CharField | LINE 用戶 ID |
| display_name | CharField | 用戶暱稱 |
| preferred_tags | ManyToManyField | 偏好標籤 |
| push_enabled | BooleanField | 是否啟用推播 |

### Subscription（活動訂閱）
| 字段 | 類型 | 說明 |
|------|------|------|
| user | ForeignKey | 用戶 |
| activity | ForeignKey | 活動 |
| remind_before_days | IntegerField | 提前提醒天數 |
| is_notified | BooleanField | 是否已通知 |

---

## 🔗 URL 路由配置

### 後台管理系統

| 路徑 | 視圖函數 | 方法 | 說明 |
|------|---------|------|------|
| `/` | `login()` | GET/POST | 登入頁面 |
| `/admin/` | Django Admin | - | Django 後台管理 |
| `/dashboard/` | `dashboard()` | GET | 儀表板首頁 |
| `/activityList/` | `activityList()` | GET | 活動列表 |
| `/activityList/activityAdd/` | `activityAdd()` | GET | 新增活動頁面 |
| `/activityList/Edit/<int:id>/` | `activityEdit(id)` | GET | 編輯活動頁面 |
| `/push` | `pushManagement()` | GET | 推播管理 |
| `/User` | `userManagement()` | GET | 用戶管理 |

### LINE Bot

| 路徑 | 視圖函數 | 方法 | 說明 |
|------|---------|------|------|
| `/callback` | `callback()` | POST | LINE 消息 Webhook |

---

## 🛠 技術堆棧

| 技術 | 版本 | 用途 |
|------|------|------|
| Django | 5.2.7 | 後端框架 |
| Python | 3.x | 後端語言 |
| SQLite | - | 數據庫 |
| HTML/CSS | - | 前端界面 |
| LINE Bot SDK | - | LINE Bot 集成 |
| ngrok | - | 本地 Webhook 代理 |

---

## 🚀 快速開始

### 開發環境設置

#### 1. 安裝依賴
```bash
cd Database
pip install -r requirements.txt
# 或主目錄
pip install django linebot
```

#### 2. 應用數據庫遷移
```bash
python manage.py migrate
```

#### 3. 創建超級用戶（可選）
```bash
python manage.py createsuperuser
```

#### 4. 啟動開發服務器
```bash
python manage.py runserver
```
服務器將運行在 `http://127.0.0.1:8000/`

### LINE Bot 本地測試（使用 ngrok）

#### 1. 下載並安裝 ngrok
下載地址：https://ngrok.com/download

#### 2. 啟動 ngrok 代理
```bash
./ngrok http 8000
```
您將獲得一個公開 URL，例如：`https://xxxxx.ngrok.io`

#### 3. 配置 LINE Developer Console
1. 登入 [LINE Developers](https://developers.line.biz/)
2. 選擇您的 Channel
3. 在 **Messaging API** 設定頁面中：
   - 設置 **Webhook URL** 為：`https://xxxxx.ngrok.io/callback`
   - 啟用 **Use webhook**

#### 4. 更新 Django 設置
在 [IMintergrateSys/settings.py](IMintergrateSys/settings.py) 中確保已配置：
```python
LINE_CHANNEL_ACCESS_TOKEN = '您的 Channel Access Token'
LINE_CHANNEL_SECRET = '您的 Channel Secret'
```

#### 5. 在 LINE 上測試
1. 將 Bot 加為好友
2. 發送消息或點擊選單
3. Bot 應自動回應

---

## 📝 常見開發任務

### 模板開發注意事項

⚠️ **重要提醒：** 每個 HTML 模板檔案**必須**在頂部包含以下代碼，以正確加載 CSS 文件：

```html
{% load static %}
```

否則靜態文件（CSS）將無法正常加載。

### 新增後台頁面流程

每次新增分頁時，需要執行以下步驟：

1. 在 [admin_app/views.py](admin_app/views.py) 中創建視圖函數
2. 在 [IMintergrateSys/urls.py](IMintergrateSys/urls.py) 中配置 URL 路由
3. 在 [templates/](templates/) 中創建對應 HTML 模板
4. 如需樣式，在 [static/css/](static/css/) 中創建 CSS 文件

**示例：**
```python
# views.py in admin_app
def myNewPage(request):
    return render(request, 'myNewPage.html')

# urls.py
path('myNewPage/', myNewPage, name='myNewPage'),

# templates/myNewPage.html
{% load static %}
<!DOCTYPE html>
<html>
  <head>
    <link rel="stylesheet" href="{% static 'css/myNewPage.css' %}">
  </head>
  <body>
    <!-- 內容 -->
  </body>
</html>
```

### Django Admin 操作

訪問 `/admin/` 可以管理所有模型，包括：
- Activity（活動）
- SourceWebsite（數據源）
- Tag（標籤）
- UserProfile（用戶檔案）
- Subscription（訂閱）

---

## 📚 應用說明

### admin_app（後台管理應用）
- **位置：** `admin_app/`
- **功能：** 提供後台管理界面
- **主要視圖：**
  - `login()` - 登入（需完成身份驗證邏輯）
  - `dashboard()` - 儀表板
  - `activityList()` - 活動列表（支持篩選）
  - `activityAdd()` - 新增活動
  - `activityEdit()` - 編輯活動
  - `pushManagement()` - 推播管理
  - `userManagement()` - 用戶管理

### events（數據庫應用）
- **位置：** `Database/events/`
- **功能：** 核心數據模型和業務邏輯
- **主要內容：**
  - 完整的 Activity、UserProfile、Subscription 等模型
  - 爬蟲模塊用於數據導入
  - 服務層提供業務邏輯

### myapp（LINE Bot 應用）
- **位置：** `myapp/`
- **功能：** LINE Bot 消息處理和交互
- **事件處理：**
  - `handle_follow()` - 用戶關注事件
  - `handle_postback()` - 按鈕點擊事件（標籤切換、活動訂閱）
  - `handle_text_message()` - 文本消息事件（推薦活動、關鍵字搜尋）

---

## 🐛 已知問題和解決方案

### 1. CSRF Token 錯誤
**問題：** `Forbidden (CSRF cookie not set): /`  
**解決：** 確保 HTML 表單中包含 `{% csrf_token %}`

### 2. 模型重複註冊
**問題：** `AlreadyRegistered: The model Activity is already registered`  
**解決：** 只在一個 app 的 `admin.py` 中註冊模型，不要重複

### 3. URL 導入錯誤
**問題：** `AttributeError: module 'views' has no attribute 'views'`  
**解決：** 正確導入視圖函數，不要使用 `views.views`

### 4. LINE Bot 無回應
**問題：** 發送消息但 Bot 不回應  
**檢查清單：**
- 確認 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 正確
- 確認 ngrok 正常運行
- 確認 Webhook URL 在 LINE Developer Console 中正確設置
- 確認 Django 服務器正常運行
- 查看 Django 日誌是否有錯誤

---

## 📖 開發日誌

### 2026年5月21日
- ✅ 專案建立
- ✅ Django 項目初始化

### 2026年5月22日
- ✅ **發現：** `admin_app` 後台管理與 LINE Bot 可以進行整合
- ✅ 確認開發方法和最佳實踐
- ✅ CSS 加載問題解決（需要 `{% load static %}`）

### 2026年5月30日
- ✅ 修復 CSRF 保護錯誤（添加 csrf_token）
- ✅ 修復 URL 路由導入問題
- ✅ 修復模型重複註冊問題
- ✅ LINE Bot 事件處理器完整實現
- ✅ 更新完整 README 文檔
- 🔧 **當前狀態：** Django 開發服務器正常運行，ngrok 已啟動，等待 LINE Bot 完整測試

---

## 🔐 生產部署提醒

⚠️ **重要：部署前必須執行的項目**

1. **安全設置**
   - [ ] `DEBUG = False` 關閉調試模式
   - [ ] `SECRET_KEY` 使用環境變數而非硬編碼
   - [ ] `ALLOWED_HOSTS` 限制為特定域名

2. **身份驗證**
   - [ ] 實現完整的登入邏輯（目前只是簡單驗證）
   - [ ] 添加會話管理
   - [ ] 實現權限檢查

3. **LINE Bot**
   - [ ] **確保使用正確的 LINE Channel 金鑰**（目前為開發金鑰）
   - [ ] 使用正式的 Webhook URL（不使用 ngrok）
   - [ ] 測試所有 Bot 功能

4. **數據庫**
   - [ ] 遷移至 PostgreSQL 或其他生產數據庫（不使用 SQLite）
   - [ ] 設置數據庫備份

5. **監控與日誌**
   - [ ] 配置日誌系統
   - [ ] 設置錯誤監控（如 Sentry）
   - [ ] 監控 Bot 響應狀態

---

## 📞 支援與聯繫

- **數據庫文檔：** 詳見 [Database/README_DB.md](Database/README_DB.md)
- **快速開始：** 詳見 [Database/docs/delivery/QUICK_START.md](Database/docs/delivery/QUICK_START.md)
- **架構參考：** 詳見 [Database/docs/delivery/ER_REFERENCE.md](Database/docs/delivery/ER_REFERENCE.md)

---

**最後更新：** 2026年5月30日  
**項目狀態：** 🚀 開發進行中

---


