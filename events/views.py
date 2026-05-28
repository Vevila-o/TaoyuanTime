import json
import urllib.parse
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.conf import settings

# 引入 LINE SDK
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    FollowEvent, PostbackEvent, FlexSendMessage
)

# 引入本機的 Models
from .models import UserProfile, Tag, Activity, Subscription

# 🎯 這裡完完整整引入組員寫在 services.py 裡的所有武器，一行都不用改！
from events.services import (
    recommend_activities_for_user,
    search_activities_by_conditions,
    log_user_action
)

# ==================== LINE Bot 金鑰設定 ====================
LINE_CHANNEL_ACCESS_TOKEN = getattr(settings, 'LINE_CHANNEL_ACCESS_TOKEN', '')
LINE_CHANNEL_SECRET = getattr(settings, 'LINE_CHANNEL_SECRET', '')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
# =========================================================

@csrf_exempt
def callback(request):
    if request.method == 'POST':
        signature = request.META.get('HTTP_X_LINE_SIGNATURE', '')
        body = request.body.decode('utf-8')
        try:
            handler.handle(body, signature)
        except InvalidSignatureError:
            return HttpResponseForbidden("LINE signature verification failed.")
        except Exception as e:
            return HttpResponseBadRequest(f"Error handling webhook: {str(e)}")
        return HttpResponse("OK")
    else:
        return HttpResponseBadRequest("Method not allowed. Please use POST.")


def get_preference_flex_message(user_profile):
    """偏好設定選單（這部分保持不變）"""
    current_tags = list(user_profile.preferred_tags.values_list('name', flat=True))
    sections = [
        {
            "title": "🎵 想找什麼類型的活動？",
            "tags": [
                {"name": "藝文", "label": "🎨 藝文展覽"},
                {"name": "市集", "label": "🛍️ 踩點市集"},
                {"name": "戶外", "label": "🌲 戶外休閒"},
                {"name": "美食", "label": "🍕 美食饗宴"},
                {"name": "音樂", "label": "🎸 流行音樂"}
            ]
        },
        {
            "title": "👥 專屬合適對象",
            "tags": [
                {"name": "親子", "label": "👨‍👩‍👧 親子同樂"},
                {"name": "學生", "label": "🎒 學生專屬"},
                {"name": "情侶", "label": "👩‍❤️‍👨 約會勝地"},
                {"name": "毛孩", "label": "🐾 寵物友善"}
            ]
        },
        {
            "title": "🎁 好康與小資專區",
            "tags": [
                {"name": "免費", "label": "💰 免費入場"},
                {"name": "市民卡", "label": "💳 市民卡優惠"}
            ]
        }
    ]
    
    body_contents = [{
        "type": "text",
        "text": "請自由點選下方標籤（可多選），綠色代表已追蹤。設定完成後直接關閉視窗即可！",
        "wrap": True, "size": "xs", "color": "#666666", "margin": "xs"
    }]
    
    for sec in sections:
        body_contents.append({
            "type": "text", "text": sec["title"], "weight": "bold",
            "size": "sm", "margin": "lg", "color": "#333333"
        })
        tag_list = sec["tags"]
        for i in range(0, len(tag_list), 2):
            pair = tag_list[i:i+2]
            row_buttons = []
            for opt in pair:
                is_selected = opt["name"] in current_tags
                status_icon = " ✓" if is_selected else ""
                row_buttons.append({
                    "type": "button",
                    "action": {
                        "type": "postback",
                        "label": f"{opt['label']}{status_icon}",
                        "data": f"action=toggle_tag&tag={opt['name']}"
                    },
                    "style": "primary" if is_selected else "secondary",
                    "color": "#1DB446" if is_selected else "#E5E5E5", 
                    "height": "sm", "flex": 1, "margin": "sm"
                })
            if len(pair) == 1:
                row_buttons.append({"type": "filler", "flex": 1})
            body_contents.append({"type": "box", "layout": "horizontal", "margin": "xs", "contents": row_buttons})

    flex_contents = {
        "type": "bubble",
        "header": {
            "type": "box", "layout": "vertical", "backgroundColor": "#1DB446",
            "contents": [{"type": "text", "text": f"👋 {user_profile.display_name}，設定您的活動偏好", "weight": "bold", "size": "sm", "color": "#FFFFFF"}]
        },
        "body": {"type": "box", "layout": "vertical", "paddingAll": "md", "contents": body_contents}
    }
    return FlexSendMessage(alt_text="請設定活動偏好(可多選)", contents=flex_contents)


