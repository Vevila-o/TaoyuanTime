import os
import re
import urllib.parse
from datetime import date

import barcode
from barcode.writer import ImageWriter

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    FollowEvent, FlexSendMessage, ImageSendMessage, LocationMessage, MessageEvent,
    PostbackEvent, TextMessage, TextSendMessage,
)

from events.models import Activity, CitizenCardData, Store, UserProfile
from .line_services import (
    build_preference_message,
    get_or_create_line_user,
    handle_activity_postback,
    handle_line_text_message,
    record_action,
    safe_detail_url,
    google_calendar_url,
    google_maps_url,
)
from .service import calculate_distance, log_user_action, recommend_activities_for_user


line_bot_api = LineBotApi(settings.LINE_CHANNEL_ACCESS_TOKEN) if settings.LINE_CHANNEL_ACCESS_TOKEN else None
parser = WebhookParser(settings.LINE_CHANNEL_SECRET) if settings.LINE_CHANNEL_SECRET else None


@csrf_exempt
# LINE Webhook 入口，接收並驗證所有 LINE 事件
def callback(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('Only POST is allowed')
    if line_bot_api is None or parser is None:
        return HttpResponse('LINE credentials are not configured', status=503)

    signature = request.headers.get('X-Line-Signature', '')
    body = request.body.decode('utf-8')

    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        return HttpResponseForbidden('Invalid LINE signature')

    for event in events:
        try:
            reply_message = dispatch_line_event(event)
            if reply_message:
                line_bot_api.reply_message(event.reply_token, reply_message)
        except LineBotApiError as exc:
            return HttpResponseBadRequest(str(exc))

    return HttpResponse('OK')


# 事件分派器，依事件類型（追蹤/Postback/文字/位置）決定處理方式
def dispatch_line_event(event):
    if isinstance(event, FollowEvent):
        user = get_or_create_line_user(getattr(event.source, 'user_id', ''), fetch_display_name(event.source.user_id))
        return build_preference_message(user)

    if isinstance(event, PostbackEvent):
        return handle_postback_event(event)

    if isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
        return handle_text_message(event)

    if isinstance(event, MessageEvent) and isinstance(event.message, LocationMessage):
        handle_location(event)
        return None

    return None


# 處理 LINE Postback 事件，分流市民卡與活動操作
def handle_postback_event(event):
    user = get_or_create_line_user(getattr(event.source, 'user_id', ''))
    params = dict(urllib.parse.parse_qsl(event.postback.data or ''))
    action = params.get('action')

    if action in ('citizen_card_menu', 'confirm_bind', 'request_location'):
        handle_citizen_card_postback(event, action, params)
        return None

    return handle_activity_postback(user, action, params)


# 處理 LINE 文字訊息事件，分流市民卡指令與一般查詢
def handle_text_message(event):
    text = event.message.text.strip()
    user = get_or_create_line_user(getattr(event.source, 'user_id', ''))

    if handle_citizen_card_text(event, text):
        return None

    return handle_line_text_message(user, text)


# 處理市民卡相關 Postback（顯示條碼、綁定確認、請求位置）
def handle_citizen_card_postback(event, action, params):
    line_user_id = event.source.user_id
    try:
        user = UserProfile.objects.get(line_user_id=line_user_id)
    except UserProfile.DoesNotExist:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="找不到您的使用者資料，請重新加入好友。"))
        return

    if action == 'citizen_card_menu':
        if user.citizen_card_number:
            try:
                barcode_url = generate_barcode_image(user.citizen_card_number)
                line_bot_api.reply_message(event.reply_token, [
                    TextSendMessage(text=f"【數位市民卡】\n姓名：{user.citizen_name}\n數位碼：{user.citizen_card_number}"),
                    ImageSendMessage(original_content_url=barcode_url, preview_image_url=barcode_url)
                ])
            except Exception as e:
                print(f"Error showing citizen card barcode: {str(e)}")
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"讀取條碼失敗。({str(e)})"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="您尚未綁定市民卡，請輸入卡號進行綁定。"))

    elif action == 'confirm_bind':
        input_card = params.get('card')
        if isinstance(input_card, list):
            input_card = input_card[0]
        
        # 清理卡號（移除可能的空白）
        input_card = input_card.strip() if input_card else None
        
        if not input_card:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 卡號無效，請重新輸入。"))
            return
        
        try:
            card_info = CitizenCardData.objects.get(card_number=input_card)
            user.citizen_card_number = card_info.card_number
            user.citizen_name = card_info.name
            user.citizen_phone = card_info.phone
            user.citizen_birthdate = card_info.birthdate
            user.has_citizen_card = True
            user.save()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ 綁定成功！"))
            # 記錄綁定行為
            record_action(user, None, 'citizen_card_bind', {'card_number': input_card, 'source': 'line_postback'})
        except CitizenCardData.DoesNotExist:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 查無此數位碼，請確認後重新輸入。"))
        except Exception as e:
            print(f"Error binding citizen card for {line_user_id}: {str(e)}")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 系統錯誤，請稍後再試。"))

    elif action == 'request_location':
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請點選下方選單的「＋」或「位置」按鈕，分享您的位置給我們，我將立刻為您搜尋附近的特約商店！")
        )


