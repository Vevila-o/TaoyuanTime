### Hui的筆記

#### 5/21
專案建立

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

#### 5/29
大家都好厲害 寫的超快又有想法
收到line bot了

**之後一定要先建好一個基本專案後再請大家開工，每個人都是完整的專案，修改太麻煩了**

### 資料庫
將資料庫另外單獨出來，在Database 這個資料夾底下的events (不知道為甚麼是命名events)
所有應用的資料庫import 方式

```
 from Database.events.models import 
```

這是芷晴的ngrok
https://098f-60-251-236-105.ngrok-free.app/callback

admin 註冊是為了資料庫的註冊因為大家都是令建專案導致有3個admin
>將其他的都刪除，全部移到events/admin.py 

