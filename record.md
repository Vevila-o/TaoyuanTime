### Hui的筆記

#### 5/21
專案建立

---

#### 5/22
**admin_app**是開發政府後台管理
新開發的頁面跟linebot竟然是可以整合的!!

太久沒寫都忘光光怎麼回傳頁面
>setting.py 已經先設定好路徑
>DIR[...] 
>views.py 只要直接寫回傳的html就好了 

每個分頁記得要去 views.py urls.py 去做request

### html 一定要記得加 `{% load static %}` 
不然css 跑不出來

----

#### 5/29
大家都好厲害 寫的超快又有想法
收到line bot了

**之後一定要先建好一個基本專案後再請大家開工，每個人都是完整的專案，修改太麻煩了**

### 資料庫
將資料庫另外單獨出來，在Database 這個資料夾底下的events (不知道為甚麼是命名events)
所有應用的資料庫import 方式

```
 from events.models import 
```


admin 註冊是為了資料庫的註冊因為大家都是令建專案導致有3個admin
>將其他的都刪除，全部移到events/admin.py 
---

#### 6/10
問題處理

1. line 偏好標籤
   line flex_message 衝突，留下line_service中的功能
   嘗試修改成讓使用者可以一次選完標籤
   >目前狀況：選擇一個標籤 >> 跳一次Flex Bubble
  
  
2. 特約商店
   尚未爬取，功能尚未完成

   - `Store` 資料模型已建好（`events/models.py`，有 name, district, address, latitude, longitude, discount_info, start/end_date）
   - LINE 位置訊息處理已寫好（`myapp/views.py handle_location`），5公里內搜尋並回覆 Flex 卡片
   - 後台管理介面（新增/編輯商店）**尚未建立**
   - 爬蟲 / 資料匯入**尚未建立**
   - 資料庫目前 **0 筆**，使用者分享位置永遠回覆「附近目前沒有有效的特約商店」
   - 待辦：① 從政府開放資料（data.gov.tw）爬取桃園市民卡特約商店，或手動 CSV 匯入 ② 後台加商店管理頁面

3. ai chat&活動爬蟲
   chat發現 *平鎮* 的活動沒辦法被抓到，但資料庫裡確實有
   > 1. 對話跳針
   System prompt寬鬆一些。 使用者只要沒傳到有符合規則的內容就重複出現：
   
   ```
   我可以幫你找桃園活動。你可以試試：
   - 中壢免費活動
   - 週末親子活動
   - 桃園藝文展覽

   也可以點選單的「設定偏好」或「猜你喜歡」
   ```
   > 2. 上下文
   目前的流程僅只步於搜尋活動，使用者延伸話題訊息傳出後，系統就無法回應。

   ```
   使用者：要去中壢玩
   系統：圖文選單
   使用者：xx活動要錢嗎?
   系統：
   我可以幫你找桃園活動。你可以試試：
   - 中壢免費活動
   - 週末親子活動
   - 桃園藝文展覽

   也可以點選單的「設定偏好」或「猜你喜歡」
   ```
   
    

4. 提醒通知修改
   目前提醒推播不論幾天都是「前一天」，要根據使用者的選擇做改動

---

#### 6/10 活動資料重建教學

這版已改成以本機 AI 為主，預設不走 OpenAI fallback。

重建活動資料建議順序：

1. 確認 `.env`

   ```env
   AI_PROVIDER_ORDER=local
   AI_BASE_URL=http://localhost:11434/v1
   AI_MODEL=qwen
   ```

   重點是 `AI_PROVIDER_ORDER=local`，如果本機 AI 沒開，AI tag / search profile 會直接失敗，不會偷偷改用 OpenAI。

2. 確認本機 AI 連線

   ```powershell
   python manage.py shell --skip-checks
   ```

   進入 shell 後可以測：

   ```python
   from events.ai_providers import provider_order
   provider_order()
   ```

   正常應該看到：

   ```python
   ['local']
   ```

3. 清空活動資料，但保留使用者、標籤、特約商店

   先 dry-run 看會刪什麼：

   ```powershell
   python manage.py reset_activity_data --dry-run --skip-checks
   ```

   確認後再真的刪：

   ```powershell
   python manage.py reset_activity_data --confirm --skip-checks
   ```

   這個指令會刪活動、活動訂閱、活動推播紀錄、活動搜尋語意、AI 處理紀錄；不會刪 `UserProfile`、`Tag`、`Store`。

4. 重新爬活動並匯入

   現在後台與命令列的預設爬取上限已改成 1，方便先小量測試。

   小量測試：

   ```powershell
   python manage.py run_crawler_pipeline --primary-limit 1 --secondary-limit 1 --max-runtime 10 --skip-dynamic --no-assets --activate --skip-checks
   ```

   想加大數量時，自己把 `--primary-limit` / `--secondary-limit` 改大即可，例如：

   ```powershell
   python manage.py run_crawler_pipeline --primary-limit 30 --secondary-limit 30 --max-runtime 30 --skip-dynamic --no-assets --activate --skip-checks
   ```

5. 補 AI tag 與搜尋語意

   匯入後要再跑一次 AI tag，因為 LINE 的資料庫型聊天搜尋會吃 `ActivitySearchProfile`。

   小量測試：

   ```powershell
   python manage.py ai_tag_activities --limit 5 --apply --skip-checks
   ```

   大量處理：

   ```powershell
   python manage.py ai_tag_activities --limit 50 --apply --skip-checks
   ```

   如果中途停止，已完成的活動會留下 tag / search profile；之後可以再跑一次接著補。

6. 驗證資料量

   ```powershell
   python manage.py reset_activity_data --dry-run --skip-checks
   ```

   或用 Django shell 看活動數：

   ```python
   from events.models import Activity, ActivitySearchProfile
   Activity.objects.count()
   ActivitySearchProfile.objects.count()
   ```

7. 注意目前本機環境

   `smoke_extreme_line_flow` 目前會被 `barcode` 套件擋住，因為 `myapp/views.py` 會 import `barcode`。
   `requirements.txt` 裡已經有 `python-barcode>=0.15`，但目前本機 Python 環境看起來尚未安裝。