CITIZEN_CARD_COMMANDS = {'我的桃園市民卡', '市民卡', '數位市民卡', '查詢市民卡', '市民卡查詢'}


# 處理市民卡相關文字指令（查詢顯示條碼、輸入卡號綁定）
def handle_citizen_card_text(event, text):
    line_user_id = event.source.user_id

    if text in CITIZEN_CARD_COMMANDS:
        try:
            user = UserProfile.objects.get(line_user_id=line_user_id)
            if user.citizen_card_number:
                try:
                    barcode_url = generate_barcode_image(user.citizen_card_number)
                    line_bot_api.reply_message(event.reply_token, [
                        TextSendMessage(text=f"【數位市民卡】\n姓名：{user.citizen_name}\n數位碼：{user.citizen_card_number}"),
                        ImageSendMessage(original_content_url=barcode_url, preview_image_url=barcode_url)
                    ])
                except Exception as e:
                    print(f"Error displaying barcode for {line_user_id}: {str(e)}")
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"讀取條碼失敗，請稍後再試。({str(e)})"))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(
                    text="您尚未綁定市民卡。\n\n請直接輸入您的數位碼進行綁定！\n\n格式說明：\n• 3個英文字母 + 11個數字\n• 範例：ABC12345678901\n• 共14碼，請使用半形輸入"
                ))
        except UserProfile.DoesNotExist:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="找不到您的使用者資料。"))
        return True

    if text == "附近的市民卡特約商店":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請點選下方選單的「＋」或「位置」按鈕，分享您的位置給我們，我將立刻為您搜尋附近的特約商店！")
        )
        return True

    if re.match(r'^[A-Za-z]{3}\d{11}$', text):
        input_card = text.strip()
        try:
            card_info = CitizenCardData.objects.get(card_number=input_card)
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
                        {"type": "button", "style": "primary", "color": "#1DB446",
                         "action": {"type": "postback", "label": "確定綁定", "data": f"action=confirm_bind&card={urllib.parse.quote(input_card)}"}}
                    ]
                }
            }
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="請確認數位碼", contents=confirm_flex))
        except CitizenCardData.DoesNotExist:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"❌ 查無此數位碼：{text}\n\n請確認後重新輸入。\n\n📋 格式說明：\n• 3個英文字母 + 11個數字\n• 範例：ABC12345678901\n• 共14碼，請使用半形輸入"
            ))
        return True

    return False


# 取得 LINE 使用者顯示名稱，失敗時回傳預設值
def fetch_display_name(line_user_id):
    if not line_user_id or line_bot_api is None:
        return '桃園市民'
    try:
        return line_bot_api.get_profile(line_user_id).display_name
    except Exception:
        return '桃園市民'