# ==================== 事件監聽區 ====================

@handler.add(FollowEvent)
def handle_follow(event):
    line_user_id = event.source.user_id
    try:
        profile = line_bot_api.get_profile(line_user_id)
        display_name = profile.display_name
    except Exception:
        display_name = "桃園市民"

    user_profile, created = UserProfile.objects.get_or_create(
        line_user_id=line_user_id,
        defaults={'display_name': display_name, 'push_enabled': True, 'default_remind_before_days': 1}
    )
    if not created:
        user_profile.display_name = display_name
        user_profile.save()

    flex_message = get_preference_flex_message(user_profile)
    line_bot_api.reply_message(event.reply_token, flex_message)


@handler.add(PostbackEvent)
def handle_postback(event):
    line_user_id = event.source.user_id
    postback_data = event.postback.data
    
    try:
        params = dict(urllib.parse.parse_qsl(postback_data))
    except Exception:
        params = {}
        
    action = params.get('action')
    
    # ---------------- 邏輯 A：使用者切換標籤偏好 ----------------
    if action == 'toggle_tag':
        chosen_tag_name = params.get('tag')
        try:
            user = UserProfile.objects.get(line_user_id=line_user_id)
            tag = Tag.objects.get(name=chosen_tag_name)
            
            if user.preferred_tags.filter(id=tag.id).exists():
                user.preferred_tags.remove(tag)
            else:
                user.preferred_tags.add(tag)
            
            # 更新偏好選單打勾狀態
            updated_flex = get_preference_flex_message(user)
            line_bot_api.reply_message(event.reply_token, updated_flex)
            
            # 🎯【 views 呼叫點 1 】使用者剛勾選某標籤，views 直接呼叫組員的條件搜尋服務，幫他找該標籤的活動
            raw_activities = search_activities_by_conditions(tag_names=[chosen_tag_name], limit=3, ai_mode=False)
            
            if raw_activities:
                carousel_payload = generate_activity_carousel(raw_activities, focus_tag=chosen_tag_name)
                line_bot_api.push_message(
                    user.line_user_id,
                    FlexSendMessage(alt_text=f"為您精選【{chosen_tag_name}】的近期活動推薦！", contents=carousel_payload)
                )
        except Exception:
            pass

    # ---------------- 🎯 邏輯 B：使用者點選「訂閱活動」按鈕（已完美整合明細卡片） ----------------
    elif action == 'subscribe_activity':
        activity_id = params.get('activity_id')
        try:
            user = UserProfile.objects.get(line_user_id=line_user_id)
            activity = Activity.objects.get(id=activity_id)
            
            subscription, created = Subscription.objects.get_or_create(
                user=user,
                activity=activity,
                defaults={
                    'remind_before_days': getattr(user, 'default_remind_before_days', 1),
                    'is_notified': False
                }
            )
            
            # 🎯【 views 呼叫點 2 】呼叫組員的服務來記錄使用者的訂閱行為 Log
            try:
                log_user_action(user=user, action_type="subscribe", activity=activity)
            except Exception:
                pass
            
            # 準備要在成功卡片上顯示的明細內容
            try:
                time_display = f"{activity.start_date.strftime('%Y/%m/%d %H:%M')} ~ {activity.end_date.strftime('%m/%d %H:%M')}"
            except Exception:
                time_display = "請詳見活動官網公告"
                
            act_district = getattr(activity, 'district', '') or '桃園'
            act_location = getattr(activity, 'location', '') or '活動現場'
            location_display = f"[{act_district}] {act_location}"

            # Google 行事曆網址安全建構
            def to_google_format(dt_obj):
                if not dt_obj: return None
                dt_str = str(dt_obj).replace('-', '').replace(':', '').replace(' ', 'T')
                if 'T' not in dt_str: dt_str += "T000000"
                if not dt_str.endswith('Z'):
                    if '+' in dt_str: dt_str = dt_str.split('+')[0]
                    dt_str += "Z"
                return dt_str

            g_start = to_google_format(activity.start_date)
            g_end = to_google_format(activity.end_date)
            if not g_start:
                now_str = timezone.now().strftime("%Y%m%dT%H%M%SZ")
                g_start = g_end = now_str
            elif not g_end:
                g_end = g_start
            
            g_title = urllib.parse.quote(str(activity.title))
            g_location = urllib.parse.quote(f"桃園市{act_district}{act_location}")
            act_desc = getattr(activity, 'description', '') or '暫無說明'
            act_url = getattr(activity, 'official_detail_url', '') or 'https://www.tycg.gov.tw/'
            g_details = urllib.parse.quote(f"{act_desc[:40]}\n\n詳情：{act_url}")
            
            google_calendar_url = f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={g_title}&dates={g_start}/{g_end}&details={g_details}&location={g_location}"
            if len(google_calendar_url) > 950:
                g_details_short = urllib.parse.quote(f"詳情：{act_url}")
                google_calendar_url = f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={g_title}&dates={g_start}/{g_end}&details={g_details_short}&location={g_location}"

            # 設定訂閱成功的明細 Flex 訊息（修正 size: "mega"）
            if created:
                remind_days = getattr(subscription, 'remind_before_days', 1)
                status_title = f"🔔 訂閱成功！(將於前 {remind_days} 天通知)"
                status_color = "#1DB446"
            else:
                status_title = "👌 您先前已訂閱過此活動囉！"
                status_color = "#4A4A4A"
                
            calendar_flex = {
                "type": "bubble", "size": "mega",
                "header": {
                    "type": "box", "layout": "vertical", "backgroundColor": status_color,
                    "contents": [{"type": "text", "text": status_title, "weight": "bold", "size": "sm", "color": "#FFFFFF"}]
                },
                "body": {
                    "type": "box", "layout": "vertical", "spacing": "md",
                    "contents": [
                        {"type": "text", "text": activity.title, "weight": "bold", "size": "md", "wrap": True, "color": "#111111"},
                        {"type": "separator", "margin": "sm"},
                        {
                            "type": "box", "layout": "horizontal", "spacing": "sm", "margin": "sm",
                            "contents": [
                                {"type": "text", "text": "時間", "size": "xs", "color": "#888888", "flex": 1},
                                {"type": "text", "text": time_display, "size": "xs", "color": "#333333", "flex": 5, "wrap": True}
                            ]
                        },
                        {
                            "type": "box", "layout": "horizontal", "spacing": "sm",
                            "contents": [
                                {"type": "text", "text": "地點", "size": "xs", "color": "#888888", "flex": 1},
                                {"type": "text", "text": location_display, "size": "xs", "color": "#333333", "flex": 5, "wrap": True}
                            ]
                        },
                        {
                            "type": "button", "style": "primary", "color": "#4285F4", "height": "sm", "margin": "md",
                            "action": {"type": "uri", "label": "📅 新增至 Google 行事曆", "uri": google_calendar_url}
                        }
                    ]
                }
            }
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text=f"活動訂閱成功：{activity.title}", contents=calendar_flex))
        except Exception as ce:
            pass


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_message = event.message.text.strip()
    line_user_id = event.source.user_id
    
    # ---------------- 🎯 邏輯 C：使用者點擊圖文選單「猜你喜歡」或輸入關鍵字 ----------------
    if user_message in ["推薦活動", "猜你喜歡", "今日推薦"]:
        try:
            user = UserProfile.objects.get(line_user_id=line_user_id)
            
            # 🎯【 views 呼叫點 3 】直接呼叫組員寫好的推薦演算法，回傳符合他標籤的 3 筆活動 list
            matched_activities = recommend_activities_for_user(user, limit=3)
            
            if matched_activities:
                # 呼叫下面的卡片生成函式，把組員算出來的活動倒進去
                carousel_payload = generate_activity_carousel(matched_activities)
                line_bot_api.reply_message(
                    event.reply_token,
                    FlexSendMessage(alt_text="為您奉上專屬活動推薦！", contents=carousel_payload)
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="👌 您目前尚未設定偏好標籤，請點選選單設定，以便系統為您精準推薦！")
                )
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="推薦系統忙碌中，請稍後再試。"))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"您輸入了：'{user_message}'。關鍵字搜尋功能開發中！"))
    

