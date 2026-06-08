import json
import urllib.parse
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.conf import settings
from datetime import date # 記得 import 這個

import os
import barcode
from barcode.writer import ImageWriter
import re

# 引入 LINE SDK
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    FollowEvent, PostbackEvent, FlexSendMessage,ImageSendMessage,LocationMessage
)

# 引入本機的 Models
from events.models import UserProfile, Tag, Activity, Subscription,Store,CitizenCardData

# 🎯 這裡完完整整引入組員寫在 services.py 裡的所有武器，一行都不用改！
from .service import (
    recommend_activities_for_user,
    search_activities_by_conditions,
    log_user_action,calculate_distance
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


def get_preference_flex_message(user_profile, show_only=None):
    current_tags = list(user_profile.preferred_tags.values_list('name', flat=True))
    
    if user_profile.has_citizen_card and "市民卡" not in current_tags:
        # 這裡不存入資料庫，只為了 UI 顯示效果
        display_tags = current_tags + ["市民卡"]
    else:
        display_tags = current_tags
    
    # 定義所有區塊
    all_sections = [
        {"title": "🎨 藝文與知識", "tags": [{"name": "藝文", "label": "🎨 藝文"}, {"name": "表演", "label": "🎭 表演"},
                {"name": "展覽", "label": "🖼️ 展覽"}, {"name": "電影", "label": "🎬 電影"},
                {"name": "閱讀", "label": "📖 閱讀"}, {"name": "講座", "label": "🎤 講座"}]}, # 放入你的標籤資料
        {"title": "🌲 休閒與戶外", "tags": [{"name": "戶外", "label": "🌲 戶外"}, {"name": "市集", "label": "🛍️ 市集"},
                {"name": "農遊", "label": "🚜 農遊"}, {"name": "運動", "label": "⚽ 運動"},
                {"name": "手作", "label": "🔨 手作"}]},
        {"title": "🎵 其他類型", "tags": [{"name": "動漫", "label": "✨ 動漫"}, {"name": "音樂", "label": "🎸 音樂"},
                {"name": "節慶", "label": "🎉 節慶"}]},
        {"title": "👥 專屬目標對象", "tags": [{"name": "親子", "label": "👨‍👩‍👧 親子"}, {"name": "學生", "label": "🎒 學生"},
                {"name": "情侶", "label": "👩‍❤️‍👨 情侶"}, {"name": "毛孩", "label": "🐾 寵物"},
                {"name": "長輩", "label": "👵 長輩"}, {"name": "青年", "label": "🚀 青年"}]},
        {"title": "💳 優惠與費用", "tags": [
            {"name": "免費", "label": "🆓 免費"}, {"name": "免預約", "label": "📝 免預約"},
            {"name": "市民卡", "label": "💳 市民卡"}, {"name": "特約優惠", "label": "🏷️ 特約優惠"}
        ]},
        {"title": "📍 地區選擇", "tags": [
            {"name": "中壢", "label": "📍 中壢"}, {"name": "桃園", "label": "📍 桃園"},
            {"name": "八德", "label": "📍 八德"}, {"name": "平鎮", "label": "📍 平鎮"},
            {"name": "大園", "label": "📍 大園"}, {"name": "楊梅", "label": "📍 楊梅"},
            {"name": "蘆竹", "label": "📍 蘆竹"}, {"name": "龜山", "label": "📍 龜山"},
            {"name": "大溪", "label": "📍 大溪"}, {"name": "龍潭", "label": "📍 龍潭"},
            {"name": "觀音", "label": "📍 觀音"}, {"name": "新屋", "label": "📍 新屋"},
            {"name": "復興", "label": "📍 復興"}
        ]}
    ]
    
    # 如果指定只顯示活動類型，就過濾列表
    if show_only == "activity_type":
        sections = all_sections[:3] # 只取前三個：藝文、休閒、音樂
    else:
        sections = all_sections
    
    body_contents = [{
        "type": "text",
        "text": "請自由點選下方標籤（可多選），綠色代表已追蹤。設定完成後直接關閉視窗即可！",
        "wrap": True, "size": "xs", "color": "#666666", "margin": "xs"
    }]
    
    for sec in sections:
        body_contents.append({
            "type": "text", 
            "text": sec["title"], 
            "weight": "bold", 
            "size": "sm", 
            "margin": "md"
        })
        tag_list = sec["tags"]
        for i in range(0, len(tag_list), 2):
            pair = tag_list[i:i+2]
            row_buttons = []
            for opt in pair:
                # 🎯 這裡進行雙重判定：資料庫裡有，或者是市民卡綁定者
                is_selected = opt["name"] in current_tags or (opt["name"] == "市民卡" and user_profile.has_citizen_card)
                
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

    flex_message = get_preference_flex_message(user_profile, show_only="activity_type")
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
        
        # 定義哪些標籤屬於「活動類型」，勾選後需要觸發即時推薦
        # 請根據你 full_sections 前三個區塊的標籤名稱填入
        activity_type_tags = [
            "藝文", "表演", "展覽", "電影", "閱讀", "講座",  # 藝文與知識
            "戶外", "市集", "農遊", "運動", "手作",          # 休閒與戶外
            "動漫", "音樂", "節慶"                          # 其他類型
        ]
        
        try:
            user = UserProfile.objects.get(line_user_id=line_user_id)
            tag = Tag.objects.get(name=chosen_tag_name)
            
            # --- 1. 記錄偏好（不論什麼標籤，一律更新資料庫） ---
            if user.preferred_tags.filter(id=tag.id).exists():
                user.preferred_tags.remove(tag)
            else:
                user.preferred_tags.add(tag)
            
            # 更新偏好選單打勾狀態（UI 回饋）
            updated_flex = get_preference_flex_message(user)
            line_bot_api.reply_message(event.reply_token, updated_flex)
            
            # --- 2. 判斷是否「即時推播推薦」 ---
            # 只有標籤名稱在清單內，且該次操作是「新增」（即 tag 現在在用戶偏好中）才觸發
            if chosen_tag_name in activity_type_tags and user.preferred_tags.filter(id=tag.id).exists():
                raw_activities = search_activities_by_conditions(tag_names=[chosen_tag_name], limit=3, ai_mode=False)
                
                if raw_activities:
                    carousel_payload = generate_activity_carousel(raw_activities, focus_tag=chosen_tag_name)
                    line_bot_api.push_message(
                        user.line_user_id,
                        FlexSendMessage(alt_text=f"為您精選【{chosen_tag_name}】的近期活動推薦！", contents=carousel_payload)
                    )
        except Exception as e:
            print(f"Error handling toggle_tag: {e}")
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
        
    # 3. 查看已訂閱活動
    elif action == 'view_subscriptions':
        try:
            user = UserProfile.objects.get(line_user_id=line_user_id)
            subscriptions = Subscription.objects.filter(user=user)
            if not subscriptions:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="您目前尚未訂閱任何活動喔！"))
            else:
                activities = [sub.activity for sub in subscriptions]
                carousel_payload = generate_subscription_carousel(activities)
                line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="您的訂閱清單", contents=carousel_payload))
        except Exception:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="讀取訂閱清單時發生錯誤。"))

    # 4. 取消訂閱
    elif action == 'unsubscribe_activity':
        activity_id = params.get('activity_id')
        user = UserProfile.objects.get(line_user_id=line_user_id)
        deleted_count, _ = Subscription.objects.filter(user=user, activity_id=activity_id).delete()
        if deleted_count > 0:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ 已成功取消訂閱該活動！"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="該活動已不在您的訂閱清單中。"))
            
