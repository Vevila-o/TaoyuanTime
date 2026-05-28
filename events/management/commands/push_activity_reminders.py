from django.core.management.base import BaseCommand
from django.conf import settings
from linebot import LineBotApi
from linebot.models import FlexSendMessage, TextSendMessage

# 🎯 關鍵：我們直接引入組員原本就寫好的現成函式，以及你寫在 views 的卡片生成工具
from events.services import get_due_subscriptions, log_user_action
from events.views import generate_activity_carousel

class Command(BaseCommand):
    help = '定時任務：呼叫組員寫好的篩選邏輯，主動發送活動提醒通知'

    def handle(self, *args, **options):
        # 1. 讀取 LINE 金鑰
        LINE_CHANNEL_ACCESS_TOKEN = getattr(settings, 'LINE_CHANNEL_ACCESS_TOKEN', '')
        if not LINE_CHANNEL_ACCESS_TOKEN:
            self.stderr.write("❌ 錯誤：未設定 LINE_CHANNEL_ACCESS_TOKEN")
            return
        line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)

        # 2. 🎯 直接呼叫組員寫好的現成功能！
        # 撈出未來 24 小時內，使用者有訂閱且時間到了、該發送通知的訂閱列表
        due_subs = get_due_subscriptions(window_hours=24)
        
        self.stdout.write(f"🚀 開始掃描定時通知，偵測到 {len(due_subs)} 筆即將到期的活動...")

        for sub in due_subs:
            try:
                user = sub.user
                activity = sub.activity
                
                # 確保使用者與活動資料結構正常
                if not user or not activity:
                    continue
                
                # 3. 🎯 呼叫你原本寫在 views.py 裡的漂亮卡片，把這個活動包裝成 Carousel
                # 這裡只傳入單個活動，外面用中括號 [activity] 包成 list 符合你的函式格式
                carousel_payload = generate_activity_carousel([activity])
                
                # 4. LINE 主動 PUSH 推播給使用者
                line_bot_api.push_message(
                    user.line_user_id,
                    FlexSendMessage(
                        alt_text=f"⏰ 叮咚！您訂閱的活動【{activity.title}】即將開始囉！",
                        contents=carousel_payload
                    )
                )
                
                # 5. 🎯 通知成功後，把這筆訂閱狀態改成「已通知」，避免重複發送
                sub.is_notified = True
                sub.save()
                
                # 6. 呼叫組員的 Log 功能記錄一下
                try:
                    log_user_action(user=user, action_type="push_reminder", activity=activity)
                except Exception:
                    pass
                
                self.stdout.write(self.style.SUCCESS(f"  ✅ 已成功推播【{activity.title}】提醒給 {user.display_name}"))
                
            except Exception as e:
                self.stderr.write(f"  ❌ 推送給使用者失敗: {str(e)}")

        self.stdout.write(self.style.SUCCESS("🏁 定時推播任務執行完畢！"))