def generate_activity_carousel(activities, focus_tag=None):
    """【活動 Carousel 卡片生成工具】"""
    bubbles = []
    for act in activities:
        summary_text = act.ai_summary if getattr(act, 'ai_summary', None) else (act.description[:50] + "..." if getattr(act, 'description', None) else "暫無活動摘要介紹。")
        try:
            time_str = f"⏰ {act.start_date.strftime('%m/%d %H:%M')} ~ {act.end_date.strftime('%m/%d %H:%M')}"
        except Exception:
            time_str = "⏰ 詳見活動官網公告"
            
        act_district = act.district if getattr(act, 'district', None) else "桃園"
        act_location = act.location if getattr(act, 'location', None) else "活動現場"
        
        encoded_location = urllib.parse.quote(f"桃園市{act_district}{act_location}")
        google_maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_location}"
        
        img_url = act.image_url if getattr(act, 'image_url', None) else "https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=500"

        tag_badges = []
        if focus_tag:
            tag_badges.append({
                "type": "box", "layout": "horizontal", "backgroundColor": "#E8F5E9", "paddingX": "sm", "paddingY": "xs", "borderRadius": "md",
                "contents": [{"type": "text", "text": f"#{focus_tag}", "size": "xxs", "color": "#2E7D32", "weight": "bold"}]
            })
            
        try:
            for t in act.tags.all():
                if focus_tag and t.name == focus_tag: continue
                if len(tag_badges) >= 3: break
                tag_badges.append({
                    "type": "box", "layout": "horizontal", "backgroundColor": "#F5F5F5", "paddingX": "sm", "paddingY": "xs", "borderRadius": "md",
                    "contents": [{"type": "text", "text": f"#{t.name}", "size": "xxs", "color": "#666666", "weight": "bold"}]
                })
        except Exception: pass
            
        bubble = {
            "type": "bubble", "size": "mega",
            "hero": {"type": "image", "url": img_url, "size": "full", "aspectRatio": "20:13", "aspectMode": "cover"},
            "body": {
                "type": "box", "layout": "vertical", "paddingAll": "md",
                "contents": [
                    {"type": "text", "text": act.title, "weight": "bold", "size": "md", "wrap": True, "maxLines": 2},
                    {"type": "box", "layout": "horizontal", "margin": "sm", "spacing": "xs", "contents": tag_badges if tag_badges else [{"type": "filler"}]},
                    {"type": "box", "layout": "vertical", "margin": "md", "spacing": "xs", "contents": [{"type": "text", "text": time_str, "size": "xs", "color": "#666666"}, {"type": "text", "text": f"📍 [{act_district}] {act_location}", "size": "xs", "color": "#666666", "wrap": True}]},
                    {"type": "text", "text": summary_text, "size": "xs", "color": "#444444", "margin": "md", "wrap": True, "maxLines": 3}
                ]
            },
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {"type": "button", "action": {"type": "uri", "label": "ℹ️ 活動詳細資訊", "uri": act.official_detail_url if getattr(act, 'official_detail_url', None) and act.official_detail_url.startswith('http') else "https://www.tycg.gov.tw/"}, "style": "secondary", "height": "sm"},
                    {"type": "button", "action": {"type": "uri", "label": "🗺️ 導航前往地點", "uri": google_maps_url}, "style": "secondary", "height": "sm"},
                    {"type": "button", "action": {"type": "postback", "label": "🔔 訂閱此活動通知", "data": f"action=subscribe_activity&activity_id={act.id}"}, "style": "primary", "color": "#1DB446", "height": "sm"}
                ]
            }
        }
        bubbles.append(bubble)
        
    return {"type": "carousel", "contents": bubbles}