# 調整 views.py 中的 confirm_bind 邏輯
    elif action == 'confirm_bind':
        # 確保 card 參數存在且為字串
        input_card = params.get('card')
        if isinstance(input_card, list):
            input_card = input_card[0]
            
        try:
            line_user_id = event.source.user_id
            user = UserProfile.objects.get(line_user_id=line_user_id)
            card_info = CitizenCardData.objects.get(card_number=input_card)
            
            # 更新資料
            user.citizen_card_number = card_info.card_number
            user.citizen_name = card_info.name
            user.citizen_phone = card_info.phone
            user.citizen_birthdate = card_info.birthdate
            user.has_citizen_card = True
            user.save()
            
            line_bot_api.reply_message(
                event.reply_token, 
                TextSendMessage(text=f"✅ 綁定成功！")
            )
        except Exception as e:
            print(f"DEBUG: 綁定失敗 {e}")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 系統錯誤，請稍後再試。"))


   
    elif action == 'citizen_card_menu':
        user = UserProfile.objects.get(line_user_id=line_user_id)
        
        # 只要卡號不是空的，就代表已綁定
        if user.citizen_card_number:
            try:
                barcode_url = generate_barcode_image(user.citizen_card_number)
                line_bot_api.reply_message(event.reply_token, [
                    TextSendMessage(text=f"【數位市民卡】\n姓名：{user.citizen_name}\n數位碼：{user.citizen_card_number}"),
                    ImageSendMessage(
                        original_content_url=barcode_url,
                        preview_image_url=barcode_url
                    )
                ])
            except Exception as e:
                print(f"DEBUG: 條碼生成錯誤: {e}")
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="讀取條碼失敗。"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="您尚未綁定市民卡，請輸入卡號進行綁定。"))
            
    elif action == 'request_location':
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="請點選下方選單的「＋」或「位置」按鈕，分享您的位置給我們，我將立刻為您搜尋附近的特約商店！"
            )
        )


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_message = event.message.text.strip()
    line_user_id = event.source.user_id
    
    # ---------------- 🎯 邏輯 C：處理圖文選單指令 ----------------
    
    # 1. 處理推薦相關指令
    if user_message in ["推薦活動", "猜你喜歡", "今日推薦"]:
        try:
            user = UserProfile.objects.get(line_user_id=line_user_id)
            matched_activities = recommend_activities_for_user(user, limit=3)
            
            if matched_activities:
                carousel_payload = generate_activity_carousel(matched_activities)
                line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="為您奉上專屬活動推薦！", contents=carousel_payload))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="👌 您目前尚未設定偏好標籤，請點選「偏好設定」進行設定！"))
        except Exception:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="推薦系統忙碌中，請稍後再試。"))

    # 2. 處理偏好設定指令 (新加入的！)
    elif user_message == "偏好設定":
        try:
            user = UserProfile.objects.get(line_user_id=line_user_id)
            # 呼叫你原本寫好的那個 Flex Message 函式
            flex_message = get_preference_flex_message(user)
            line_bot_api.reply_message(event.reply_token, flex_message)
        except Exception:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="系統無法讀取您的設定，請稍後再試。"))
            
    elif user_message == "已訂閱活動":
        try:
            user = UserProfile.objects.get(line_user_id=line_user_id)
            subscriptions = Subscription.objects.filter(user=user)
            if not subscriptions:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="您目前尚未訂閱任何活動喔！"))
            else:
                activities = [sub.activity for sub in subscriptions]
                carousel_payload = generate_subscription_carousel(activities)
                line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="您的訂閱清單", contents=carousel_payload))
        except Exception:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="讀取訂閱清單時發生錯誤。"))
            
    elif user_message == "我的市民卡":
            user = UserProfile.objects.get(line_user_id=line_user_id)
            
            # 修正這裡：直接檢查資料庫中的卡號欄位是否為空
            if user.citizen_card_number and user.citizen_card_number != "":
                try:
                    barcode_url = generate_barcode_image(user.citizen_card_number)
                    line_bot_api.reply_message(event.reply_token, [
                        TextSendMessage(text=f"【數位市民卡】\n姓名：{user.citizen_name}\n數位碼：{user.citizen_card_number}"),
                        ImageSendMessage(
                            original_content_url=barcode_url, 
                            preview_image_url=barcode_url
                        )
                    ])
                except Exception as e:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="讀取條碼失敗，請稍後再試。"))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="您尚未綁定市民卡。請直接輸入市民卡號進行綁定！"))
             


    # ... 內的 else if 改為
    # 這是當輸入卡號格式正確時，顯示的確認訊息
    elif re.match(r'^[A-Za-z]{3}\d{11}$', user_message):
        input_card = user_message.strip()
        
        try:
            card_info = CitizenCardData.objects.get(card_number=input_card)
            
            # 為了避免 400，我們簡化 JSON 結構，確保沒有過深的巢狀或無效欄位
            confirm_flex = {
                "type": "bubble",
                "body": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "請確認綁定資料", "weight": "bold", "size": "lg"},
                    {"type": "separator", "margin": "md"},
                    {"type": "box", "layout": "vertical", "margin": "md", "spacing": "sm",
                     "contents": [
                        {"type": "text", "text": f"姓名：{card_info.name}"},
                        {"type": "text", "text": f"電話：{card_info.phone}"},
                        {"type": "text", "text": f"生日：{card_info.birthdate}"},
                        {"type": "text", "text": f"數位碼：{card_info.card_number}", "color": "#1DB446", "weight": "bold"}
                    ]}
                ]
                },
                "footer": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {
                            "type": "button", "style": "primary", "color": "#1DB446",
                            "action": {
                                "type": "postback", 
                                "label": "確定綁定", 
                                "data": f"action=confirm_bind&card={input_card}"
                            }
                        }
                    ]
                }
            }
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="請確認數位碼", contents=confirm_flex))
            
        except CitizenCardData.DoesNotExist:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 查無此數位碼資料，請確認後重新輸入。"))
            
        except CitizenCardData.DoesNotExist:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 查無此數位碼資料：{input_card}，請確認後重新輸入。"))
    
    elif user_message == "附近的市民卡特約商店":
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="請點選下方選單的「＋」或「位置」按鈕，分享您的位置給我們，我將立刻為您搜尋附近的特約商店！")
        )

    # 3. 其他情況
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"您輸入了：'{user_message}'。關鍵字搜尋功能開發中！"))
        