# 處理位置訊息，搜尋 5 公里內有效特約商店並回覆 Flex 卡片
def handle_location(event):
    lat = event.message.latitude
    lon = event.message.longitude
    today = date.today()

    nearby_stores = []
    for s in Store.objects.all():
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
        map_url = f"https://www.google.com/maps/search/?api=1&query={s.latitude},{s.longitude}"
        display_address = s.address if s.address else "地址未提供"
        display_date = f"📅 優惠至 {s.end_date.strftime('%Y/%m/%d')}" if s.end_date else "📅 常駐優惠"
        bubbles.append({
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#1DB446",
                "contents": [
                    {"type": "text", "text": "💳 特約商店", "color": "#FFFFFF", "weight": "bold", "size": "sm"}
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": s.name[:30], "weight": "bold", "size": "lg"},
                    {"type": "text", "text": f"📍 {display_address}", "wrap": True, "size": "xs", "color": "#999999", "margin": "sm"},
                    {"type": "text", "text": f"距離 {dist} 公里", "color": "#FF6347", "size": "sm", "margin": "sm"},
                    {"type": "separator", "margin": "md"},
                    {"type": "text", "text": s.discount_info[:50], "wrap": True, "size": "sm", "color": "#555555", "margin": "md"},
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


# 產生偏好設定 Flex Message（全版標籤選擇面板）>>在line_service.py
def get_preference_flex_message(user_profile, show_only=None):
    current_tags = list(user_profile.preferred_tags.values_list('name', flat=True))

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

    sections = all_sections[:3] if show_only == "activity_type" else all_sections

    body_contents = [{
        "type": "text",
        "text": "請自由點選下方標籤（可多選），綠色代表已追蹤。設定完成後直接關閉視窗即可！",
        "wrap": True, "size": "xs", "color": "#666666", "margin": "xs"
    }]

    for sec in sections:
        body_contents.append({
            "type": "text",
            "text": sec["title"],
            "weight": "bold", "size": "sm", "margin": "md"
        })
        tag_list = sec["tags"]
        for i in range(0, len(tag_list), 2):
            pair = tag_list[i:i+2]
            row_buttons = []
            for opt in pair:
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


# 產生活動卡片輪播 Flex 訊息（舊版，供後台推播使用）
def generate_activity_carousel(activities, focus_tag=None):
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
        maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_location}"
        img_url = act.image_url if getattr(act, 'image_url', None) else "https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=500"

        tag_badges = []
        if focus_tag:
            tag_badges.append({
                "type": "box", "layout": "horizontal", "backgroundColor": "#E8F5E9",
                "paddingX": "sm", "paddingY": "xs", "borderRadius": "md",
                "contents": [{"type": "text", "text": f"#{focus_tag}", "size": "xxs", "color": "#2E7D32", "weight": "bold"}]
            })
        try:
            for t in act.tags.all():
                if focus_tag and t.name == focus_tag:
                    continue
                if len(tag_badges) >= 3:
                    break
                tag_badges.append({
                    "type": "box", "layout": "horizontal", "backgroundColor": "#F5F5F5",
                    "paddingX": "sm", "paddingY": "xs", "borderRadius": "md",
                    "contents": [{"type": "text", "text": f"#{t.name}", "size": "xxs", "color": "#666666", "weight": "bold"}]
                })
        except Exception:
            pass

        detail_url = act.official_detail_url if getattr(act, 'official_detail_url', None) and act.official_detail_url.startswith('http') else "https://www.tycg.gov.tw/"
        bubble = {
            "type": "bubble", "size": "mega",
            "hero": {"type": "image", "url": img_url, "size": "full", "aspectRatio": "20:13", "aspectMode": "cover"},
            "body": {
                "type": "box", "layout": "vertical", "paddingAll": "md",
                "contents": [
                    {"type": "text", "text": act.title, "weight": "bold", "size": "md", "wrap": True, "maxLines": 2},
                    {"type": "box", "layout": "horizontal", "margin": "sm", "spacing": "xs",
                     "contents": tag_badges if tag_badges else [{"type": "filler"}]},
                    {"type": "box", "layout": "vertical", "margin": "md", "spacing": "xs", "contents": [
                        {"type": "text", "text": time_str, "size": "xs", "color": "#666666"},
                        {"type": "text", "text": f"📍 [{act_district}] {act_location}", "size": "xs", "color": "#666666", "wrap": True}
                    ]},
                    {"type": "text", "text": summary_text, "size": "xs", "color": "#444444", "margin": "md", "wrap": True, "maxLines": 3}
                ]
            },
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {"type": "button", "action": {"type": "uri", "label": "ℹ️ 活動詳細資訊", "uri": detail_url}, "style": "secondary", "height": "sm"},
                    {"type": "button", "action": {"type": "uri", "label": "🗺️ 導航前往地點", "uri": maps_url}, "style": "secondary", "height": "sm"},
                    {"type": "button", "action": {"type": "postback", "label": "🔔 訂閱此活動通知", "data": f"action=subscribe_activity&activity_id={act.id}"}, "style": "primary", "color": "#1DB446", "height": "sm"}
                ]
            }
        }
        bubbles.append(bubble)

    return {"type": "carousel", "contents": bubbles}