# ====================================================================
# 【新功能】即時推播服務 (直接寫在 views.py)
# ====================================================================

def push_activity_to_interested_users(activity):
    """
    當有新活動時，呼叫此函式，它會自動運用組員的推薦邏輯，
    篩選出感興趣的用戶並透過 LINE PUSH 推播。
    """
    # 撈出所有設定接收推播的用戶
    all_users = UserProfile.objects.filter(line_user_id__isnull=False, push_enabled=True)
    
    # 用你的卡片工具產生單一活動的卡片 (傳入 list 格式)
    carousel_payload = generate_activity_carousel([activity])
    
    push_count = 0
    for user in all_users:
        try:
            # 🎯 應用組員的核心演算法：看這筆活動是否在該用戶的推薦清單中
            recommendations = recommend_activities_for_user(user, limit=3)
            
            if activity in recommendations:
                # 執行推播
                line_bot_api.push_message(
                    user.line_user_id,
                    FlexSendMessage(
                        alt_text=f"✨ 桃園新活動推薦：{activity.title}",
                        contents=carousel_payload
                    )
                )
                
                # 記錄組員要求的 Log
                try:
                    log_user_action(user=user, action_type="new_activity_push", activity=activity)
                except:
                    pass
                
                push_count += 1
        except Exception as e:
            print(f"推播失敗 (user: {user.line_user_id}): {e}")
            
    return push_count