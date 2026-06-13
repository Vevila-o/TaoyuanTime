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

#### 6/13 LINE AI 對話追問測試與修正

這輪針對 LINE Bot 的自然語言活動對話做連續追問測試，不只測單句規則，而是模擬使用者隨興追問：

```text
想帶小孩去放電
這個會不會很遠
啊第二個呢
要報名嗎
換一批看看
```

以及：

```text
有什麼戶外活動
不要親子的
也不要展覽
最好晚上
更多
```

修正重點：

- 對話狀態不再只看第幾輪，而是由 context router 判斷本輪是「追問上一輪卡片」、「精煉上一輪搜尋」、「開始新搜尋」、「查看更多」或「不支援聊天」。
- `免費嗎`、`要報名嗎`、`在哪裡`、`這個會不會很遠` 這種屬性追問會留在上一輪活動卡片，不會重新搜尋。
- `啊第二個呢`、`第二個在哪裡` 會指向上一輪第 2 張卡片，不會被當成「更多活動」或 keyword。
- `不要親子的`、`也不要展覽` 會寫入 `exclude_tag_names`，查詢時排除對應 tag，而不是把負面條件當成想找的 tag。
- `那小孩浴場呢` 這種短新主題會重設上一輪髒掉的查詢字串，不再合併成 `開箱大溪展館是啥，那小孩浴場呢`。
- 明確活動名稱命中標題時，會在 AI rerank 後保護命中活動，避免「小孩浴場」被相近活動擠出前三張。
- `推薦活動` 後追問「更多」會排除近期看過的推薦卡片，避免同一批活動重複出現。
- 費用回覆不再預設「未標示就是免費」；未明確標示會回 `費用未明確標示`。
- 非桃園查詢例如 `台北有什麼展覽` 會回覆目前只支援桃園活動，不會硬塞桃園卡片。

本輪驗證：

```powershell
python manage.py test tests.test_search_profiles tests.test_line_semantic_query
```

結果：

```text
30 tests OK
```

另外有用 `handle_line_text_message` 跑真實連續 replay。最後確認：

- `這個會不會很遠` 回覆上一張活動地點與導航提示。
- `啊第二個呢` 回覆上一輪第 2 張活動。
- `那小孩浴場呢` 會重設 `last_query`，且第一張卡片是小孩浴場。

#### 6/13 LINE AI 對話上下文事件紀錄

這次測試發現 LINE 活動對話不能只靠「第幾輪」判斷狀態，必須看使用者本句是在：

- 追問上一輪活動卡片
- 精煉上一輪搜尋條件
- 要更多卡片
- 重新開始找活動
- 換成新的活動主題

事件 1：泛用重新找活動被當成 refine。

```text
使用者：幫我找中原的活動
使用者：中壢的
使用者：幫我找活動
錯誤：幫我找中原的活動，中壢的，幫我找活動
正確：把「幫我找活動」視為重新找活動或一般推薦，不沿用中原 / 中壢 context
```

修正重點：

- `幫我找活動`、`找活動`、`有什麼活動` 這類沒有地區、標籤、生活情境的新請求，直接清掉上一輪 context。
- 這不是純死規則取代 AI，而是高風險入口的 deterministic guard，避免 AI router 誤判後污染 `LineConversationState.last_query`。
- 已補 regression test：`test_generic_activity_request_resets_previous_location_context`。

事件 2：新主體加追問語氣被誤判成上一輪卡片追問。

```text
上一輪卡片：中原文創園區《即刻救原3-珍綜再見》
使用者：書法展在幹嘛
錯誤：沿用上一輪中原 / 中壢 context，甚至把《即刻救原3》一起回傳
正確：把「書法展」視為新的搜尋主體，不是「這個活動在幹嘛」
```

修正重點：

- `書法展在幹嘛` 這種句子雖然有「在幹嘛」，但前面有明確新主體，不應自動指向上一輪單一卡片。
- 若句中有 `這個`、`那個`、`剛剛`、序號或活動名稱，才偏向上一輪卡片追問。
- 若有新主體加內容詢問詞，會清掉舊 query，並用核心詞過濾搜尋結果，避免舊活動或泛相近卡片混入。
- 已補 regression test：`test_new_subject_with_description_phrase_replaces_previous_context`。

本次驗證：

```powershell
python manage.py test tests.test_line_semantic_query
python manage.py test tests
python manage.py check
```

結果：

- `tests.test_line_semantic_query`：34 tests OK
- 全測試：126 tests OK
- Django check：OK