@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    lat = event.message.latitude
    lon = event.message.longitude
    today = date.today()
    
    nearby_stores = []
    for s in Store.objects.all():
        # 呼叫正確的距離計算函數
        dist = calculate_distance(lat, lon, s.latitude, s.longitude)
        
        if s.end_date and s.end_date < today:
            continue
            
        if dist <= 5.0:
            nearby_stores.append((s, round(dist, 2)))
            
    if not nearby_stores:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="附近目前沒有有效的特約商店。"))
        return

    bubbles = []
    for s, dist in nearby_stores[:9]:
        # 修正導航連結：改用標準的 maps.google.com 網址
        map_url = f"https://www.google.com/maps/search/?api=1&query={s.latitude},{s.longitude}"
        
        display_address = s.address if s.address else "地址未提供"
        display_date = f"📅 優惠至 {s.end_date.strftime('%Y/%m/%d')}" if s.end_date else "📅 常駐優惠"

        bubbles.append({
            "type": "bubble",
            "size": "mega",
            # 將原本的圖片區塊換成 Header，利用綠色底色讓卡片更有質感
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#1DB446", # 桃園市民卡的代表色
                "contents": [
                    {"type": "text", "text": "💳 特約商店", "color": "#FFFFFF", "weight": "bold", "size": "sm"}
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": s.name[:30], "weight": "bold", "size": "lg"},
                    # 地址
                    {"type": "text", "text": f"📍 {display_address}", "wrap": True, "size": "xs", "color": "#999999", "margin": "sm"},
                    {"type": "text", "text": f"距離 {dist} 公里", "color": "#FF6347", "size": "sm", "margin": "sm"},
                    # 分隔線
                    {"type": "separator", "margin": "md"},
                    # 優惠詳情
                    {"type": "text", "text": s.discount_info[:50], "wrap": True, "size": "sm", "color": "#555555", "margin": "md"},
                    # 優惠時間
                    {"type": "text", "text": display_date, "size": "xs", "color": "#888888", "margin": "sm"},

                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "button", "style": "primary", "color": "#4285F4", 
                     "action": {"type": "uri", "label": "🚗 導航前往", "uri": map_url}}
                ]
            }
        })

    line_bot_api.reply_message(
        event.reply_token,
        FlexSendMessage(
            alt_text="附近優惠商店",
            contents={"type": "carousel", "contents": bubbles}
        )
    )
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