# 產生訂閱活動輪播 Flex 訊息（含取消訂閱按鈕）
def generate_subscription_carousel(activities):
    bubbles = []
    for act in activities:
        img_url = act.image_url if getattr(act, 'image_url', None) else "https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=500"
        act_district = act.district if getattr(act, 'district', None) else "桃園"
        act_location = act.location if getattr(act, 'location', None) else "活動現場"
        try:
            time_str = f"⏰ {act.start_date.strftime('%m/%d %H:%M')} ~ {act.end_date.strftime('%m/%d %H:%M')}"
        except Exception:
            time_str = "⏰ 詳見活動官網公告"

        encoded_location = urllib.parse.quote(f"桃園市{act_district}{act_location}")
        maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_location}"
        detail_url = act.official_detail_url or "https://www.tycg.gov.tw/"

        bubble = {
            "type": "bubble", "size": "mega",
            "hero": {"type": "image", "url": img_url, "size": "full", "aspectRatio": "20:13", "aspectMode": "cover"},
            "body": {
                "type": "box", "layout": "vertical", "paddingAll": "md",
                "contents": [
                    {"type": "text", "text": act.title, "weight": "bold", "size": "md", "wrap": True},
                    {"type": "text", "text": time_str, "size": "xs", "color": "#666666", "margin": "md"},
                    {"type": "text", "text": f"📍 [{act_district}] {act_location}", "size": "xs", "color": "#666666", "margin": "xs"}
                ]
            },
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {"type": "button", "action": {"type": "uri", "label": "ℹ️ 查看詳情", "uri": detail_url}, "style": "secondary", "height": "sm"},
                    {"type": "button", "action": {"type": "uri", "label": "🗺️ 導航前往", "uri": maps_url}, "style": "secondary", "height": "sm"},
                    {"type": "button", "action": {"type": "postback", "label": "❌ 取消訂閱", "data": f"action=unsubscribe_activity&activity_id={act.id}"}, "style": "primary", "color": "#FF5722", "height": "sm"}
                ]
            }
        }
        bubbles.append(bubble)

    return {"type": "carousel", "contents": bubbles}


# 產生市民卡 Code128 條碼圖片並回傳可公開存取的完整 URL
def generate_barcode_image(card_number):
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
    base_url = "https://06e1-2001-b011-6c06-9d61-21ec-df73-6a44-e9f0.ngrok-free.app" 
    return f"{base_url}{settings.MEDIA_URL}barcodes/{filename}"


# 推播新活動給符合推薦條件且已開啟推播的用戶
def push_activity_to_interested_users(activity):
    all_users = UserProfile.objects.filter(line_user_id__isnull=False, push_enabled=True)
    carousel_payload = generate_activity_carousel([activity])

    push_count = 0
    for user in all_users:
        try:
            recommendations = recommend_activities_for_user(user, limit=3)
            if activity in recommendations:
                line_bot_api.push_message(
                    user.line_user_id,
                    FlexSendMessage(
                        alt_text=f"✨ 桃園新活動推薦：{activity.title}",
                        contents=carousel_payload
                    )
                )
                try:
                    log_user_action(user=user, action_type="new_activity_push", activity=activity)
                except Exception:
                    pass
                push_count += 1
        except Exception as e:
            print(f"推播失敗 (user: {user.line_user_id}): {e}")

    return push_count


# 追蹤活動詳情點擊行為並重導向至官方頁
def track_activity(request, activity_id):
    activity = Activity.objects.filter(id=activity_id).first()
    if not activity:
        raise Http404('Activity not found')

    line_user_id = request.GET.get('line_user_id') or ''
    if line_user_id:
        user = get_or_create_line_user(line_user_id)
        action = request.GET.get('action') or 'view_detail'
        action_type = 'view_detail' if action == 'view_detail' else 'view_card'
        record_action(user, activity, action_type, {'source': 'tracking_redirect', 'click_action': action})

    return HttpResponseRedirect(safe_detail_url(activity))


# 追蹤加入行事曆動作並重導向至 Google Calendar
def track_calendar(request, activity_id):
    activity = Activity.objects.filter(id=activity_id).first()
    if not activity:
        raise Http404('Activity not found')
    user = user_from_tracking_request(request)
    if user:
        record_action(user, activity, 'add_calendar', {'source': 'tracking_redirect', 'interested': True})
    return HttpResponseRedirect(google_calendar_url(activity))


# 追蹤導航動作並重導向至 Google Maps
def track_maps(request, activity_id):
    activity = Activity.objects.filter(id=activity_id).first()
    if not activity:
        raise Http404('Activity not found')
    user = user_from_tracking_request(request)
    if user:
        record_action(user, activity, 'how_to_go', {'source': 'tracking_redirect'})
    return HttpResponseRedirect(google_maps_url(activity.district, activity.location))


# 從追蹤請求的查詢參數取得使用者物件
def user_from_tracking_request(request):
    line_user_id = request.GET.get('line_user_id') or ''
    if not line_user_id:
        return None
    return get_or_create_line_user(line_user_id)
