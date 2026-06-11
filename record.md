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
   展示用資料已固定為中原附近 4 筆市民卡特約優惠，不做爬蟲

   總之我找了4筆特惠資料直接檔資料庫基本(必勝客之類的，只有這些)，沒有任何擴充，都在中原，ps沒測試過

3. ai chat&活動爬蟲
   chat發現 *平鎮* 的活動沒辦法被抓到，但資料庫裡確實有
   > 1. 對話跳針 (已經調整，但有侷限)
   System prompt寬鬆一些。 使用者只要沒傳到有符合規則的內容就重複出現：
   
   ```
   我可以幫你找桃園活動。你可以試試：
   - 中壢免費活動
   - 週末親子活動
   - 桃園藝文展覽

   也可以點選單的「設定偏好」或「猜你喜歡」
   ```
   > 2. 上下文 (調整後我覺得不錯)
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
   
    

4. 提醒通知修改 (我沒測試，但我現在一律改成，設置你想要之天數語境，應該沒必要那樣= =)
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

#### 6/11 市民卡特約優惠展示資料

市民卡特約商店這輪不做爬蟲，也不做 CSV 擴充；直接使用固定 4 筆中原附近優惠作為正式展示資料。

匯入或更新資料庫：

```powershell
python manage.py seed_zhongyuan_citizen_stores --apply --skip-checks
```

LINE 行為：

- 使用者傳「附近的市民卡特約商店」會直接收到固定 4 張優惠卡片。
- 不要求使用者分享位置。
- 卡片包含店名、地址、優惠內容、優惠期限、導航按鈕。

固定店家：

| 店家 | 優惠期限 | 優惠重點 |
| --- | --- | --- |
| 大魯閣遊戲愛樂園－中壢中原萌獸公園店 | 2025/07/15－2026/07/14 | 憑桃園市民卡或桃園數位碼購票入園，贈送手作童玩區。 |
| 養鍋－中壢中原店 | 2024/08/29－2026/07/14 | 內用消費免費兌換「好養禮」一份，肉品或海鮮擇一。 |
| 必勝客－中壢新中北店 | 2026/03/10－2026/11/30 | 使用優惠代碼 26705，可享指定人氣饗宴餐 399 元。 |
| 肯德基－中壢環中東二店 | 2026/03/10－2026/11/30 | 使用優惠代碼 26763，可享指定雙料冠軍爭霸戰套餐 299 元。 |


#### 6/12 OCR → AI Repair+Tag → Readiness 閉環與資料補救

後台完整更新流程改成：

```text
crawler/import → OCR → AI repair+tag → apply safe repairs → recompute readiness → public/search/recommend
```

重點：

- OCR 候選不再要求 `recommendation_ready=True` 或 `quality_level=high`，避免缺日期/地點的活動永遠進不了 OCR。
- AI tag 擴充成 repair+tag，除了標籤，也會嘗試補 `start_date`、`end_date`、`location`、`district`、`registration_info`、`registration_url`、`fee_type`。
- repair 自動套用只補空欄位，不覆蓋既有值；門檻為 `confidence >= 0.65`。
- repair evidence 與套用/拒絕結果寫在 `AIProcessingLog.output_json`；實際欄位異動寫入 `ActivityChangeLog`。
- 後台「一鍵完整更新」會跑同一套補救流程，且 `--repair-gaps-only` 只處理剛好缺漏核心資訊的活動。

本次資料庫補救：

- 套用最新 dry-run 判定可用的 12 筆 AI repair 結果。
- 平鎮圖書館活動 544-548 由 raw HTML 人工補齊活動時間、精確地點、報名資訊與費用類型。
- 平鎮 544-548 補完後已重算 readiness，`line_ready=True`、`recommendation_ready=True`，`quality_warnings=[]`。
- 平鎮這批 OCR 內容誤指向大溪活動，因此本輪人工修補明確不採用 OCR，只採 raw HTML 的「活動時間 / 活動地點 / 報名期限 / 活動費用」欄位。