def generate_subscription_carousel(activities):
    bubbles = []
    for act in activities:
        # 基本資料與時間格式處理
        img_url = act.image_url if getattr(act, 'image_url', None) else "https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=500"
        act_district = act.district if getattr(act, 'district', None) else "桃園"
        act_location = act.location if getattr(act, 'location', None) else "活動現場"
        
        try:
            time_str = f"⏰ {act.start_date.strftime('%m/%d %H:%M')} ~ {act.end_date.strftime('%m/%d %H:%M')}"
        except Exception:
            time_str = "⏰ 詳見活動官網公告"
            
        # 導航連結
        encoded_location = urllib.parse.quote(f"桃園市{act_district}{act_location}")
        google_maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_location}"
        
        bubble = {
            "type": "bubble", "size": "mega",
            "hero": {"type": "image", "url": img_url, "size": "full", "aspectRatio": "20:13", "aspectMode": "cover"},
            "body": {
                "type": "box", "layout": "vertical", "paddingAll": "md",
                "contents": [
                    {"type": "text", "text": act.title, "weight": "bold", "size": "md", "wrap": True},
                    # 這裡呈現時間與地點
                    {"type": "text", "text": time_str, "size": "xs", "color": "#666666", "margin": "md"},
                    {"type": "text", "text": f"📍 [{act_district}] {act_location}", "size": "xs", "color": "#666666", "margin": "xs"}
                ]
            },
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {
                        "type": "button", 
                        "action": {"type": "uri", "label": "ℹ️ 查看詳情", "uri": act.official_detail_url or "https://www.tycg.gov.tw/"}, 
                        "style": "secondary", "height": "sm"
                    },
                    {
                        "type": "button", 
                        "action": {"type": "uri", "label": "🗺️ 導航前往", "uri": google_maps_url}, 
                        "style": "secondary", "height": "sm"
                    },
                    {
                        "type": "button", 
                        "action": {"type": "postback", "label": "❌ 取消訂閱", "data": f"action=unsubscribe_activity&activity_id={act.id}"}, 
                        "style": "primary", "color": "#FF5722", "height": "sm"
                    }
                ]
            }
        }
        bubbles.append(bubble)
    
    return {"type": "carousel", "contents": bubbles}


def generate_barcode_image(card_number):
    # 確保資料夾存在
    save_dir = os.path.join(settings.MEDIA_ROOT, 'barcodes')
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        
    save_path = os.path.join(save_dir, card_number) # 產生的檔案名稱
    
    # 產生 Code 128 條碼 (barcode 套件會自動加上 .png)
    code128 = barcode.get('code128', card_number, writer=ImageWriter())
    file_path = code128.save(save_path) 
    
    # file_path 會是完整路徑，我們只需要檔案名稱來組網址
    filename = os.path.basename(file_path)
    
    # ⚠️ 重要：設定您的 ngrok 網址或公開網址
    # 若在本地測試，這裡必須是 https://xxxx.ngrok-free.app/media/barcodes/xxxx.png
    base_url = "https://e0e1-2001-b011-6c05-1bd7-602e-d0ad-4b72-58d1.ngrok-free.app" 
    return f"{base_url}{settings.MEDIA_URL}barcodes/{filename}"

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
