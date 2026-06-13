import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, time as datetime_time, timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from linebot.models import FlexSendMessage, TextSendMessage

from events.models import AIProcessingLog, ActionLog, Activity, ActivitySearchProfile, LineConversationState, PushDeliveryLog, Subscription, Tag, UserProfile
from events.ai_providers import call_json_with_fallback, call_text_with_fallback, payload_messages
from events.search_profiles import raw_html_text_for_activity
from events.services import (
  activity_business_key,
  activity_business_keys,
  dedupe_activities_by_business_key,
  get_recommendation_ready_activities,
  recommend_activities_for_user,
)


DISTRICTS = (
  '桃園', '中壢', '平鎮', '八德', '楊梅', '蘆竹', '大溪', '龍潭', '龜山',
  '大園', '觀音', '新屋', '復興',
)
SUMMARY_MAX_LENGTH = 50
ACTIVITY_SEARCH_HINT_WORDS = (
  '活動', '展覽', '藝文', '市集', '戶外', '美食', '音樂', '親子', '免費',
  '週末', '周末', '今天', '今日', '明天', '推薦', '有啥', '有哪些',
  '想找', '找一下', '哪裡', '運動', '腳踏車', '自行車', '單車', '騎車',
  '不用錢', '免門票', '動一動', '小朋友', '兒童', '潛水', '去哪',
)
SMALLTALK_WORDS = ('你好', '嗨', 'hello', 'hi', '謝謝', '你是誰', '幫助', 'help')
PREFERENCE_COMMANDS = {'偏好設定', '設定偏好', '喜好設定'}
RECOMMENDATION_COMMANDS = {'推薦活動', '猜你喜歡', '今日推薦'}
SUBSCRIPTION_COMMANDS = {'已訂閱活動', '我的訂閱', '已訂閱'}
MORE_RESULT_WORDS = {
  '還有嗎', '還有沒有', '還有別的', '別的嗎',
  '換一批', '換一些', '再換', '再給我',
  '更多', '查看更多', '下一批',
}
CLEAR_CONTEXT_COMMANDS = {'清除搜尋', '清除我的搜尋', '重新搜尋', '重設', '清除', '重來', '重新開始'}
LINE_CONTEXT_TTL_MINUTES = 30
SEMANTIC_QUERY_EXPANSIONS = {
  '腳踏車': ['自行車', '單車', '騎車', '運動', '戶外'],
  '自行車': ['腳踏車', '單車', '騎車', '運動', '戶外'],
  '單車': ['自行車', '腳踏車', '騎車', '運動', '戶外'],
  '騎車': ['自行車', '單車', '腳踏車', '運動', '戶外'],
  '運動': ['戶外', '健走', '路跑', '自行車', '單車', '體驗'],
  '戶外': ['運動', '健走', '自然', '旅遊', '體驗'],
  '免費': ['免門票', '不用錢', '免費入場'],
  '親子': ['兒童', '家庭', '小朋友', '孩子'],
  '藝文': ['展覽', '表演', '音樂', '藝術', '文化'],
  '美食': ['餐廳', '餐飲', '小吃', '夜市', '料理'],
  '泥巴': ['黏土', '陶土', '陶藝', '陶瓷', '手作', '親子體驗'],
  '黏土': ['泥巴', '陶土', '陶藝', '陶瓷', '手作', '親子體驗'],
  '陶土': ['泥巴', '黏土', '陶藝', '陶瓷', '手作', '親子體驗'],
  '陶藝': ['泥巴', '黏土', '陶土', '陶瓷', '手作', '親子體驗'],
  '陶瓷': ['泥巴', '黏土', '陶土', '陶藝', '手作', '親子體驗'],
}
CHILD_AUDIENCE_TERMS = ('小孩', '孩子', '小朋友', '兒童', '親子', '家庭')
CHILD_ACTIVITY_CONTEXT_TERMS = ('玩', '放電', '去哪', '哪裡', '想帶', '帶', '出門', '出去')
RAINY_ACTIVITY_TERMS = ('下雨', '雨天')
DATE_ACTIVITY_TERMS = ('約會', '情侶')
LIFESTYLE_KEYWORD_STOPWORDS = (
  '小孩', '孩子', '小朋友', '兒童', '親子', '家庭',
  '玩', '放電', '去哪', '哪裡', '想帶', '帶', '出門', '出去',
  '下雨天', '下雨', '雨天', '情侶', '約會',
)
WEAK_SEMANTIC_TERMS = {'體驗', '自然', '旅遊', '旅行', '休閒', '公園', '推薦', '最好', '吃'}
FEE_SEMANTIC_TERMS = {'免費', '免門票', '不用錢', '免費入場'}
INFERRED_GENERIC_TAGS = {'一般', '青年', '長輩'}
IMPOSSIBLE_LOCAL_TERMS = {'火星', '月球', '外太空'}
OUT_OF_TAOYUAN_TERMS = {
  '台北', '臺北', '新北', '基隆', '新竹', '苗栗', '台中', '臺中', '彰化',
  '南投', '雲林', '嘉義', '台南', '臺南', '高雄', '屏東', '宜蘭',
  '花蓮', '台東', '臺東', '澎湖', '金門', '馬祖', '日本', '韓國',
  '東京', '大阪', '京都',
}
STRICT_SEARCH_TOPICS = {'美食', '餐廳', '餐飲', '小吃', '夜市', '料理', '腳踏車', '自行車', '單車', '騎車', '運動', '路跑', '健走', '潛水'}
FALLBACK_IMAGE_BY_TAG = {
  '藝文': (
    'https://images.unsplash.com/photo-1460661419201-fd4cecdf8a8b?w=800&h=520&fit=crop&auto=format',
    'https://images.unsplash.com/photo-1541961017774-22349e4a1262?w=800&h=520&fit=crop&auto=format',
    'https://images.unsplash.com/photo-1518998053901-5348d3961a04?w=800&h=520&fit=crop&auto=format',
  ),
  '展覽': (
    'https://images.unsplash.com/photo-1545987796-200677ee1011?w=800&h=520&fit=crop&auto=format',
    'https://images.unsplash.com/photo-1531058020387-3be344556be6?w=800&h=520&fit=crop&auto=format',
    'https://images.unsplash.com/photo-1564399579883-451a5d44ec08?w=800&h=520&fit=crop&auto=format',
  ),
  '市集': (
    'https://images.unsplash.com/photo-1488459716781-31db52582fe9?w=800&h=520&fit=crop&auto=format',
    'https://images.unsplash.com/photo-1533900298318-6b8da08a523e?w=800&h=520&fit=crop&auto=format',
    'https://images.unsplash.com/photo-1514933651103-005eec06c04b?w=800&h=520&fit=crop&auto=format',
  ),
  '音樂': (
    'https://images.unsplash.com/photo-1501386761578-eac5c94b800a?w=800&h=520&fit=crop&auto=format',
    'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=800&h=520&fit=crop&auto=format',
    'https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=800&h=520&fit=crop&auto=format',
  ),
  '戶外': (
    'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=800&h=520&fit=crop&auto=format',
    'https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?w=800&h=520&fit=crop&auto=format',
    'https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=800&h=520&fit=crop&auto=format',
  ),
  '美食': (
    'https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=800&h=520&fit=crop&auto=format',
    'https://images.unsplash.com/photo-1555939594-58d7cb561ad1?w=800&h=520&fit=crop&auto=format',
    'https://images.unsplash.com/photo-1498654896293-37aacf113fd9?w=800&h=520&fit=crop&auto=format',
  ),
  '親子': (
    'https://images.unsplash.com/photo-1503454537195-1dcabb73ffb9?w=800&h=520&fit=crop&auto=format',
    'https://images.unsplash.com/photo-1472162072942-cd5147eb3902?w=800&h=520&fit=crop&auto=format',
    'https://images.unsplash.com/photo-1502781252888-9143ba7f074e?w=800&h=520&fit=crop&auto=format',
  ),
}
REMOTE_DEFAULT_IMAGES = (
  'https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=800&h=520&fit=crop&auto=format',
  'https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=800&h=520&fit=crop&auto=format',
  'https://images.unsplash.com/photo-1523580494863-6f3031224c94?w=800&h=520&fit=crop&auto=format',
)
PLACEHOLDER_IMAGE_HOSTS = {'placehold.co', 'via.placeholder.com', 'placeholder.com'}
FALLBACK_IMAGE_KEYWORDS = (
  ('親子', '親子'),
  ('兒童', '親子'),
  ('家庭', '親子'),
  ('美食', '美食'),
  ('餐', '美食'),
  ('市集', '市集'),
  ('展覽', '展覽'),
  ('特展', '展覽'),
  ('藝文', '藝文'),
  ('藝術', '藝文'),
  ('文化', '藝文'),
  ('音樂', '音樂'),
  ('演唱', '音樂'),
  ('樂團', '音樂'),
  ('戶外', '戶外'),
  ('農遊', '戶外'),
  ('健行', '戶外'),
)

PREFERENCE_SECTIONS = [
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



# 取得或建立 LINE 使用者的 UserProfile
def get_or_create_line_user(line_user_id, display_name='桃園市民'):
  user_id = line_user_id or settings.LINE_USER_ID or 'line-test-user'
  user, _ = UserProfile.objects.get_or_create(
    line_user_id=user_id,
    defaults={
      'display_name': display_name or '桃園市民',
      'push_enabled': True,
      'default_remind_before_days': 1,
    },
  )
  if display_name and user.display_name != display_name:
    user.display_name = display_name
    user.save(update_fields=['display_name', 'updated_at'])
  return user


# 建立偏好設定 Flex Message（標籤選擇＋推播頻率設定）
def build_preference_message(user):
  current_tags = set(user.preferred_tags.values_list('name', flat=True))
  body_contents = [{
    'type': 'text',
    'text': '請自由點選下方標籤（可多選），綠色代表已追蹤。設定完成後直接關閉視窗即可！',
    'wrap': True,
    'size': 'xs',
    'color': '#666666',
    'margin': 'xs',
  }]

  for section in PREFERENCE_SECTIONS:
    body_contents.append({
      'type': 'text',
      'text': section['title'],
      'weight': 'bold',
      'size': 'sm',
      'margin': 'lg',
      'color': '#333333',
    })
    tags = section['tags']
    for index in range(0, len(tags), 2):
      row = []
      for item in tags[index:index + 2]:
        selected = item['name'] in current_tags
        row.append({
        'type': 'button',
        'action': {
          'type': 'postback',
          'label': f"{item['label']}{' ✓' if selected else ''}",
            'data': f"action=toggle_tag&tag={urllib.parse.quote(item['name'])}",
          },
          'style': 'primary' if selected else 'secondary',
          'color': '#1DB446' if selected else '#E5E5E5',
          'height': 'sm',
          'flex': 1,
          'margin': 'sm',
        })
      if len(row) == 1:
        row.append({'type': 'filler', 'flex': 1})
      body_contents.append({'type': 'box', 'layout': 'horizontal', 'margin': 'xs', 'contents': row})

  body_contents.append({
    'type': 'text',
    'text': '🔔 推薦推播頻率',
    'weight': 'bold',
    'size': 'sm',
    'margin': 'lg',
    'color': '#333333',
  })
  body_contents.append({
    'type': 'box',
    'layout': 'horizontal',
    'margin': 'xs',
    'contents': [
      push_interval_button(user, 1, '每天'),
      push_interval_button(user, 3, '每 3 天'),
    ],
  })
  body_contents.append({
    'type': 'box',
    'layout': 'horizontal',
    'margin': 'xs',
    'contents': [
      push_interval_button(user, 5, '每 5 天'),
      push_interval_button(user, 0, '關閉'),
    ],
  })

  contents = {
    'type': 'bubble',
    'header': {
      'type': 'box',
      'layout': 'vertical',
      'backgroundColor': '#1DB446',
      'contents': [{
        'type': 'text',
        'text': f'👋 {user.display_name or "桃園市民"}，設定您的活動偏好',
        'weight': 'bold',
        'size': 'sm',
        'color': '#FFFFFF',
      }],
    },
    'body': {'type': 'box', 'layout': 'vertical', 'paddingAll': 'md', 'contents': body_contents},
  }
  return FlexSendMessage(alt_text='請設定活動偏好(可多選)', contents=contents)


# 建立推播頻率設定按鈕元件（已選取時顯示為綠色）
def push_interval_button(user, days, label):
  selected = (days == 0 and not user.recommend_push_enabled) or (
    days > 0 and user.recommend_push_enabled and user.recommend_push_interval_days == days
  )
  return {
    'type': 'button',
    'action': {
      'type': 'postback',
      'label': f"{label}{' ✓' if selected else ''}",
      'data': f'action=set_recommend_push_interval&days={days}',
    },
    'style': 'primary' if selected else 'secondary',
    'color': '#1DB446' if selected else '#E5E5E5',
    'height': 'sm',
    'flex': 1,
    'margin': 'sm',
  }


# 查找有效的 Tag 資料（含「區」後綴容錯與市民卡特例處理）
def find_active_tag(tag_name):
  tag_name = (tag_name or '').strip()
  if not tag_name:
    return None
  tag = Tag.objects.filter(name=tag_name, is_active=True).first()
  if tag:
    return tag
  if tag_name.endswith('區'):
    tag = Tag.objects.filter(name=tag_name[:-1], is_active=True).first()
    if tag:
      return tag
  if tag_name == '市民卡':
    return Tag.objects.filter(name__icontains='市民卡', is_active=True).first()
  return None


# 新增或移除使用者偏好標籤（切換）
def toggle_preference_tag(user, tag_name):
  tag = find_active_tag(tag_name)
  if not tag:
    return False
  if user.preferred_tags.filter(id=tag.id).exists():
    user.preferred_tags.remove(tag)
  else:
    user.preferred_tags.add(tag)
  return True


# 取得推薦活動（含去重、輪替已看活動、AI 重排序）
def get_recommended_activities(user, limit=3, use_ai=True, offset=0, exclude_subscribed=False, exclude_recently_pushed=False, exclude_recently_seen=False):
  pool_size = max(50, limit + offset + 20)
  candidates = recommend_activities_for_user(user, limit=pool_size)
  if not candidates:
    candidates = list(get_recommendation_ready_activities().order_by('start_date', 'id')[:pool_size])
  candidates = dedupe_activities_by_business_key(candidates)
  if exclude_subscribed:
    candidates = exclude_subscribed_equivalent_activities(user, candidates)
  if exclude_recently_pushed:
    candidates = exclude_recently_pushed_activities(user, candidates)
  if exclude_recently_seen:
    seen_keys = recent_seen_business_keys(user)
    fresh_candidates = [activity for activity in candidates if not seen_keys.intersection(activity_business_keys(activity))]
    if fresh_candidates:
      candidates = fresh_candidates
      offset = 0
  ranked = rank_activities_for_user(user, candidates)
  ranked = blend_exploration_activity(user, rotate_recently_seen_activities(user, ranked), limit=max(limit + offset, limit))
  target_size = limit + offset
  if use_ai and len(ranked) > target_size:
    ai_limit = min(len(ranked), target_size + 10)
    ranked = rerank_activities_with_ai(user, '推薦活動', ranked, limit=ai_limit) or ranked
    ranked = blend_exploration_activity(user, rotate_recently_seen_activities(user, ranked), limit=max(limit + offset, limit))
  return ranked[offset:offset + limit]


# 取得使用者有效且尚未結束的訂閱活動
def get_active_subscribed_activities(user, limit=10):
  now = timezone.now()
  subscriptions = (Subscription.objects
                   .select_related('activity')
                   .filter(user=user, status='active', activity__status='active')
                   .filter(activity__excluded_from_public=False, activity__is_activity=True)
                   .filter(Q(activity__end_date__isnull=True) | Q(activity__end_date__gte=now))
                   .order_by('activity__start_date', '-created_at')[:limit])
  return dedupe_activities_by_business_key([subscription.activity for subscription in subscriptions if subscription.activity], limit=limit)


# 查找使用者對業務上相同活動的訂閱（支援相似活動去重）
def equivalent_subscription_for_activity(user, activity, include_cancelled=False):
  if not user or not activity:
    return None
  target_keys = set(activity_business_keys(activity))
  qs = Subscription.objects.select_related('activity').filter(user=user)
  if not include_cancelled:
    qs = qs.filter(status='active')
  active_match = None
  cancelled_match = None
  for subscription in qs:
    if not subscription.activity:
      continue
    if target_keys.intersection(activity_business_keys(subscription.activity)):
      if subscription.status == 'active':
        active_match = subscription
        break
      if cancelled_match is None:
        cancelled_match = subscription
  return active_match or cancelled_match


# 取得使用者已訂閱活動的業務鍵集合
def subscribed_business_keys(user, include_cancelled=False):
  qs = Subscription.objects.select_related('activity').filter(user=user)
  if not include_cancelled:
    qs = qs.filter(status='active')
  keys = set()
  for subscription in qs:
    if subscription.activity:
      keys.update(activity_business_keys(subscription.activity))
  return keys


# 排除使用者已訂閱的相同業務活動
def exclude_subscribed_equivalent_activities(user, activities):
  keys = subscribed_business_keys(user)
  if not keys:
    return activities
  return [activity for activity in activities if not keys.intersection(activity_business_keys(activity))]


# 取得使用者最近 12 小時內看過的活動業務鍵
def recent_seen_business_keys(user, hours=12):
  since = timezone.now() - timedelta(hours=hours)
  keys = set()
  logs = (ActionLog.objects
          .select_related('activity')
          .filter(user=user, action_type='view_card', created_at__gte=since, activity_id__isnull=False)
          .order_by('-created_at')[:50])
  for log in logs:
    if log.activity:
      keys.update(activity_business_keys(log.activity))
  return keys


# 將近期已看過的活動排到推薦清單後面，讓新活動優先顯示
def rotate_recently_seen_activities(user, activities):
  seen_keys = recent_seen_business_keys(user)
  if not seen_keys or len(activities) <= 3:
    return activities
  fresh = []
  seen = []
  for activity in activities:
    if seen_keys.intersection(activity_business_keys(activity)):
      seen.append(activity)
    else:
      fresh.append(activity)
  return fresh + seen


# 取得最近 14 天內已推播過的活動業務鍵
def recent_pushed_business_keys(user, days=14):
  since = timezone.now() - timedelta(days=days)
  keys = set()
  logs = (PushDeliveryLog.objects
          .select_related('activity')
          .filter(user=user, notification_type='recommendation', status='sent', created_at__gte=since)
          .exclude(activity_id__isnull=True)[:100])
  for log in logs:
    if log.activity:
      keys.update(activity_business_keys(log.activity))
  return keys


# 排除近期已推播過的活動，確保推播內容多樣
def exclude_recently_pushed_activities(user, activities):
  keys = recent_pushed_business_keys(user)
  if not keys:
    return activities
  fresh = [activity for activity in activities if not keys.intersection(activity_business_keys(activity))]
  return fresh or activities


# 取得使用者偏好標籤依類型（地區/活動類型/受眾/費用/優惠）分組的集合
def preferred_tag_sets(user):
  tags = list(user.preferred_tags.filter(is_active=True))
  return {
    'region': {tag.name for tag in tags if tag.tag_type == 'region'},
    'activity_type': {tag.id for tag in tags if tag.tag_type == 'activity_type'},
    'audience': {tag.id for tag in tags if tag.tag_type == 'audience'},
    'cost': {tag.id for tag in tags if tag.tag_type == 'cost'},
    'discount': {tag.id for tag in tags if tag.tag_type == 'discount'},
    'all_ids': {tag.id for tag in tags},
  }


# 判斷活動是否符合使用者的偏好地區
def activity_region_match(activity, preferred_regions):
  if not preferred_regions:
    return False
  district = (activity.district or '').replace('區', '')
  if district in preferred_regions:
    return True
  return any(tag.tag_type == 'region' and tag.name in preferred_regions for tag in activity.tags.all())


# 計算已訂閱活動的分數懲罰（避免重複推薦已訂閱活動）
def subscribed_activity_score(user, activity):
  return -25 if equivalent_subscription_for_activity(user, activity) else 0


# 計算近期已看活動的分數懲罰（-18）
def recent_seen_penalty(user, activity):
  return -18 if recent_seen_business_keys(user).intersection(activity_business_keys(activity)) else 0


# 取得使用者未見過且未訂閱的探索候選活動
def exploration_candidates(user, activities):
  seen = recent_seen_business_keys(user)
  subscribed = subscribed_business_keys(user)
  return [
    activity for activity in activities
    if not seen.intersection(activity_business_keys(activity))
    and not subscribed.intersection(activity_business_keys(activity))
  ]


# 在推薦清單末尾注入一個使用者未見過的探索活動
def blend_exploration_activity(user, ranked, limit=3):
  if len(ranked) <= 1 or limit < 3:
    return ranked
  selected = list(ranked[:limit])
  if len(selected) < limit:
    return ranked
  selected_keys = {key for activity in selected for key in activity_business_keys(activity)}
  for activity in exploration_candidates(user, ranked[limit:]):
    if selected_keys.intersection(activity_business_keys(activity)):
      continue
    selected[-1] = activity
    tail = [item for item in ranked if item.id not in {activity.id for activity in selected}]
    return selected + tail
  return ranked


# 判斷訊息是否為活動查詢（含生活情境、地區、關鍵字）
def is_activity_query(text):
  text = (text or '').strip()
  if not text:
    return False
  if text.lower() in SMALLTALK_WORDS:
    return False
  if is_lifestyle_activity_query(text):
    return True
  if any(word in text for word in ACTIVITY_SEARCH_HINT_WORDS):
    return True
  if any(district in text for district in DISTRICTS):
    return True
  return False


# 判斷是否為高確信度活動查詢（不需 AI 確認可直接搜尋）
def high_confidence_activity_query(text):
  text = text or ''
  if is_lifestyle_activity_query(text):
    return True
  if any(term in text for term in ('活動', '推薦', '有沒有', '想看', '想找', '不用錢', '免門票')):
    return True
  if any(term in text for term in ('腳踏車', '自行車', '單車', '騎車', '運動', '動一動', '小朋友', '兒童', '孩子', '小孩', '潛水')):
    return True
  return False


def is_generic_activity_restart_request(text):
  compact = re.sub(r'\s+', '', text or '')
  if not compact:
    return False
  if any(district in compact for district in DISTRICTS) or contains_known_tag(compact):
    return False
  if is_lifestyle_activity_query(compact):
    return False
  return compact in {
    '找活動',
    '幫我找活動',
    '幫我找一下活動',
    '推薦活動',
    '推薦一下活動',
    '有活動嗎',
    '有什麼活動',
    '看看活動',
  }


# 判斷是否為生活情境活動查詢（帶小孩/雨天/約會）
def is_lifestyle_activity_query(text):
  compact = re.sub(r'\s+', '', text or '')
  if not compact:
    return False
  if has_child_lifestyle_intent(compact):
    return True
  if has_rainy_lifestyle_intent(compact):
    return True
  if has_date_lifestyle_intent(compact):
    return True
  return False


# 判斷訊息是否有帶小孩出門的活動意圖
def has_child_lifestyle_intent(compact):
  return (
    any(term in (compact or '') for term in CHILD_AUDIENCE_TERMS)
    and any(term in (compact or '') for term in CHILD_ACTIVITY_CONTEXT_TERMS)
  )


# 判斷訊息是否有雨天找室內活動的意圖
def has_rainy_lifestyle_intent(compact):
  return (
    any(term in (compact or '') for term in RAINY_ACTIVITY_TERMS)
    and any(term in (compact or '') for term in ('去哪', '哪裡', '活動', '推薦', '想找'))
  )


# 判斷訊息是否有約會找活動的意圖
def has_date_lifestyle_intent(compact):
  return (
    any(term in (compact or '') for term in DATE_ACTIVITY_TERMS)
    and any(term in (compact or '') for term in ('約會', '去哪', '哪裡', '活動', '推薦', '想找'))
  )


# 建立查詢說明訊息，告訴使用者如何查詢活動
def build_query_help_message():
  return TextSendMessage(
    text='我可以用活動資料庫幫你找桃園行程，也能延續上一輪結果回答費用、地點、報名和時間。\n'
         '你可以直接說「要去中壢玩」、「泥巴相關活動」或「週末親子活動」。'
  )


def out_of_taoyuan_query(text):
  compact = re.sub(r'\s+', '', text or '')
  if not compact or any(term in compact for term in ('桃園', '桃市')):
    return False
  return any(term in compact for term in OUT_OF_TAOYUAN_TERMS)


def build_scope_limit_message():
  return TextSendMessage(text='目前我只查得到桃園活動資料。你可以改問「桃園展覽」「中壢週末活動」或「親子活動」。')


def is_activity_followup_question(text):
  compact = re.sub(r'\s+', '', text or '')
  if not compact:
    return False
  followup_terms = (
    '這個', '這些', '剛剛', '那個', '那些', '要錢', '免費', '費用', '票價',
    '門票', '票錢', '多少錢', '收費', '要付費', '要購票', '要買票',
    '需要報名', '要報名', '報名', '在哪', '哪裡', '地點', '地址',
    '什麼時候', '時間', '幾點', '遠不遠', '會不會很遠', '很遠', '距離',
    '適合小孩', '適合親子', '小孩適合',
    '在幹嘛', '在幹麻', '幹嘛', '幹麻', '做什麼', '玩什麼', '內容', '介紹', '是什麼',
  )
  return any(term in compact for term in followup_terms)


def is_activity_attribute_followup_question(text):
  compact = re.sub(r'\s+', '', text or '')
  if not compact:
    return False
  attribute_terms = (
    '免費', '要錢', '費用', '票價', '門票', '票錢', '多少錢', '收費', '要付費', '要購票', '要買票',
    '需要報名', '要報名', '報名', '在哪', '哪裡', '地點', '地址',
    '什麼時候', '時間', '幾點', '哪天', '遠不遠', '會不會很遠', '很遠', '距離',
    '適合小孩', '適合親子', '小孩適合', '親子適合',
  )
  return any(term in compact for term in attribute_terms)


def ordinal_out_of_range_message(index, activities):
  return TextSendMessage(text=f'上一輪只有 {len(activities)} 個活動，沒有第 {index + 1} 個。你可以說「更多」看下一批。')


def context_activities(state):
  ids = [activity_id for activity_id in (state.last_activity_ids or []) if activity_id]
  if not ids:
    return []
  by_id = {activity.id: activity for activity in Activity.objects.filter(id__in=ids).prefetch_related('tags')}
  return [by_id[activity_id] for activity_id in ids if activity_id in by_id]


def ordinal_context_index(text):
  compact = re.sub(r'\s+', '', text or '')
  if not compact:
    return None
  ordinal_words = {
    '一': 0, '1': 0, '壹': 0,
    '二': 1, '兩': 1, '2': 1, '貳': 1,
    '三': 2, '3': 2, '參': 2,
    '四': 3, '4': 3, '肆': 3,
    '五': 4, '5': 4, '伍': 4,
  }
  match = re.search(r'第([一二兩三四五壹貳參肆伍1-5])(?:個|張|項|則|筆)?', compact)
  if match:
    return ordinal_words.get(match.group(1))
  match = re.search(r'([1-5])(?:個|張|項|則|筆)', compact)
  if match:
    return ordinal_words.get(match.group(1))
  return None


def choose_context_activity(text, activities):
  if not activities:
    return None
  compact = re.sub(r'\s+', '', text or '')
  ordinal_index = ordinal_context_index(compact)
  if ordinal_index is not None and 0 <= ordinal_index < len(activities):
    return activities[ordinal_index]
  for activity in activities:
    title = re.sub(r'\s+', '', activity.title or '')
    if title and (title in compact or any(len(part) >= 4 and part in compact for part in re.split(r'[：:「」（）()\\-－]', title))):
      return activity
  if has_new_subject_with_description_phrase(compact):
    return None
  return activities[0] if len(activities) == 1 or any(term in compact for term in ('這個', '那個')) else None


def has_new_subject_with_description_phrase(text):
  compact = re.sub(r'\s+', '', text or '')
  if not compact or any(term in compact for term in ('這個', '那個', '剛剛', '上一個', '上一張')):
    return False
  description_terms = ('在幹嘛', '在幹麻', '幹嘛', '幹麻', '做什麼', '玩什麼', '內容', '介紹', '是什麼')
  if not any(term in compact for term in description_terms):
    return False
  subject = compact
  for term in description_terms:
    subject = subject.replace(term, '')
  subject = subject.replace('活動', '').strip()
  return len(subject) >= 2


def context_activity_payload(activity):
  return {
    'id': activity.id,
    'title': activity.title,
    'district': activity.district,
    'time': format_time_range(activity),
    'tags': [tag.name for tag in activity.tags.all()[:5]],
    'summary': (activity.ai_summary or activity.description or '')[:120],
  }


def route_line_context_with_ai(user, text, state, activities):
  if not state or not activities:
    return None
  fallback_intent = 'refine_search' if looks_like_refinement(text) else ('activity_followup' if is_activity_followup_question(text) else None)
  started_at = time.monotonic()
  try:
    response = call_json_with_fallback(
      payload_messages(
        '你是桃園活動 LINE 助手的上下文路由器，只輸出 JSON，不要解釋。'
        '你的任務是判斷使用者本輪訊息是在追問上一輪活動卡片、延續上一輪條件重新搜尋、開始新搜尋、查看更多，或不支援。'
        'activity_followup 只能用於使用者明確問上一輪某個活動的時間、地點、費用、報名、內容、適合對象等細節。'
        'refine_search 用於「大園的呢」「免費的呢」「週末的呢」這類把上一輪查詢加上新條件的句子。'
        '「不要親子」「不是展覽」這種負面條件放進 exclude_tag_names，不要放進 tag_names。'
        '「第二個呢」這種追問用 target_activity_index 指向上一輪第幾張卡片。'
        '如果使用者改問明顯不同的新活動或新主題，回 new_search 並設定 replace_previous_query=true。'
        '不要把整段對話合併成 keyword；只回結構化 refine_patch。',
        {
          'message': text,
          'previous_query': state.last_query,
          'previous_conditions': deserialize_conditions(state.conditions or {}),
          'previous_activities': [context_activity_payload(activity) for activity in activities[:5]],
          'allowed_intents': ['activity_followup', 'refine_search', 'new_search', 'more_results', 'unsupported_chat'],
          'output_schema': {
            'intent': 'one allowed intent',
            'target_activity_id': 'integer id from previous_activities when intent is activity_followup, otherwise null',
            'target_activity_index': '1-based card index from previous_activities when user says 第一個/第二個/etc, otherwise null',
            'followup_field': 'one of time, location, distance, fee, registration, description, suitability, or none',
            'replace_previous_query': 'true when new_search should ignore previous query and conditions',
            'refine_patch': {
              'district': 'one Taoyuan district without 區, or empty string',
              'tag_names': 'array of existing tag names',
              'exclude_tag_names': 'array of existing tag names the user explicitly does not want',
              'is_free': 'true, false, or null',
              'keyword': 'short keyword only if needed',
              'soft_topics': 'array',
              'related_terms': 'array',
            },
          },
        },
      )
    )
    parsed = response.parsed or {}
    intent = str(parsed.get('intent') or '').strip()
    if intent not in {'activity_followup', 'refine_search', 'new_search', 'more_results', 'unsupported_chat'}:
      intent = fallback_intent or ''
    if fallback_intent == 'activity_followup' and intent in {'unsupported_chat', 'new_search'}:
      intent = 'activity_followup'
    refine_patch = normalize_ai_conditions(parsed.get('refine_patch') or {}, fallback={}, user=user, query=text)
    raw_excluded = (parsed.get('refine_patch') or {}).get('exclude_tag_names') or []
    if isinstance(raw_excluded, str):
      raw_excluded = [raw_excluded]
    allowed_tags = set(Tag.objects.filter(is_active=True).values_list('name', flat=True))
    exclude_tag_names = []
    for name in raw_excluded:
      tag_name = str(name).strip().lstrip('#')
      if tag_name in allowed_tags and tag_name not in exclude_tag_names:
        exclude_tag_names.append(tag_name)
    if exclude_tag_names:
      refine_patch['exclude_tag_names'] = exclude_tag_names
    route = {
      'intent': intent,
      'target_activity_id': parsed.get('target_activity_id'),
      'target_activity_index': parsed.get('target_activity_index'),
      'followup_field': str(parsed.get('followup_field') or '').strip(),
      'replace_previous_query': bool(parsed.get('replace_previous_query')),
      'refine_patch': refine_patch,
    }
    log_ai_processing(
      task_type='condition_extract',
      user=user,
      input_summary=f'context-route:{text}',
      output_json={'route': route, 'provider': response.provider},
      latency_ms=elapsed_ms(started_at),
      status='success',
      model=f'{response.provider}:{response.model}',
      prompt_version='line-context-route-v1',
    )
    return route
  except Exception as exc:
    log_ai_processing(
      task_type='condition_extract',
      user=user,
      input_summary=f'context-route:{text}',
      output_json={'intent': fallback_intent or 'fallback'},
      latency_ms=elapsed_ms(started_at),
      status='failed',
      error=str(exc),
      model='rule',
      prompt_version='line-context-route-v1',
    )
    return {'intent': fallback_intent} if fallback_intent else None


def pick_routed_activity(route, text, activities):
  target_index = (route or {}).get('target_activity_index')
  if target_index:
    try:
      index = int(target_index) - 1
    except (TypeError, ValueError):
      index = None
    if index is not None and 0 <= index < len(activities):
      return activities[index]
  target_id = (route or {}).get('target_activity_id')
  if target_id:
    for activity in activities:
      if str(activity.id) == str(target_id):
        return activity
  return choose_context_activity(text, activities)


def build_ai_activity_detail_reply(user, text, activity):
  html_text = raw_html_text_for_activity(activity, limit=3500)
  if not html_text and not (activity.ocr_summary or activity.ocr_text):
    return None
  source_text = re.sub(
    r'\s+',
    ' ',
    ' '.join(
      part
      for part in (
        activity.description,
        activity.ai_summary,
        activity.ocr_summary,
        activity.ocr_text,
        html_text,
      )
      if part
    ),
  ).strip()
  if not source_text:
    return None
  started_at = time.monotonic()
  try:
    response = call_text_with_fallback([
      {
        'role': 'system',
        'content': (
          '你是桃園活動 LINE 助手。請用繁體中文回答使用者對單一活動的追問，最多 120 字。'
          '只能根據提供的 Activity 欄位、OCR 與本機 HTML 文字回答；不知道就說目前資料沒有寫清楚。'
          '不要編造日期、地點、費用、報名方式。'
        ),
      },
      {
        'role': 'user',
        'content': json.dumps(
          {
            'question': text,
            'activity': context_activity_payload(activity),
            'known_fields': {
              'time': format_time_range(activity),
              'location': f'{activity.district or "桃園"} {activity.location or ""}'.strip(),
              'fee': activity.fee_description or '',
              'registration': activity.registration_info or '',
              'detail_url': safe_detail_url(activity),
            },
            'source_text': source_text[:4000],
          },
          ensure_ascii=False,
          default=str,
        ),
      },
    ])
    answer = re.sub(r'\s+', ' ', (response.raw_text or '').strip())
    if not answer:
      return None
    if len(answer) > 160:
      answer = answer[:160].rstrip('，,。 ') + '。'
    log_ai_processing(
      task_type='rerank',
      user=user,
      input_summary=f'activity-followup:{activity.id}:{text}',
      output_json={'text': answer, 'provider': response.provider, 'used_html': bool(html_text)},
      latency_ms=elapsed_ms(started_at),
      status='success',
      model=f'{response.provider}:{response.model}',
      prompt_version='line-activity-followup-v1',
    )
    return TextSendMessage(text=answer)
  except Exception as exc:
    log_ai_processing(
      task_type='rerank',
      user=user,
      input_summary=f'activity-followup:{activity.id}:{text}',
      output_json={'fallback': True, 'used_html': bool(html_text)},
      latency_ms=elapsed_ms(started_at),
      status='failed',
      error=str(exc),
      model='rule',
      prompt_version='line-activity-followup-v1',
    )
    return None


def build_activity_description_reply(activity):
  summary = compact_activity_summary(activity, limit=160)
  title = activity.title or '這個活動'
  detail_url = safe_detail_url(activity)
  tag_names = [tag.name for tag in activity.tags.all()[:4]]
  known_parts = [
    f'時間：{format_time_range(activity)}',
    f'地點：{(activity.district or "桃園")} {activity.location or "活動現場"}'.strip(),
  ]
  if tag_names:
    known_parts.append(f'類型：{"、".join(tag_names)}')
  if detail_url:
    known_parts.append(f'詳情：{detail_url}')

  if summary and summary != title:
    return TextSendMessage(text=f'{title}：{summary}\n' + '\n'.join(known_parts))
  return TextSendMessage(text=f'{title}：目前資料庫沒有更完整的活動內容摘要，我先列出已知資訊。\n' + '\n'.join(known_parts))


def answer_activity_followup(user, text, state, route=None, activities=None):
  activities = activities if activities is not None else (context_activities(state) if state else [])
  if not activities:
    return None
  compact = re.sub(r'\s+', '', text or '')
  activity = pick_routed_activity(route, text, activities) if route else choose_context_activity(text, activities)
  followup_field = str((route or {}).get('followup_field') or '').strip()
  target = activity or activities[0]

  if followup_field in {'description', 'content'}:
    ai_reply = build_ai_activity_detail_reply(user, text, target)
    if ai_reply:
      return ai_reply
    return build_activity_description_reply(target)

  if followup_field == 'fee':
    fee = target.fee_description or ('免費' if target.is_free else '費用未明確標示')
    return TextSendMessage(text=f'{target.title}：{fee}。實際費用以官方頁為準。')

  if followup_field == 'registration':
    if target.requires_registration:
      info = target.registration_info or '需要報名'
      return TextSendMessage(text=f'{target.title}：{info}。')
    return TextSendMessage(text=f'{target.title}：目前資料沒有顯示必須報名，建議出發前再看官方頁確認。')

  if followup_field == 'location':
    location = f'{target.district or "桃園"} {target.location or "地點請見官方頁"}'.strip()
    return TextSendMessage(text=f'{target.title}：地點是 {location}。')

  if followup_field == 'distance':
    location = f'{target.district or "桃園"} {target.location or "地點請見官方頁"}'.strip()
    return TextSendMessage(text=f'{target.title} 在 {location}。目前沒有你的出發地，距離建議點卡片的「導航前往地點」確認。')

  if followup_field == 'time':
    return TextSendMessage(text=f'{target.title}：{format_time_range(target)}。')

  if followup_field == 'suitability':
    tag_names = {tag.name for tag in target.tags.all()}
    text_blob = f'{target.title} {target.description} {target.ai_summary}'
    suitable = bool({'親子', '兒童'}.intersection(tag_names) or any(term in text_blob for term in CHILD_AUDIENCE_TERMS))
    if suitable:
      return TextSendMessage(text=f'{target.title}：目前資料看起來適合親子或小孩參加，仍建議看官方頁確認年齡限制。')
    return TextSendMessage(text=f'{target.title}：目前資料沒有明確標示親子或兒童適合，建議先看官方頁確認。')

  if any(term in compact for term in ('在幹嘛', '在幹麻', '幹嘛', '幹麻', '做什麼', '玩什麼', '內容', '介紹', '是什麼')):
    ai_reply = build_ai_activity_detail_reply(user, text, target)
    if ai_reply:
      return ai_reply
    return build_activity_description_reply(target)

  if any(term in compact for term in ('免費', '要錢', '費用', '票價')):
    targets = [activity] if activity else activities
    free_items = [item for item in targets if item.is_free]
    unknown_items = [item for item in targets if not item.is_free and (item.fee_type or 'unknown') == 'unknown' and not item.fee_description]
    if '這些' in compact or not activity:
      parts = []
      if free_items:
        parts.append(f'明確標示免費：{"、".join(item.title for item in free_items[:3])}')
      if unknown_items:
        parts.append(f'費用未明確標示：{"、".join(item.title for item in unknown_items[:3])}')
      if parts:
        return TextSendMessage(text=f'上一輪結果裡，{"；".join(parts)}。實際費用仍以官方頁為準。')
      return TextSendMessage(text='上一輪結果裡目前沒有明確標示免費的活動，費用請以官方頁為準。')
    fee = activity.fee_description or ('免費' if activity.is_free else '費用未明確標示')
    return TextSendMessage(text=f'{activity.title}：{fee}。實際費用以官方頁為準。')

  if any(term in compact for term in ('門票', '票錢', '多少錢', '收費', '要付費', '要購票', '要買票', '買票')):
    target = activity or activities[0]
    fee = target.fee_description or ('免費' if target.is_free else '費用未明確標示')
    return TextSendMessage(text=f'{target.title}：{fee}。實際費用以官方頁為準。')

  if any(term in compact for term in ('需要報名', '要報名', '報名')):
    target = activity or activities[0]
    if target.requires_registration:
      info = target.registration_info or '需要報名'
      return TextSendMessage(text=f'{target.title}：{info}。')
    return TextSendMessage(text=f'{target.title}：目前資料沒有顯示必須報名，建議出發前再看官方頁確認。')

  if any(term in compact for term in ('在哪', '哪裡', '地點', '地址')):
    target = activity or activities[0]
    location = f'{target.district or "桃園"} {target.location or "地點請見官方頁"}'.strip()
    return TextSendMessage(text=f'{target.title}：地點是 {location}。')

  if any(term in compact for term in ('遠不遠', '會不會很遠', '很遠', '距離')):
    target = activity or activities[0]
    location = f'{target.district or "桃園"} {target.location or "地點請見官方頁"}'.strip()
    return TextSendMessage(text=f'{target.title} 在 {location}。目前沒有你的出發地，距離建議點卡片的「導航前往地點」確認。')

  if any(term in compact for term in ('什麼時候', '時間', '幾點', '哪天')):
    target = activity or activities[0]
    return TextSendMessage(text=f'{target.title}：{format_time_range(target)}。')

  if any(term in compact for term in ('適合小孩', '小孩適合', '適合親子', '親子適合')):
    target = activity or activities[0]
    tag_names = {tag.name for tag in target.tags.all()}
    text_blob = f'{target.title} {target.description} {target.ai_summary}'
    suitable = bool({'親子', '兒童'}.intersection(tag_names) or any(term in text_blob for term in CHILD_AUDIENCE_TERMS))
    if suitable:
      return TextSendMessage(text=f'{target.title}：目前資料看起來適合親子或小孩參加，仍建議看官方頁確認年齡限制。')
    return TextSendMessage(text=f'{target.title}：目前資料沒有明確標示親子或兒童適合，建議先看官方頁確認。')

  return None


# 處理 LINE 文字訊息主流程（含指令偵測、意圖分類、活動搜尋）
def handle_line_text_message(user, text):
  text = (text or '').strip()
  if text in CLEAR_CONTEXT_COMMANDS:
    LineConversationState.objects.filter(user=user).delete()
    return TextSendMessage(text='已清除搜尋記錄，請重新輸入你想找的活動。')

  if text in PREFERENCE_COMMANDS:
    return build_preference_message(user)

  if text in RECOMMENDATION_COMMANDS:
    activities = get_recommended_activities(user, limit=3, exclude_subscribed=True)
    log_card_views(user, activities, source='line_recommendation', query=text)
    save_conversation_state(user, 'recommendation', text, {'mode': 'recommendation'}, activities, offset=len(activities))
    return build_activity_carousel_message(
      activities,
      alt_text='為您奉上專屬活動推薦！',
      user=user,
      query_context='推薦活動',
      include_intro=True,
    )

  if text in SUBSCRIPTION_COMMANDS:
    activities = get_active_subscribed_activities(user, limit=10)
    log_card_views(user, activities, source='line_subscriptions', query=text)
    if not activities:
      return TextSendMessage(text='目前沒有尚未結束的訂閱活動。看到喜歡的活動可以點「訂閱此活動通知」。')
    save_conversation_state(user, 'subscriptions', text, {'mode': 'subscriptions'}, activities, offset=len(activities))
    return build_activity_carousel_message(
      activities,
      alt_text='您已訂閱的活動',
      user=user,
      query_context='已訂閱活動',
      include_intro=True,
    )

  if out_of_taoyuan_query(text):
    return build_scope_limit_message()

  state = get_valid_conversation_state(user)
  context_items = context_activities(state) if state else []
  if state and is_generic_activity_restart_request(text):
    state = None
    context_items = []
  if context_items:
    ordinal_index = ordinal_context_index(text)
    if ordinal_index is not None:
      if ordinal_index >= len(context_items):
        return ordinal_out_of_range_message(ordinal_index, context_items)
      if is_activity_attribute_followup_question(text) or is_activity_followup_question(text):
        followup_message = answer_activity_followup(user, text, state, activities=context_items)
      else:
        followup_message = answer_activity_followup(
          user,
          text,
          state,
          route={'target_activity_index': ordinal_index + 1, 'followup_field': 'description'},
          activities=context_items,
        )
      if followup_message:
        return followup_message
  if state and rule_classify_line_intent(text, state=state) == 'more_results':
    return handle_more_results_text(user, text, state)
  if context_items:
    if is_activity_attribute_followup_question(text) or (is_activity_followup_question(text) and choose_context_activity(text, context_items)):
      followup_message = answer_activity_followup(user, text, state, activities=context_items)
      if followup_message:
        return followup_message
    route = route_line_context_with_ai(user, text, state, context_items)
    route_intent = (route or {}).get('intent')
    if route_intent == 'activity_followup':
      followup_message = answer_activity_followup(user, text, state, route=route, activities=context_items)
      if followup_message:
        return followup_message
    if route_intent == 'refine_search':
      return handle_refined_search_text(user, text, state, patch=(route or {}).get('refine_patch') or {})
    if route_intent == 'more_results':
      return handle_more_results_text(user, text, state)
    if route_intent == 'new_search':
      patch = (route or {}).get('refine_patch') or {}
      if (route or {}).get('replace_previous_query') and patch:
        activities, conditions = search_activities_for_line(user, text, limit=3, conditions=patch, return_conditions=True)
        log_card_views(user, activities, source='line_new_query', query=text)
        if activities:
          save_conversation_state(user, 'activity_search', text, conditions, activities, offset=len(activities))
        return build_activity_carousel_message(
          activities,
          alt_text='桃園活動查詢結果',
          user=user,
          query_context=text,
          include_intro=True,
        )
      state = None
    elif route_intent == 'unsupported_chat' and not is_activity_query(text):
      return build_query_help_message()
  elif state and is_activity_followup_question(text):
    followup_message = answer_activity_followup(user, text, state)
    if followup_message:
      return followup_message

  intent = classify_line_intent(user, text, state=state)
  if intent == 'more_results':
    return handle_more_results_text(user, text, state)
  if intent == 'refine_search':
    return handle_refined_search_text(user, text, state)
  if intent == 'preference_help':
    return build_preference_message(user)
  if intent == 'subscription_help':
    activities = get_active_subscribed_activities(user, limit=10)
    if not activities:
      return TextSendMessage(text='目前沒有尚未結束的訂閱活動。看到喜歡的活動可以點「訂閱此活動通知」。')
    return build_activity_carousel_message(activities, alt_text='您已訂閱的活動', user=user, query_context='已訂閱活動', include_intro=True)
  if intent != 'activity_search':
    return build_query_help_message()

  activities, conditions = search_activities_for_line(user, text, limit=3, return_conditions=True)
  log_card_views(user, activities, source='line_ai_query', query=text)
  if activities:
    save_conversation_state(user, 'activity_search', text, conditions, activities, offset=len(activities))
  return build_activity_carousel_message(
    activities,
    alt_text='桃園活動查詢結果',
    user=user,
    query_context=text,
    include_intro=True,
  )


# 處理使用者要求「查看更多」的文字指令，延續上一輪查詢
def handle_more_results_text(user, text, state):
  if not state:
    activities = get_recommended_activities(user, limit=3, exclude_subscribed=True)
    log_card_views(user, activities, source='line_more_without_context', query=text)
    save_conversation_state(user, 'recommendation', '推薦活動', {'mode': 'recommendation'}, activities, offset=len(activities))
    return build_activity_carousel_message(activities, alt_text='更多桃園活動', user=user, query_context='推薦活動', include_intro=True)

  offset = state.offset or len(state.last_activity_ids or []) or 3
  conditions = deserialize_conditions(state.conditions or {})
  if conditions.get('mode') == 'recommendation' or state.intent == 'recommendation':
    activities = get_recommended_activities(user, limit=3, offset=offset, exclude_subscribed=True, exclude_recently_seen=True)
    query = '推薦活動'
    next_conditions = {'mode': 'recommendation'}
  else:
    query = state.last_query or text
    activities, next_conditions = search_activities_for_line(
      user,
      query,
      limit=3,
      offset=offset,
      conditions=conditions,
      return_conditions=True,
    )
  record_action(user, None, 'view_more', {'source': 'line_text', 'query': state.last_query, 'offset': offset})
  log_card_views(user, activities, source='line_text_more', query=state.last_query)
  if activities:
    save_conversation_state(user, state.intent or 'activity_search', query, next_conditions, activities, offset=offset + len(activities))
  return build_activity_carousel_message(activities, alt_text='更多桃園活動', user=user, query_context=query, offset=offset, include_intro=True)


# 處理搜尋精煉文字（在上一輪查詢基礎上加入新條件）
def handle_refined_search_text(user, text, state, patch=None):
  base_conditions = deserialize_conditions(state.conditions or {}) if state else {}
  effective_patch = patch if patch is not None else extract_conditions_from_message(user, text)
  effective_patch = supplement_refine_patch_from_text(text, base_conditions, effective_patch)
  reset_query_context = bool(base_conditions.get('mode')) or should_replace_context_query(text, base_conditions, effective_patch)
  if reset_query_context:
    base_conditions = {}
  refined = merge_search_conditions(base_conditions, effective_patch)
  query = text if reset_query_context else combine_context_query(state.last_query if state else '', text)
  activities, conditions = search_activities_for_line(
    user,
    query,
    limit=3,
    conditions=refined,
    return_conditions=True,
  )
  log_card_views(user, activities, source='line_refine_query', query=query)
  if activities:
    save_conversation_state(user, 'activity_search', query, conditions, activities, offset=len(activities))
  return build_activity_carousel_message(activities, alt_text='桃園活動查詢結果', user=user, query_context=query, include_intro=True)


# 用 AI 分類使用者訊息意圖（規則型為備援）
def classify_line_intent(user, text, state=None):
  fallback = rule_classify_line_intent(text, state=state)
  # Deterministic control phrases should not be overridden by the model.
  if fallback == 'more_results':
    return fallback
  if fallback == 'activity_search' and high_confidence_activity_query(text):
    return fallback
  started_at = time.monotonic()
  try:
    response = call_json_with_fallback(
      payload_messages(
        '你是桃園活動 LINE 助手的 intent 分類器。只輸出 JSON，不要解釋。'
        '如果使用者是在找活動或延續上一輪查詢，就分類到 activity_search/refine_search/more_results；'
        '一般聊天不回答，分類到 unsupported_chat。',
        {
          'message': text,
          'has_recent_context': bool(state),
          'recent_intent': state.intent if state else '',
          'recent_query': state.last_query if state else '',
          'allowed_intents': [
            'activity_search',
            'more_results',
            'refine_search',
            'preference_help',
            'subscription_help',
            'unsupported_chat',
          ],
          'output_schema': {'intent': 'one allowed intent'},
        },
      )
    )
    intent = normalize_line_intent((response.parsed or {}).get('intent'), fallback)
    log_ai_processing(
      task_type='condition_extract',
      user=user,
      input_summary=f'intent:{text}',
      output_json={'intent': intent, 'fallback': fallback, 'provider': response.provider},
      latency_ms=elapsed_ms(started_at),
      status='success',
      model=f'{response.provider}:{response.model}',
      prompt_version='line-intent-v1',
    )
    return intent
  except Exception as exc:
    log_ai_processing(
      task_type='condition_extract',
      user=user,
      input_summary=f'intent:{text}',
      output_json={'intent': fallback, 'provider': 'rule'},
      latency_ms=elapsed_ms(started_at),
      status='failed',
      error=str(exc),
      model='rule',
      prompt_version='line-intent-v1',
    )
    return fallback


# 驗證意圖字串是否合法，不合法時回傳 fallback
def normalize_line_intent(value, fallback):
  intent = str(value or '').strip()
  allowed = {'activity_search', 'more_results', 'refine_search', 'preference_help', 'subscription_help', 'unsupported_chat'}
  return intent if intent in allowed else fallback


# 用規則快速分類使用者意圖（不呼叫 AI）
def rule_classify_line_intent(text, state=None):
  normalized = re.sub(r'\s+', '', (text or '').strip().lower())
  if not normalized:
    return 'unsupported_chat'
  if any(word in normalized for word in MORE_RESULT_WORDS):
    return 'more_results' if state else 'activity_search'
  if any(word in normalized for word in ('偏好', '喜好', '設定')):
    return 'preference_help'
  if '訂閱' in normalized and not is_activity_query(text):
    return 'subscription_help'
  if is_activity_query(text) or contains_known_tag(text):
    return 'activity_search'
  return 'unsupported_chat'


# 判斷短文字是否為針對上一輪結果的搜尋精煉（如「免費的呢」）
def looks_like_refinement(text):
  compact = re.sub(r'\s+', '', text or '')
  if not compact:
    return False
  if compact.endswith('呢') or compact.endswith('的呢'):
    return True
  if len(compact) <= 10 and (
    any(district in compact for district in DISTRICTS)
    or any(word in compact for word in ('免費', '親子', '週末', '周末', '今天', '明天', '不要太遠', '附近'))
    or contains_known_tag(compact)
  ):
    return True
  return False


# 判斷文字是否包含資料庫中已知的有效標籤
def contains_known_tag(text):
  if not text:
    return False
  return Tag.objects.filter(is_active=True, name__in=[tag for tag in Tag.objects.filter(is_active=True).values_list('name', flat=True) if tag and tag in text]).exists()


# 合併上一輪與本輪查詢字串為完整查詢
def combine_context_query(previous, current):
  previous = (previous or '').strip()
  current = (current or '').strip()
  if not previous:
    return current
  if not current or previous == current or previous.endswith(f'，{current}'):
    return previous
  return f'{previous}，{current}'


def should_replace_context_query(text, base_conditions, patch):
  keyword = str((patch or {}).get('keyword') or '').strip()
  previous_keyword = str((base_conditions or {}).get('keyword') or '').strip()
  compact = re.sub(r'\s+', '', text or '')
  patch_tags = set((patch or {}).get('tag_names') or [])
  base_tags = set((base_conditions or {}).get('tag_names') or [])
  if patch_tags and not patch_tags.issubset(base_tags):
    if compact.startswith(('那', '那個', '不然', '換', '改', '算了')) or compact.endswith(('呢', '勒', '咧')):
      return True
  if not keyword or not previous_keyword or keyword == previous_keyword:
    return False
  if keyword not in compact:
    return False
  if has_new_subject_with_description_phrase(compact):
    return True
  if compact.startswith(('那', '那個', '不然', '換', '改')) or compact.endswith(('呢', '勒', '咧')):
    return True
  return False


def supplement_refine_patch_from_text(text, base_conditions, patch):
  patch = dict(patch or {})
  compact = re.sub(r'\s+', '', text or '')
  has_negative_tag_intent = any(term in compact for term in ('不要', '不想', '不看', '不是', '也不要'))
  rule_patch = rule_extract_conditions(text)
  rule_tags = rule_patch.get('tag_names') or []
  base_tags = set((base_conditions or {}).get('tag_names') or [])
  rule_has_new_tags = bool(rule_tags and not set(rule_tags).issubset(base_tags))
  if rule_has_new_tags and not patch.get('exclude_tag_names') and not has_negative_tag_intent:
    patch['tag_names'] = rule_tags
    patch['keyword'] = ''
    patch['soft_topics'] = rule_patch.get('soft_topics') or []
    patch['related_terms'] = rule_patch.get('related_terms') or []
  elif rule_tags and not patch.get('tag_names') and not patch.get('exclude_tag_names') and not has_negative_tag_intent:
    patch['tag_names'] = rule_tags
    if rule_patch.get('soft_topics'):
      patch['soft_topics'] = rule_patch.get('soft_topics')
    if rule_patch.get('related_terms'):
      patch['related_terms'] = rule_patch.get('related_terms')
  return patch


# 合併基底查詢條件與新的精煉條件（patch 優先覆蓋）
def merge_search_conditions(base, patch):
  merged = dict(base or {})
  patch = dict(patch or {})
  if patch.get('district'):
    merged['district'] = patch['district']
  if patch.get('is_free') is not None:
    merged['is_free'] = patch['is_free']
  if patch.get('keyword'):
    merged['keyword'] = patch['keyword']
  for key in ('soft_topics', 'related_terms', 'relax_order'):
    merged[key] = merge_query_terms((base or {}).get(key), patch.get(key), limit=24)
  for date_key in ('start_date', 'end_date'):
    if patch.get(date_key):
      merged[date_key] = patch[date_key]
  if patch.get('nearby_intent'):
    merged['nearby_intent'] = True
  tag_names = []
  for name in (base or {}).get('tag_names') or []:
    if name not in tag_names:
      tag_names.append(name)
  for name in patch.get('tag_names') or []:
    if name not in tag_names:
      tag_names.append(name)
  exclude_tag_names = []
  for name in (base or {}).get('exclude_tag_names') or []:
    if name not in exclude_tag_names:
      exclude_tag_names.append(name)
  for name in patch.get('exclude_tag_names') or []:
    if name not in exclude_tag_names:
      exclude_tag_names.append(name)
  merged['exclude_tag_names'] = exclude_tag_names
  merged['tag_names'] = [name for name in tag_names if name not in exclude_tag_names]
  return apply_nearby_preference(None, merged)


# 儲存使用者對話狀態（查詢意圖、條件、活動 ID），TTL 30 分鐘
def save_conversation_state(user, intent, query, conditions, activities, offset=0):
  if not user:
    return None
  expires_at = timezone.now() + timedelta(minutes=LINE_CONTEXT_TTL_MINUTES)
  state, _ = LineConversationState.objects.update_or_create(
    user=user,
    defaults={
      'intent': intent or '',
      'last_query': (query or '')[:300],
      'conditions': serialize_conditions(conditions or {}),
      'last_activity_ids': [activity.id for activity in activities if getattr(activity, 'id', None)],
      'offset': max(0, int(offset or 0)),
      'expires_at': expires_at,
    },
  )
  return state


# 取得尚未過期的使用者對話狀態
def get_valid_conversation_state(user):
  if not user:
    return None
  state = LineConversationState.objects.filter(user=user).first()
  if not state:
    return None
  if state.is_expired:
    state.delete()
    return None
  return state


# 序列化查詢條件為可儲存的 JSON（日期物件轉字串）
def serialize_conditions(conditions):
  result = {}
  for key, value in (conditions or {}).items():
    if key in {'start_date', 'end_date'} and hasattr(value, 'isoformat'):
      result[key] = value.isoformat()
    else:
      result[key] = value
  return result


# 反序列化查詢條件（ISO 字串轉回日期物件）
def deserialize_conditions(conditions):
  result = dict(conditions or {})
  for key in ('start_date', 'end_date'):
    value = result.get(key)
    if isinstance(value, str):
      parsed = parse_datetime(value)
      if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
      result[key] = parsed
  return result


# LINE 活動搜尋主流程（AI 條件提取→資料庫查詢→放寬策略→排序）
def search_activities_for_line(user, query, limit=3, offset=0, conditions=None, return_conditions=False):
  query = (query or '').strip()
  if not query:
    return ([], conditions or {}) if return_conditions else []

  conditions = deserialize_conditions(conditions) if conditions is not None else extract_conditions_from_message(user, query)
  if force_no_result_query(query, conditions):
    return ([], conditions) if return_conditions else []
  pool_size = max(30, limit + offset + 10)
  candidates = query_activities_by_conditions(conditions, limit=pool_size)
  
  if not candidates:
    # If no results and it was strict, try relaxing immediately
    relaxed_conditions = dict(conditions)
    relaxed_conditions['strict_topics'] = []
    candidates = query_activities_by_conditions(relaxed_conditions, limit=pool_size)
  if not candidates and not semantic_terms_from_conditions(conditions):
    candidates = search_activities_by_rules(query, limit=pool_size)
  if not candidates:
    candidates, notice = relaxed_search_activities(user, conditions, query, limit=pool_size)
  else:
    notice = ''
  if not candidates:
    return ([], conditions) if return_conditions else []

  candidates = dedupe_activities_by_business_key(candidates)
  ranked = rank_activities_for_user(user, candidates)
  if notice:
    for activity in ranked:
      activity._line_notice = notice
  target_size = limit + offset
  exact_keyword_matches = exact_keyword_title_matches(ranked, conditions)
  if len(ranked) > target_size:
    ai_limit = min(len(ranked), target_size + 10)
    ranked = rerank_activities_with_ai(user, query, ranked, limit=ai_limit) or ranked
    ranked = rotate_recently_seen_activities(user, ranked)
  if has_new_subject_with_description_phrase(query):
    strict_ranked = [activity for activity in ranked if activity_matches_keyword_subject(activity, conditions)]
    if strict_ranked:
      ranked = strict_ranked
  ranked = promote_exact_keyword_title_matches(ranked, conditions, exact_keyword_matches)
  if strict_district_requested(query, conditions):
    district = conditions.get('district') or ''
    ranked = [activity for activity in ranked if district in (activity.district or '')]
  result = ranked[offset:offset + limit]
  return (result, conditions) if return_conditions else result


def activity_matches_keyword_subject(activity, conditions):
  keyword = re.sub(r'\s+', '', str((conditions or {}).get('keyword') or ''))
  if len(keyword) < 2:
    return True
  terms = [keyword]
  if keyword.endswith('展') and len(keyword) > 2:
    terms.append(keyword[:-1])
  blob = re.sub(r'\s+', '', activity_search_blob(activity))
  return any(term and term in blob for term in terms)


def exact_keyword_title_matches(activities, conditions):
  keyword = re.sub(r'\s+', '', str((conditions or {}).get('keyword') or ''))
  if len(keyword) < 2:
    return []
  exact = []
  for activity in activities:
    title = re.sub(r'\s+', '', activity.title or '')
    if title and (keyword in title or title in keyword):
      exact.append(activity)
  return exact


def promote_exact_keyword_title_matches(activities, conditions, promoted=None):
  exact = []
  seen_exact_ids = set()
  for activity in (promoted or []):
    activity_id = getattr(activity, 'id', None)
    if activity_id not in seen_exact_ids:
      exact.append(activity)
      seen_exact_ids.add(activity_id)
  for activity in exact_keyword_title_matches(activities, conditions):
    activity_id = getattr(activity, 'id', None)
    if activity_id not in seen_exact_ids:
      exact.append(activity)
      seen_exact_ids.add(activity_id)
  if not exact:
    return activities
  others = []
  for activity in activities:
    if getattr(activity, 'id', None) not in seen_exact_ids:
      others.append(activity)
  return exact + others


# 建立活動輪播 LINE 訊息（可選含引言文字）
def build_activity_carousel_message(
  activities,
  alt_text='桃園活動推薦',
  focus_tag=None,
  user=None,
  query_context='推薦活動',
  offset=0,
  include_intro=False,
):
  if not activities:
    return build_no_result_message(query_context)
  carousel = FlexSendMessage(
    alt_text=alt_text,
    contents=build_activity_carousel(
      activities,
      focus_tag=focus_tag,
      user=user,
      query_context=query_context,
      offset=offset,
    ),
  )
  if include_intro:
    return [TextSendMessage(text=build_activity_intro_text(activities, query_context, user=user)), carousel]
  return carousel


# 建立無查詢結果的提示訊息
def build_no_result_message(query=''):
  suffix = f'「{query}」' if query else '目前條件'
  return TextSendMessage(text=f'目前沒有找到符合{suffix}的活動，可以改查地區、活動類型或免費活動。')


# 建立活動介紹引言文字（優先用 AI，失敗時用規則型備援）
def build_activity_intro_text(activities, query_context='推薦活動', user=None):
  count = len(activities)
  notice = next((getattr(activity, '_line_notice', '') for activity in activities if getattr(activity, '_line_notice', '')), '')
  if notice:
    return f'{notice}\n我先整理 {count} 個相近活動給你參考，詳細時間地點請以官方頁為準。'
  if any(getattr(activity, '_search_plan_score', 0) for activity in activities):
    return f'目前找到 {count} 個符合「{query_context}」的活動，詳細時間地點請以官方頁為準。'
  ai_intro = build_activity_intro_text_with_ai(activities, query_context, user=user)
  if ai_intro:
    return ai_intro
  if query_context == '推薦活動':
    preferred_regions = sorted(preferred_tag_sets(user)['region']) if user else []
    if preferred_regions:
      return f'依照你的偏好和常看地區（{"、".join(preferred_regions[:3])}），先推薦 {count} 個活動。'
    return f'依照你的偏好和近期活動，我先推薦 {count} 個活動。'
  if query_context == '已訂閱活動':
    return f'你目前有 {count} 個尚未結束的訂閱活動。'
  return f'我找到 {count} 個符合「{query_context}」的活動，先給你卡片參考。'


# 用 AI 產生活動介紹引言文字（1-2 句，最多 70 字）
def build_activity_intro_text_with_ai(activities, query_context='推薦活動', user=None):
  if not activities or query_context == '已訂閱活動':
    return ''
  started_at = time.monotonic()
  notice = next((getattr(activity, '_line_notice', '') for activity in activities if getattr(activity, '_line_notice', '')), '')
  candidates = [
    {
      'title': activity.title,
      'district': activity.district,
      'start_date': activity.start_date.date().isoformat() if activity.start_date else '',
      'summary': (activity.ai_summary or activity.description or '')[:80],
    }
    for activity in activities[:5]
  ]
  try:
    response = call_text_with_fallback([
      {
        'role': 'system',
        'content': (
          '你是桃園活動 LINE 助手。請用繁體中文回覆 1 到 2 句，最多 70 字。回覆時請使用正向活潑的詞語'
          '只能根據候選活動摘要說話，不可編造不存在的活動、日期、地點。'
          '如果 notice 空白，不能說沒有完全符合。'
          '使用者若有非相關的問題如「心情好差」「你會陪我聊天嗎」等，請溫和的拒絕此回答'
        ),
      },
      {
        'role': 'user',
        'content': json.dumps(
          {
            'query': query_context,
            'notice': notice,
            'activity_count': len(activities),
            'candidates': candidates,
          },
          ensure_ascii=False,
          default=str,
        ),
      },
    ])
    text = normalize_line_intro(response.raw_text)
    if not text:
      return ''
    log_ai_processing(
      task_type='rerank',
      user=user,
      input_summary=f'intro:{query_context}',
      output_json={'text': text, 'provider': response.provider},
      latency_ms=elapsed_ms(started_at),
      status='success',
      model=f'{response.provider}:{response.model}',
      prompt_version='line-intro-v1',
    )
    return text
  except Exception as exc:
    log_ai_processing(
      task_type='rerank',
      user=user,
      input_summary=f'intro:{query_context}',
      output_json={'fallback': True},
      latency_ms=elapsed_ms(started_at),
      status='failed',
      error=str(exc),
      prompt_version='line-intro-v1',
    )
    return ''


# 標準化並截斷 AI 產生的引言文字（最多 90 字）
def normalize_line_intro(text):
  text = re.sub(r'\s+', ' ', (text or '').strip())
  text = text.replace('沒有完全符合', '先整理')
  if len(text) > 90:
    text = text[:90].rstrip('，,。 ') + '。'
  return text


# 建立活動輪播 Flex 結構（最多 10 張卡片）
def build_activity_carousel(activities, focus_tag=None, user=None, query_context='推薦活動', offset=0):
  next_offset = offset + len(activities)
  for activity in activities:
    activity._line_user = user
  return {
    'type': 'carousel',
    'contents': [
      build_activity_bubble(
        activity,
        focus_tag=focus_tag,
        user=user,
        query_context=query_context,
        next_offset=next_offset,
      )
      for activity in activities[:10]
    ],
  }


# 建立單一活動 Flex Bubble 卡片（含圖片、標籤、時間、按鈕）
def build_activity_bubble(activity, focus_tag=None, user=None, query_context='推薦活動', next_offset=3):
  summary = compact_activity_summary(activity)
  district = activity.district or '桃園'
  location = activity.location or '活動現場'
  image_url = get_activity_image_url(activity)
  postback_base = f'activity_id={activity.id}'
  active_subscription = equivalent_subscription_for_activity(user, activity) if user else None
  action_buttons = [
    {'type': 'button', 'action': {'type': 'uri', 'label': 'ℹ️ 活動詳細資訊', 'uri': activity_detail_url(activity, user)}, 'style': 'secondary', 'height': 'sm'},
    {'type': 'button', 'action': {'type': 'uri', 'label': '🗺️ 導航前往地點', 'uri': tracked_maps_url(activity, user)}, 'style': 'secondary', 'height': 'sm'},
    {'type': 'button', 'action': {'type': 'uri', 'label': '📅 加入行事曆', 'uri': tracked_calendar_url(activity, user)}, 'style': 'secondary', 'height': 'sm'},
  ]
  if query_context == '已訂閱活動':
    action_buttons.append(cancel_subscription_button(active_subscription.activity if active_subscription else activity))
  elif active_subscription:
    action_buttons.append(cancel_subscription_button(active_subscription.activity, label='✅ 已訂閱 / 取消'))
  else:
    action_buttons.append({'type': 'button', 'action': {'type': 'postback', 'label': '🔔 訂閱此活動通知', 'data': f'action=subscribe_activity&{postback_base}'}, 'style': 'primary', 'color': '#1DB446', 'height': 'sm'})
  if query_context != '已訂閱活動':
    action_buttons.append(view_more_button(query_context, next_offset))
  return {
    'type': 'bubble',
    'size': 'mega',
    'hero': {
      'type': 'image',
      'url': image_url,
      'size': 'full',
      'aspectRatio': '20:13',
      'aspectMode': 'cover',
    },
    'body': {
      'type': 'box',
      'layout': 'vertical',
      'paddingAll': 'md',
      'contents': [
        *activity_notice_contents(activity),
        {'type': 'text', 'text': activity.title, 'weight': 'bold', 'size': 'md', 'wrap': True, 'maxLines': 2},
        {'type': 'box', 'layout': 'horizontal', 'margin': 'sm', 'spacing': 'xs', 'contents': build_tag_badges(activity, focus_tag, subscribed=bool(active_subscription))},
        {
          'type': 'box',
          'layout': 'vertical',
          'margin': 'md',
          'spacing': 'xs',
          'contents': [
            {'type': 'text', 'text': format_activity_time(activity), 'size': 'xs', 'color': '#666666', 'wrap': True},
            {'type': 'text', 'text': f'地點：[{district}] {location}', 'size': 'xs', 'color': '#666666', 'wrap': True},
          ],
        },
        {'type': 'text', 'text': summary, 'size': 'xs', 'color': '#444444', 'margin': 'md', 'wrap': True, 'maxLines': 3},
      ],
    },
    'footer': {
      'type': 'box',
      'layout': 'vertical',
      'spacing': 'sm',
      'contents': action_buttons,
    },
  }


# 建立活動注意事項內容（搜尋放寬提示，有才顯示）
def activity_notice_contents(activity):
  notice = getattr(activity, '_line_notice', '')
  if not notice:
    return []
  return [{
    'type': 'text',
    'text': notice,
    'size': 'xxs',
    'color': '#B45309',
    'wrap': True,
    'margin': 'none',
  }]


# 壓縮活動摘要文字至指定長度，超出則加省略號
def compact_activity_summary(activity, limit=SUMMARY_MAX_LENGTH):
  text = activity.ai_summary or activity.description or '暫無活動摘要介紹。'
  text = re.sub(r'\s+', ' ', text).strip()
  if len(text) <= limit:
    return text
  return text[:limit].rstrip() + '...'


# 取得活動安全圖片 URL，無效時依標籤或標題自動選備用圖
def get_activity_image_url(activity):
  if is_line_safe_image_url(activity.image_url) and not is_placeholder_image_url(activity.image_url):
    return activity.image_url
  for tag in activity.tags.all():
    image_urls = FALLBACK_IMAGE_BY_TAG.get(tag.name)
    if image_urls:
      return choose_fallback_image(activity, image_urls)
  inferred_key = infer_fallback_image_key(activity)
  if inferred_key:
    return choose_fallback_image(activity, FALLBACK_IMAGE_BY_TAG[inferred_key])
  return default_remote_image_url(activity)


# 判斷圖片 URL 是否符合 LINE API 要求（需 HTTPS 且純 ASCII）
def is_line_safe_image_url(url):
  if not url or not str(url).startswith('https://'):
    return False
  if not str(url).isascii():
    return False
  parsed = urllib.parse.urlparse(str(url))
  return bool(parsed.scheme == 'https' and parsed.netloc)


# 判斷是否為占位圖片 URL（placehold.co 等）
def is_placeholder_image_url(url):
  parsed = urllib.parse.urlparse(str(url))
  return parsed.netloc.lower() in PLACEHOLDER_IMAGE_HOSTS


# 依活動 id 輪流選取預設遠端圖片 URL
def default_remote_image_url(activity):
  if activity is None:
    return REMOTE_DEFAULT_IMAGES[0]
  seed = getattr(activity, 'id', None) or sum(ord(char) for char in (activity.title or ''))
  return REMOTE_DEFAULT_IMAGES[seed % len(REMOTE_DEFAULT_IMAGES)]


# 依活動 id 從備用圖片清單中循環選取一張
def choose_fallback_image(activity, image_urls):
  seed = getattr(activity, 'id', None) or sum(ord(char) for char in (activity.title or ''))
  return image_urls[seed % len(image_urls)]


# 依活動標題與描述推斷備用圖片類別（親子/美食/市集等）
def infer_fallback_image_key(activity):
  text = f'{activity.title or ""} {activity.description or ""}'
  for keyword, image_key in FALLBACK_IMAGE_KEYWORDS:
    if keyword in text:
      return image_key
  return ''


# 取得本地靜態 LINE 圖片的公開 URL（需 PUBLIC_BASE_URL）
def static_line_image_url(file_name):
  if settings.PUBLIC_BASE_URL:
    return f'{settings.PUBLIC_BASE_URL}/static/img/line/{file_name}'
  return default_remote_image_url(None)


# 建立活動標籤徽章清單（含已訂閱標記與使用者偏好高亮）
def build_tag_badges(activity, focus_tag=None, subscribed=False):
  badges = []
  if subscribed:
    badges.append(tag_badge('已訂閱', '#E8F5E9', '#2E7D32'))
  preferred_names = set()
  user = getattr(activity, '_line_user', None)
  if user:
    preferred_names = set(user.preferred_tags.values_list('name', flat=True))
  if focus_tag:
    focus = find_active_tag(focus_tag)
    if focus and focus.tag_type == 'activity_type':
      badges.append(tag_badge(focus_tag, '#E8F5E9', '#2E7D32'))
  for tag in get_public_card_tags(activity, focus_tag=focus_tag):
    if focus_tag and tag.name == focus_tag:
      continue
    if len(badges) >= 3:
      break
    if tag.name in preferred_names:
      badges.append(tag_badge(tag.name, '#E8F5E9', '#2E7D32'))
    else:
      badges.append(tag_badge(tag.name, '#F5F5F5', '#666666'))
  return badges or [{'type': 'filler'}]


# 取得活動用於卡片顯示的 activity_type 公開標籤
def get_public_card_tags(activity, focus_tag=None):
  tags = []
  for tag in activity.tags.all():
    if tag.tag_type != 'activity_type':
      continue
    if focus_tag and tag.name == focus_tag:
      continue
    tags.append(tag)
    if len(tags) >= 4:
      break
  return tags


# 建立單一標籤徽章 Flex 元件
def tag_badge(name, background, color):
  return {
    'type': 'box',
    'layout': 'horizontal',
    'backgroundColor': background,
    'paddingX': 'sm',
    'paddingY': 'xs',
    'cornerRadius': 'md',
    'contents': [{'type': 'text', 'text': f'#{name}', 'size': 'xxs', 'color': color, 'weight': 'bold'}],
  }


# 處理活動相關 Postback 事件（標籤切換、訂閱、取消、導航、行事曆、查看更多）
def handle_activity_postback(user, action, params):
  if action == 'toggle_tag':
    toggle_preference_tag(user, params.get('tag', ''))
    return build_preference_message(user)

  if action == 'set_recommend_push_interval':
    days = parse_positive_int(params.get('days'), default=3)
    if days == 0:
      user.recommend_push_enabled = False
    elif days in {1, 3, 5}:
      user.recommend_push_enabled = True
      user.recommend_push_interval_days = days
    user.save(update_fields=['recommend_push_enabled', 'recommend_push_interval_days', 'updated_at'])
    return build_preference_message(user)

  if action == 'set_reminder_days':
    return set_subscription_reminder_days(user, params.get('activity_id'), params.get('days'))

  if action in {'subscribe_activity', 'interested'}:
    return subscribe_activity(user, params.get('activity_id'), source_action=action)

  if action == 'cancel_subscription':
    return cancel_subscription(user, params.get('activity_id'))

  if action == 'how_to_go':
    activity = get_activity_from_postback(params)
    if not activity:
      return TextSendMessage(text='找不到這筆活動，可能已經下架或資料更新。')
    record_action(user, activity, 'how_to_go', {'source': 'line_postback'})
    return TextSendMessage(text=f'導航前往地點：\n{google_maps_url(activity.district, activity.location)}')

  if action == 'add_calendar':
    activity = get_activity_from_postback(params)
    if not activity:
      return TextSendMessage(text='找不到這筆活動，可能已經下架或資料更新。')
    record_action(user, activity, 'add_calendar', {'source': 'line_postback', 'interested': True})
    return TextSendMessage(text=f'加入 Google 行事曆：\n{google_calendar_url(activity)}')

  if action == 'view_more':
    query = params.get('query') or '推薦活動'
    offset = parse_positive_int(params.get('offset'), default=3)
    if query == '推薦活動':
      activities = get_recommended_activities(user, limit=3, offset=offset)
    else:
      activities = search_activities_for_line(user, query, limit=3, offset=offset)
    record_action(user, None, 'view_more', {'source': 'line_postback', 'query': query, 'offset': offset})
    log_card_views(user, activities, source='line_view_more', query=query)
    return build_activity_carousel_message(
      activities,
      alt_text='更多桃園活動',
      user=user,
      query_context=query,
      offset=offset,
      include_intro=True,
    )

  return TextSendMessage(text='這個操作目前還不能處理。')


# 設定訂閱活動的提醒天數（1/3/5 天前）
def set_subscription_reminder_days(user, activity_id, days_value):
  days = parse_positive_int(days_value, default=1)
  if days not in {1, 3, 5}:
    return TextSendMessage(text='提醒天數只能設定為 5 天、3 天或 1 天。')
  activity = Activity.objects.filter(id=activity_id).first()
  subscription = equivalent_subscription_for_activity(user, activity) if activity else None
  if not subscription:
    return TextSendMessage(text='請先訂閱此活動，再設定提醒時間。')
  subscription.remind_before_days = days
  subscription.is_notified = False
  subscription.save(update_fields=['remind_before_days', 'is_notified'])
  return TextSendMessage(text=f'已設定：{days} 天後活動開始，提醒您。')


# 建立或重新啟用活動訂閱
def subscribe_activity(user, activity_id, source_action='subscribe_activity'):
  activity = Activity.objects.filter(id=activity_id).first()
  if not activity:
    return TextSendMessage(text='找不到這筆活動，可能已經下架或資料更新。')
  now = timezone.now()
  if activity.excluded_from_public or not activity.is_activity or activity.status != 'active' or (activity.end_date and activity.end_date < now):
    return TextSendMessage(text='這個活動目前已下架或已結束，不能訂閱。')
  equivalent_subscription = equivalent_subscription_for_activity(user, activity, include_cancelled=True)
  if equivalent_subscription:
    subscription = equivalent_subscription
    created = False
  else:
    subscription, created = Subscription.objects.get_or_create(
      user=user,
      activity=activity,
      defaults={
        'remind_before_days': user.default_remind_before_days,
        'is_notified': False,
      },
    )
  if not created and subscription.status == 'cancelled':
    subscription.status = 'active'
    subscription.cancelled_at = None
    subscription.is_notified = False
    subscription.save(update_fields=['status', 'cancelled_at', 'is_notified'])
    created = True
  record_action(
    user,
    activity,
    'subscribe',
    {'source': 'line_postback', 'source_action': source_action, 'created': created},
  )
  return build_subscription_success_message(activity, subscription, created)


# 取消活動訂閱（狀態改為 cancelled）
def cancel_subscription(user, activity_id):
  activity = Activity.objects.filter(id=activity_id).first()
  subscription = equivalent_subscription_for_activity(user, activity, include_cancelled=True) if activity else None
  if not subscription:
    return TextSendMessage(text='您尚未訂閱這個活動。')
  if subscription.status == 'cancelled':
    return TextSendMessage(text='這個活動先前已取消訂閱。')
  subscription.status = 'cancelled'
  subscription.cancelled_at = timezone.now()
  subscription.is_notified = False
  subscription.save(update_fields=['status', 'cancelled_at', 'is_notified'])
  record_action(user, subscription.activity, 'unsubscribe', {'source': 'line_postback'})
  return TextSendMessage(text=f'已取消訂閱：{subscription.activity.title}')


# 建立訂閱成功 Flex Message（含提醒天數設定與 Google Calendar 按鈕）
def build_subscription_success_message(activity, subscription, created):
  title = f'訂閱成功！您希望提醒的時間:' if created else '您先前已訂閱過此活動'
  color = '#1DB446' if created else '#4A4A4A'
  contents = {
    'type': 'bubble',
    'size': 'mega',
    'header': {
      'type': 'box',
      'layout': 'vertical',
      'backgroundColor': color,
      'contents': [{'type': 'text', 'text': title, 'weight': 'bold', 'size': 'sm', 'color': '#FFFFFF'}],
    },
    'body': {
      'type': 'box',
      'layout': 'vertical',
      'spacing': 'md',
      'contents': [
        {'type': 'text', 'text': activity.title, 'weight': 'bold', 'size': 'md', 'wrap': True, 'color': '#111111'},
        {'type': 'separator', 'margin': 'sm'},
        info_row('時間', format_time_range(activity)),
        info_row('地點', f'[{activity.district or "桃園"}] {activity.location or "活動現場"}'),
        {
          'type': 'box',
          'layout': 'horizontal',
          'spacing': 'sm',
          'contents': [
            reminder_button(activity, 5),
            reminder_button(activity, 3),
            reminder_button(activity, 1),
          ],
        },
        {
          'type': 'button',
          'style': 'primary',
          'color': '#4285F4',
          'height': 'sm',
          'margin': 'md',
          'action': {'type': 'uri', 'label': '新增至 Google 行事曆', 'uri': google_calendar_url(activity)},
        },
      ],
    },
  }
  return FlexSendMessage(alt_text=f'活動訂閱：{activity.title}', contents=contents)


# 建立提醒天數選擇按鈕
def reminder_button(activity, days):
  return {
    'type': 'button',
    'style': 'secondary',
    'height': 'sm',
    'action': {
      'type': 'postback',
      'label': f'{days} 天後活動開始提醒',
      'data': f'action=set_reminder_days&activity_id={activity.id}&days={days}',
    },
  }


# 建立取消訂閱按鈕
def cancel_subscription_button(activity, label='取消訂閱'):
  return {
    'type': 'button',
    'style': 'secondary',
    'height': 'sm',
    'action': {
      'type': 'postback',
      'label': label,
      'data': f'action=cancel_subscription&activity_id={activity.id}',
    },
  }


# 建立查看更多活動按鈕（帶查詢與 offset 參數）
def view_more_button(query_context, next_offset):
  query = urllib.parse.quote(query_context or '推薦活動')
  return {
    'type': 'button',
    'style': 'secondary',
    'height': 'sm',
    'action': {
      'type': 'postback',
      'label': '查看更多活動',
      'data': f'action=view_more&query={query}&offset={next_offset}',
    },
  }


def search_activities_by_rules(query, limit=10):
  return query_activities_by_conditions(rule_extract_conditions(query), limit=limit)


def build_search_context():
  available_tags = {}
  for tag_type, name in Tag.objects.filter(is_active=True).order_by('tag_type', 'name').values_list('tag_type', 'name'):
    available_tags.setdefault(tag_type, []).append(name)

  return {
    'available_tags': available_tags,
    'searchable_vocabulary': search_vocabulary_terms(limit=300),
  }


def search_vocabulary_terms(limit=300):
  counts = Counter()
  profiles = ActivitySearchProfile.objects.filter(status='success').values_list('keywords', 'topics', 'synonyms')
  for keywords, topics, synonyms in profiles:
    for value in (keywords or []) + (topics or []) + (synonyms or []):
      term = str(value or '').strip()
      if len(term) >= 2:
        counts[term] += 1
  return [term for term, count in counts.most_common(limit) if count >= 2]


def expand_terms_with_search_vocabulary(terms):
  terms = merge_query_terms(terms, limit=60)
  if not terms:
    return []
  vocabulary = search_vocabulary_terms()
  expanded = list(terms)
  for term in terms:
    contained = [
      candidate
      for candidate in vocabulary
      if candidate != term and candidate in term
    ]
    for candidate in sorted(contained, key=len, reverse=True):
      if any(candidate in existing and len(existing) > len(candidate) for existing in contained):
        continue
      if candidate not in expanded:
        expanded.append(candidate)
  return expanded[:60]


def db_search_terms_from_conditions(conditions):
  terms = merge_query_terms(
    (conditions or {}).get('keyword'),
    (conditions or {}).get('soft_topics'),
    (conditions or {}).get('related_terms'),
    limit=40,
  )
  return expand_terms_with_search_vocabulary(terms)


def extract_conditions_from_message(user, query):
  started_at = time.monotonic()
  fallback = rule_extract_conditions(query)
  try:
    search_context = build_search_context()
    payload = {
      'message': query,
      'allowed_districts': list(DISTRICTS),
      'available_tags': search_context['available_tags'],
      'searchable_vocabulary': search_context['searchable_vocabulary'],
      'output_schema': {
        'district': 'one district name without 區, or empty string',
        'tag_names': 'array of existing tag names from available_tags',
        'is_free': 'true, false, or null',
        'soft_topics': 'array of broad search topics, can include non-tag natural words',
        'related_terms': 'array of synonyms or related search terms',
        'keyword': 'short keyword if needed',
        'relax_order': 'array of fields to relax, for example keyword, is_free, soft_topics, district',
      },
      'examples': [
        {
          'message': '展覽',
          'conditions': {
            'district': '',
            'tag_names': ['展覽'],
            'is_free': None,
            'keyword': '',
            'soft_topics': ['展覽'],
            'related_terms': ['藝文', '藝術', '文化'],
            'relax_order': ['soft_topics', 'tag_names'],
          },
        },
        {
          'message': '想跟女朋友去',
          'conditions': {
            'district': '',
            'tag_names': ['情侶'],
            'is_free': None,
            'keyword': '',
            'soft_topics': ['約會', '情侶'],
            'related_terms': ['兩人', '藝文', '展覽'],
            'relax_order': ['soft_topics', 'tag_names'],
          },
        },
        {
          'message': '想玩泥巴',
          'conditions': {
            'district': '',
            'tag_names': ['手作'],
            'is_free': None,
            'keyword': '',
            'soft_topics': ['陶藝', '手作'],
            'related_terms': ['黏土', '陶土', '陶瓷'],
            'relax_order': ['soft_topics', 'related_terms', 'tag_names'],
          },
        },
        {
          'message': '有文化幣可以用的活動',
          'conditions': {
            'district': '',
            'tag_names': [],
            'is_free': None,
            'keyword': '文化幣',
            'soft_topics': ['文化幣'],
            'related_terms': ['青年文化幣', '文化成年禮金'],
            'relax_order': ['keyword', 'soft_topics'],
          },
        },
        {
          'message': '有文化幣活動嗎',
          'conditions': {
            'district': '',
            'tag_names': [],
            'is_free': None,
            'keyword': '文化幣',
            'soft_topics': ['文化幣'],
            'related_terms': ['青年文化幣', '文化成年禮金'],
            'relax_order': ['keyword', 'soft_topics'],
          },
        },
        {
          'message': '我有文化幣。幫我找活動',
          'conditions': {
            'district': '',
            'tag_names': [],
            'is_free': None,
            'keyword': '文化幣',
            'soft_topics': ['文化幣'],
            'related_terms': ['青年文化幣', '文化成年禮金'],
            'relax_order': ['keyword', 'soft_topics'],
          },
        },
        {
          'message': '我想找靜態活動',
          'conditions': {
            'district': '',
            'tag_names': ['展覽', '閱讀', '講座'],
            'is_free': None,
            'keyword': '',
            'soft_topics': ['展覽', '閱讀', '講座', '藝文'],
            'related_terms': ['室內', '安靜', '不用跑跳', '欣賞'],
            'relax_order': ['soft_topics', 'tag_names'],
          },
        },
        {
          'message': '我想帶小孩玩',
          'conditions': {
            'district': '',
            'tag_names': ['親子'],
            'is_free': None,
            'keyword': '',
            'soft_topics': ['親子', '體驗'],
            'related_terms': ['兒童', '小朋友', '家庭', '放電'],
            'relax_order': ['soft_topics', 'tag_names'],
          },
        },
        {
          'message': '中壢免費親子',
          'conditions': {
            'district': '中壢',
            'tag_names': ['親子'],
            'is_free': True,
            'keyword': '',
            'soft_topics': ['親子'],
            'related_terms': ['兒童', '小朋友', '家庭'],
            'relax_order': ['soft_topics', 'tag_names', 'is_free', 'district'],
          },
        },
        {
          'message': '桃園有什麼',
          'conditions': {
            'district': '桃園',
            'tag_names': [],
            'is_free': None,
            'keyword': '',
            'soft_topics': [],
            'related_terms': [],
            'relax_order': ['district'],
          },
        },
      ],
    }
    response = call_json_with_fallback(
      payload_messages(
        '你是桃園活動查詢搜尋計畫產生器。只輸出 JSON，不要解釋。'
        '你的任務是把活動相關口語轉成資料庫查詢條件，不可推薦或創造活動。'
        'district 只能使用 allowed_districts；tag_names 只能使用 available_tags 各分類中的既有值。'
        'keyword 和 soft_topics 優先使用 searchable_vocabulary 中真實存在於資料庫的詞，但可保留使用者明確輸入的新詞。'
        'keyword 必須只放核心可搜尋名詞或專有詞，不要放整句話。'
        'keyword 必須移除語助詞與查詢用詞，例如：有、沒有、嗎、的、呢、吧、啊、想、要、找、看、活動、可以、用。'
        '例如「有文化幣活動嗎」只能輸出 keyword=文化幣，不能輸出「有文化幣 嗎」或「文化幣活動」。'
        '使用者說「我有 X」「我拿到 X」「可以用 X」時，通常是在描述可使用的票券、補助或優惠，keyword 只取 X 的核心名詞。'
        '使用者說「靜態活動」「不要跑跳」「想安靜看」時，這是活動型態偏好，請優先對應到 available_tags 中的展覽、閱讀、講座、藝文等靜態類型，不要把「靜態活動」當 keyword。'
        'related_terms 用於擴展語意搜尋，可以是同義詞、口語表達或資料庫詞彙。'
        'soft_topics/related_terms 只作資料庫搜尋語意，不是正式 tag、不要放入使用者偏好。'
        '口語句要寬鬆處理；像「桃園的」「有沒有桃園活動」只抽 district=桃園，不要把語助詞、查詢動詞或活動泛稱放進 keyword。'
        '「我想帶小孩玩」這類生活語境可用 tag_names=親子，並把兒童/小朋友/家庭/放電放進 related_terms。'
        '「心情好差」「你會陪我聊天嗎」不是活動查詢，通常不應進到此搜尋計畫。若使用者有輸入類似的話語，請給與正向的回覆無法執行',
        payload,
      )
    )
    conditions = normalize_ai_conditions(response.parsed, fallback=fallback, user=user, query=query)
    log_ai_processing(
      task_type='condition_extract',
      user=user,
      input_summary=query,
      output_json={'conditions': conditions, 'provider': response.provider},
      latency_ms=elapsed_ms(started_at),
      status='success',
      model=f'{response.provider}:{response.model}',
    )
    return conditions
  except Exception as exc:
    log_ai_processing(
      task_type='condition_extract',
      user=user,
      input_summary=query,
      output_json={'conditions': fallback, 'provider': 'rule'},
      latency_ms=elapsed_ms(started_at),
      status='failed',
      error=str(exc),
      model='rule',
    )
    return fallback


def query_activities_by_conditions(conditions, limit=10):
  qs = get_recommendation_ready_activities().select_related('search_profile').prefetch_related('tags')
  district = (conditions or {}).get('district')
  if district:
    qs = qs.filter(district__icontains=district.replace('區', ''))

  exclude_tag_names = (conditions or {}).get('exclude_tag_names') or []
  if exclude_tag_names:
    qs = qs.exclude(tags__name__in=exclude_tag_names)

  is_free = (conditions or {}).get('is_free')
  if is_free is not None:
    qs = qs.filter(is_free=bool(is_free))

  start_date = (conditions or {}).get('start_date')
  end_date = (conditions or {}).get('end_date')
  if start_date:
    qs = qs.filter(start_date__gte=start_date)
  if end_date:
    qs = qs.filter(start_date__lte=end_date)

  search_terms = db_search_terms_from_conditions(conditions or {})
  if search_terms:
    search_q = Q()
    for term in search_terms:
      search_q |= (
        Q(title__icontains=term)
        | Q(description__icontains=term)
        | Q(ai_summary__icontains=term)
        | Q(ocr_summary__icontains=term)
        | Q(ocr_text__icontains=term)
        | Q(tags__name__icontains=term)
        | Q(search_profile__search_text__icontains=term)
      )
    qs = qs.filter(search_q)

  candidates = list(qs.distinct().order_by('start_date', 'id')[:max(limit * 6, limit)])
  scored = score_activities_for_search_plan(candidates, conditions or {})
  if scored:
    return [activity for activity, _score in scored[:limit]]
  if semantic_terms_from_conditions(conditions or {}):
    return []
  return candidates[:limit]


def relaxed_search_activities(user, conditions, original_query, limit=10):
  conditions = conditions or {}
  attempts = []
  has_strict_topics = bool(strict_topic_terms(conditions, original_query))
  if conditions.get('keyword'):
    relaxed = dict(conditions)
    relaxed['keyword'] = ''
    attempts.append((relaxed, '先推薦相近活動。'))
  if conditions.get('is_free') is not None:
    relaxed = dict(conditions)
    relaxed['is_free'] = None
    attempts.append((relaxed, '先推薦相近活動。'))
  if conditions.get('tag_names'):
    relaxed = dict(conditions)
    relaxed['tag_names'] = []
    attempts.append((relaxed, '先推薦相近活動。'))
  if not has_strict_topics and (conditions.get('soft_topics') or conditions.get('related_terms')):
    relaxed = dict(conditions)
    relaxed['soft_topics'] = []
    relaxed['related_terms'] = []
    attempts.append((relaxed, '先推薦相近活動。'))
  if conditions.get('district') and not strict_district_requested(original_query, conditions):
    relaxed = dict(conditions)
    relaxed['district'] = ''
    attempts.append((relaxed, '先推薦相近活動。'))

  seen = set()
  for relaxed, notice in attempts:
    key = json.dumps(relaxed, ensure_ascii=False, sort_keys=True, default=str)
    if key in seen:
      continue
    seen.add(key)
    matches = query_activities_by_conditions(relaxed, limit=limit)
    if matches:
      return matches, notice

  if not allow_recommendation_fallback(original_query, conditions):
    return [], ''

  fallback = get_recommended_activities(user, limit=limit, use_ai=False)
  if fallback:
    return fallback, f'目前沒有找到完全符合「{original_query}」的活動，先推薦你可能喜歡的活動。'
  return [], ''


def allow_recommendation_fallback(original_query, conditions):
  text = original_query or ''
  if any(term in text for term in IMPOSSIBLE_LOCAL_TERMS):
    return False
  if strict_district_requested(original_query, conditions):
    return False
  if strict_topic_terms(conditions, original_query):
    return False
  keyword = (conditions or {}).get('keyword') or ''
  if keyword and len(keyword) >= 8 and not any(term in text for term in ('隨便', '推薦', '有什麼', '有啥')):
    return False
  return True


def strict_district_requested(original_query, conditions):
  district = (conditions or {}).get('district') or ''
  if not district:
    return False
  compact = re.sub(r'\s+', '', original_query or '')
  return district in compact or f'{district}區' in compact


def strict_topic_terms(conditions, original_query=''):
  terms = set(merge_query_terms(
    (conditions or {}).get('tag_names'),
    (conditions or {}).get('soft_topics'),
    (conditions or {}).get('related_terms'),
    original_query,
    limit=80,
  ))
  return sorted(term for term in terms if term in STRICT_SEARCH_TOPICS)


def force_no_result_query(original_query, conditions):
  text = original_query or ''
  if any(term in text for term in IMPOSSIBLE_LOCAL_TERMS):
    return True
  if '潛水' in text:
    return True
  return False


def rule_extract_conditions(query):
  text = query or ''
  conditions = {'district': '', 'tag_names': [], 'is_free': None, 'keyword': '', 'soft_topics': [], 'related_terms': [], 'relax_order': []}

  for district in DISTRICTS:
    if district in text or f'{district}區' in text:
      conditions['district'] = district
      break

  if any(word in text for word in ('免費', '免門票', '不用錢', '小資')):
    conditions['is_free'] = True
  if any(word in text for word in ('不要太遠', '附近', '近一點', '離我近')):
    conditions['nearby_intent'] = True

  compact_text = re.sub(r'\s+', '', text)
  if has_child_lifestyle_intent(compact_text):
    tag = find_active_tag('親子')
    if tag and tag.name not in conditions['tag_names']:
      conditions['tag_names'].append(tag.name)
    conditions['soft_topics'] = merge_query_terms(conditions.get('soft_topics'), ['親子', '體驗'], limit=16)
    conditions['related_terms'] = merge_query_terms(conditions.get('related_terms'), ['兒童', '小朋友', '家庭', '放電'], limit=24)

  if has_rainy_lifestyle_intent(compact_text):
    conditions['soft_topics'] = merge_query_terms(conditions.get('soft_topics'), ['室內', '展覽', '藝文'], limit=16)
    conditions['related_terms'] = merge_query_terms(conditions.get('related_terms'), ['下雨', '雨天', '室內活動'], limit=24)

  if has_date_lifestyle_intent(compact_text):
    conditions['soft_topics'] = merge_query_terms(conditions.get('soft_topics'), ['藝文', '展覽', '市集'], limit=16)
    conditions['related_terms'] = merge_query_terms(conditions.get('related_terms'), ['情侶', '約會', '休閒'], limit=24)

  if '市民卡' in text:
    tag = find_active_tag('市民卡')
    if tag:
      conditions['tag_names'].append(tag.name)

  for tag in Tag.objects.filter(is_active=True):
    if tag.tag_type == 'region' and conditions.get('district'):
      continue
    if tag.tag_type == 'cost' and conditions.get('is_free') is not None:
      continue
    if tag.name and tag.name in text and tag.name not in conditions['tag_names']:
      conditions['tag_names'].append(tag.name)
      conditions['soft_topics'].append(tag.name)

  for term, expansions in SEMANTIC_QUERY_EXPANSIONS.items():
    if term in text:
      conditions['soft_topics'] = merge_query_terms(conditions.get('soft_topics'), [term], limit=16)
      conditions['related_terms'] = merge_query_terms(conditions.get('related_terms'), expansions, limit=24)

  today = timezone.localdate()
  if any(word in text for word in ('今天', '今日')):
    conditions['start_date'] = timezone.make_aware(datetime.combine(today, datetime_time.min))
    conditions['end_date'] = timezone.make_aware(datetime.combine(today, datetime_time.max))
  elif '明天' in text:
    day = today + timedelta(days=1)
    conditions['start_date'] = timezone.make_aware(datetime.combine(day, datetime_time.min))
    conditions['end_date'] = timezone.make_aware(datetime.combine(day, datetime_time.max))
  elif '週末' in text or '周末' in text:
    days_until_saturday = (5 - today.weekday()) % 7
    saturday = today + timedelta(days=days_until_saturday)
    sunday = saturday + timedelta(days=1)
    conditions['start_date'] = timezone.make_aware(datetime.combine(saturday, datetime_time.min))
    conditions['end_date'] = timezone.make_aware(datetime.combine(sunday, datetime_time.max))

  keyword = re.sub(r'(桃園市?|區|免費|免門票|不用錢|小資|今天|今日|明天|週末|周末|活動|有沒有|想看|我要|我想|不要太遠|附近|近一點|離我近|的|我|看)', ' ', text)
  for district in DISTRICTS:
    keyword = keyword.replace(district, ' ')
  for tag_name in conditions['tag_names']:
    keyword = keyword.replace(tag_name, ' ')
  if is_lifestyle_activity_query(text):
    for term in LIFESTYLE_KEYWORD_STOPWORDS:
      keyword = keyword.replace(term, ' ')
  keyword = re.sub(r'\s+', ' ', keyword).strip()
  if keyword:
    conditions['keyword'] = keyword[:30]
  conditions['relax_order'] = infer_relax_order(conditions)

  return apply_nearby_preference(user=None, conditions=conditions)


def normalize_ai_conditions(result, fallback=None, user=None, query=''):
  if not isinstance(result, dict):
    result = {}
  fallback = fallback or {}
  active_tags = list(Tag.objects.filter(is_active=True))
  allowed_tags = {tag.name for tag in active_tags}
  tag_types_by_name = {}
  for tag in active_tags:
    tag_types_by_name.setdefault(tag.name, set()).add(tag.tag_type)
  district = str(result.get('district') or fallback.get('district') or '').replace('區', '').strip()
  if district not in DISTRICTS:
    district = fallback.get('district') or ''
  if district and district not in (query or '') and f'{district}區' not in (query or ''):
    district = fallback.get('district') or ''

  is_free = result.get('is_free')
  if is_free not in (True, False, None):
    is_free = fallback.get('is_free')

  raw_tags = result.get('tag_names') or result.get('tags') or fallback.get('tag_names') or []
  if isinstance(raw_tags, str):
    raw_tags = [raw_tags]
  tag_names = []
  for name in raw_tags:
    tag_name = str(name).strip().lstrip('#')
    tag_types = tag_types_by_name.get(tag_name, set())
    if district and 'region' in tag_types:
      continue
    if is_free is not None and 'cost' in tag_types:
      continue
    if tag_name in INFERRED_GENERIC_TAGS and tag_name not in (query or ''):
      continue
    if tag_name in allowed_tags and tag_name not in tag_names:
      tag_names.append(tag_name)

  raw_excluded_tags = result.get('exclude_tag_names') or fallback.get('exclude_tag_names') or []
  if isinstance(raw_excluded_tags, str):
    raw_excluded_tags = [raw_excluded_tags]
  exclude_tag_names = []
  for name in raw_excluded_tags:
    tag_name = str(name).strip().lstrip('#')
    if tag_name in allowed_tags and tag_name not in exclude_tag_names:
      exclude_tag_names.append(tag_name)
  if exclude_tag_names:
    tag_names = [name for name in tag_names if name not in exclude_tag_names]

  keyword = clean_query_keyword(str(result.get('keyword') or fallback.get('keyword') or '').strip(), query)[:30]
  soft_topics = clean_semantic_terms(merge_query_terms(fallback.get('soft_topics'), result.get('soft_topics') or result.get('topics'), limit=16), query=query)
  related_terms = clean_semantic_terms(merge_query_terms(fallback.get('related_terms'), result.get('related_terms') or result.get('synonyms'), limit=24), query=query)
  if is_free is not None:
    soft_topics = [term for term in soft_topics if term not in FEE_SEMANTIC_TERMS]
    related_terms = [term for term in related_terms if term not in FEE_SEMANTIC_TERMS]
  for term in [keyword, *tag_names, *soft_topics]:
    if term in SEMANTIC_QUERY_EXPANSIONS:
      related_terms = merge_query_terms(related_terms, SEMANTIC_QUERY_EXPANSIONS[term], limit=24)
  related_terms = clean_semantic_terms(related_terms, query=query)
  if is_simple_district_query(query, district):
    keyword = ''
    tag_names = []
    soft_topics = []
    related_terms = []
  relax_seed = {
    'district': district,
    'is_free': is_free,
    'keyword': keyword,
    'tag_names': tag_names,
    'exclude_tag_names': exclude_tag_names,
    'soft_topics': soft_topics,
    'related_terms': related_terms,
  }
  relax_order = applicable_relax_order(normalize_relax_order(result.get('relax_order')), relax_seed)
  relax_order = relax_order or applicable_relax_order(normalize_relax_order(fallback.get('relax_order')), relax_seed)
  relax_order = relax_order or infer_relax_order({
    'district': district,
    'is_free': is_free,
    'keyword': keyword,
    'tag_names': tag_names,
    'exclude_tag_names': exclude_tag_names,
    'soft_topics': soft_topics,
    'related_terms': related_terms,
  })
  conditions = {
    'district': district,
    'tag_names': tag_names,
    'exclude_tag_names': exclude_tag_names,
    'is_free': is_free,
    'keyword': keyword,
    'soft_topics': soft_topics,
    'related_terms': related_terms,
    'relax_order': relax_order,
  }
  if result.get('nearby_intent') or fallback.get('nearby_intent') or any(word in (query or '') for word in ('不要太遠', '附近', '近一點', '離我近')):
    conditions['nearby_intent'] = True
  return apply_nearby_preference(user=user, conditions=conditions)


def clean_query_keyword(keyword, query=''):
  text = keyword or ''
  text = re.sub(r'(桃園市?|區|免費|免門票|不用錢|小資|今天|今日|明天|週末|周末|活動|有沒有|想看|我要|我想|不要太遠|附近|近一點|離我近|的|我|看)', ' ', text)
  for district in DISTRICTS:
    text = text.replace(district, ' ')
  if is_lifestyle_activity_query(query):
    for term in LIFESTYLE_KEYWORD_STOPWORDS:
      text = text.replace(term, ' ')
  text = re.sub(r'\s+', ' ', text).strip()
  if text in {'有', '沒有', '想', '看'}:
    return ''
  if query and text == query.strip():
    simplified = re.sub(r'(桃園市?|區|活動|有沒有|想看|我要|我想|的)', ' ', text)
    simplified = re.sub(r'\s+', ' ', simplified).strip()
    return simplified if simplified != text else text
  return text


def is_simple_district_query(query, district):
  compact = re.sub(r'\s+', '', query or '')
  if not compact or not district:
    return False
  return compact in {district, f'{district}區', f'{district}的', f'{district}活動', f'有沒有{district}活動'}


def clean_semantic_terms(terms, query=''):
  stopwords = {
    '', '桃園', '桃園市', '桃市', '桃苗', '桃園縣', '活動', '推薦', '最好', '有沒有',
    '想看', '我要', '我想', '不然', '的', '呢', '請問',
  }
  cleaned = []
  for term in merge_query_terms(terms, limit=30):
    if term in stopwords:
      continue
    if term.endswith('的') and len(term) <= 4:
      continue
    if term not in cleaned:
      cleaned.append(term)
  return cleaned


def normalize_relax_order(values):
  allowed = {'keyword', 'is_free', 'soft_topics', 'related_terms', 'tag_names', 'district'}
  return [item for item in merge_query_terms(values, limit=8) if item in allowed]


def applicable_relax_order(order, conditions):
  if not order:
    return []
  return [item for item in order if conditions.get(item)]


def merge_query_terms(*groups, limit=24):
  terms = []
  for group in groups:
    if not group:
      continue
    if isinstance(group, str):
      group = re.split(r'[,，、\s]+', group)
    for value in group:
      term = re.sub(r'\s+', '', str(value or '').strip().lstrip('#'))
      if not term or len(term) > 20:
        continue
      if term not in terms:
        terms.append(term)
      if len(terms) >= limit:
        return terms
  return terms


def infer_relax_order(conditions):
  order = []
  if (conditions or {}).get('keyword'):
    order.append('keyword')
  if (conditions or {}).get('related_terms') or (conditions or {}).get('soft_topics'):
    order.append('soft_topics')
  if (conditions or {}).get('tag_names'):
    order.append('tag_names')
  if (conditions or {}).get('is_free') is not None:
    order.append('is_free')
  if (conditions or {}).get('district'):
    order.append('district')
  return order


def semantic_terms_from_conditions(conditions):
  conditions = conditions or {}
  terms = []
  terms = merge_query_terms(terms, conditions.get('keyword'), limit=60)
  terms = merge_query_terms(terms, conditions.get('tag_names'), limit=60)
  terms = merge_query_terms(terms, conditions.get('soft_topics'), limit=60)
  terms = merge_query_terms(terms, conditions.get('related_terms'), limit=60)
  return expand_terms_with_search_vocabulary(terms)


def activity_search_blob(activity):
  tag_names = ' '.join(tag.name for tag in activity.tags.all())
  profile = getattr(activity, 'search_profile', None)
  profile_text = getattr(profile, 'search_text', '') if profile else ''
  return ' '.join(str(part or '') for part in (
    activity.title,
    activity.description,
    activity.ai_summary,
    activity.ocr_summary,
    activity.ocr_text,
    activity.location,
    activity.source_agency,
    tag_names,
    profile_text,
  ))


def score_activities_for_search_plan(activities, conditions):
  terms = semantic_terms_from_conditions(conditions)
  if not terms:
    return []
  has_keyword = bool((conditions or {}).get('keyword'))
  strict_terms = set(strict_topic_terms(conditions))
  primary_terms = set(expand_terms_with_search_vocabulary(merge_query_terms(
    conditions.get('keyword'),
    conditions.get('soft_topics'),
    [term for term in (conditions.get('related_terms') or []) if term not in WEAK_SEMANTIC_TERMS],
    limit=40,
  )))
  tag_names = set((conditions or {}).get('tag_names') or [])
  scored = []
  for activity in activities:
    title = activity.title or ''
    summary = ' '.join([activity.ai_summary or '', activity.description or '', activity.ocr_summary or ''])
    blob = activity_search_blob(activity)
    profile = getattr(activity, 'search_profile', None)
    profile_text = getattr(profile, 'search_text', '') if profile else ''
    profile_terms_text = ' '.join(
      ' '.join(getattr(profile, field, None) or [])
      for field in ('keywords', 'topics', 'synonyms')
    ) if profile else ''
    activity_tags = {tag.name for tag in activity.tags.all()}
    score = 0
    matched_terms = []
    matched_primary_terms = set()
    strong_score = 0
    primary_score = 0
    strict_surface_match = False
    primary_high_confidence = False
    for term in terms:
      if not term:
        continue
      term_score = 0
      if term in title:
        term_score += 30
        if term in primary_terms:
          strict_surface_match = True
          primary_high_confidence = True
      if term in activity_tags:
        term_score += 22
        if term in primary_terms:
          strict_surface_match = True
          primary_high_confidence = True
      if tag_names and term in tag_names and term in activity_tags:
        term_score += 12
      if term in profile_text:
        term_score += 18
        if term in primary_terms and term in profile_terms_text:
          strict_surface_match = True
          primary_high_confidence = True
      if term in summary:
        term_score += 12
        if term in primary_terms:
          primary_high_confidence = True
      if term in blob:
        term_score += 6
      if term_score:
        score += term_score
        matched_terms.append(term)
        if term not in WEAK_SEMANTIC_TERMS:
          strong_score += term_score
        if term in primary_terms:
          primary_score += term_score
          matched_primary_terms.add(term)
    if conditions.get('district') and conditions['district'] in (activity.district or ''):
      score += 10
    if conditions.get('is_free') is True and activity.is_free:
      score += 8
    if score > 0 and strong_score > 0:
      if strict_terms and not (strict_surface_match or len(matched_primary_terms) >= 2):
        score -= 15
      activity._search_plan_score = score
      activity._semantic_high_confidence = primary_high_confidence
      activity._semantic_matches = matched_terms[:6]
      activity._semantic_relaxed = primary_score == 0
      if activity._semantic_relaxed:
        activity._line_notice = '先推薦相近活動。'
      scored.append((activity, score))
  if has_keyword and any(getattr(activity, '_semantic_high_confidence', False) for activity, _score in scored):
    scored = [
      (activity, score)
      for activity, score in scored
      if getattr(activity, '_semantic_high_confidence', False)
    ]
  return sorted(scored, key=lambda pair: (-pair[1], pair[0].start_date or timezone.now(), pair[0].id))


def apply_nearby_preference(user, conditions):
  conditions = dict(conditions or {})
  if not conditions.get('nearby_intent') or conditions.get('district') or not user:
    return conditions
  preferred_regions = sorted(preferred_tag_sets(user)['region'])
  if preferred_regions:
    conditions['district'] = preferred_regions[0]
  return conditions


def rank_activities_for_user(user, activities):
  if not user:
    return sorted(activities, key=lambda activity: (-getattr(activity, '_search_plan_score', 0), activity.start_date or timezone.now(), activity.id))
  preferences = preferred_tag_sets(user)
  action_counts = recent_action_counts(user)
  seen_keys = recent_seen_business_keys(user)
  subscribed_keys = subscribed_business_keys(user)

  def score(activity):
    activity_tags = list(activity.tags.all())
    activity_tag_ids = {tag.id for tag in activity_tags}
    type_score = len(preferences['activity_type'].intersection(activity_tag_ids)) * 12
    region_score = 14 if activity_region_match(activity, preferences['region']) else 0
    audience_score = len(preferences['audience'].intersection(activity_tag_ids)) * 6
    cost_score = len(preferences['cost'].intersection(activity_tag_ids)) * 4
    discount_score = len(preferences['discount'].intersection(activity_tag_ids)) * 3
    action_score = max((action_counts.get(key, 0) for key in activity_business_keys(activity)), default=0)
    seen_penalty = -18 if seen_keys.intersection(activity_business_keys(activity)) else 0
    subscribed_penalty = -25 if subscribed_keys.intersection(activity_business_keys(activity)) else 0
    date_score = 1 if activity.start_date else 0
    semantic_score = getattr(activity, '_search_plan_score', 0)
    return semantic_score + type_score + region_score + audience_score + cost_score + discount_score + action_score + seen_penalty + subscribed_penalty + date_score

  return sorted(activities, key=lambda activity: (-score(activity), activity.start_date or timezone.now(), activity.id))


def recent_action_counts(user):
  since = timezone.now() - timedelta(days=30)
  weights = {
    'subscribe': 8,
    'add_calendar': 5,
    'interested': 4,
    'how_to_go': 2,
    'unsubscribe': -12,
    'not_interested': -10,
  }
  rows = (ActionLog.objects
          .select_related('activity')
          .filter(user=user, created_at__gte=since, activity_id__isnull=False)
          .exclude(action_type='view_card'))
  scores = {}
  for row in rows:
    for key in activity_business_keys(row.activity):
      scores[key] = scores.get(key, 0) + weights.get(row.action_type, 0)
  return scores


def rerank_activities_with_ai(user, query, activities, limit=3):
  if len(activities) <= limit:
    return activities
  started_at = time.monotonic()
  activity_map = {activity.id: activity for activity in activities}
  candidates = [
    {
      'id': activity.id,
      'title': activity.title,
      'district': activity.district,
      'tags': [tag.name for tag in activity.tags.all()[:5]],
      'summary': (activity.ai_summary or activity.description or '')[:120],
    }
    for activity in activities[:10]
  ]
  try:
    response = call_json_with_fallback(
      payload_messages(
        '你是桃園活動推薦排序器。只能從候選 id 中選出最符合使用者查詢與偏好的 id。只輸出 JSON。',
        {
        'query': query,
        'user_preferred_tags': list(user.preferred_tags.values_list('name', flat=True)),
        'candidates': candidates,
        'output_schema': {'activity_ids': 'array of candidate ids in best order'},
        },
      )
    )
    result = response.parsed or {}
    ordered_ids = [int(value) for value in result.get('activity_ids', []) if int(value) in activity_map]
    ordered = [activity_map[activity_id] for activity_id in ordered_ids]
    ordered.extend(activity for activity in activities if activity.id not in ordered_ids)
    log_ai_processing(
      task_type='rerank',
      user=user,
      input_summary=query,
      output_json={'activity_ids': ordered_ids, 'provider': response.provider},
      latency_ms=elapsed_ms(started_at),
      status='success',
      model=f'{response.provider}:{response.model}',
    )
    return ordered[:limit]
  except Exception as exc:
    log_ai_processing(
      task_type='rerank',
      user=user,
      input_summary=query,
      output_json={'fallback_ids': [activity.id for activity in activities[:limit]]},
      latency_ms=elapsed_ms(started_at),
      status='failed',
      error=str(exc),
    )
    return None


def call_ai_json(system_prompt, payload):
  response = call_json_with_fallback(payload_messages(system_prompt, payload))
  return response.parsed or {}


def parse_json_object(content):
  content = (content or '').strip()
  if content.startswith('```'):
    content = re.sub(r'^```(?:json)?', '', content).strip()
    content = re.sub(r'```$', '', content).strip()
  match = re.search(r'\{.*\}', content, flags=re.S)
  if match:
    content = match.group(0)
  return json.loads(content)


def log_ai_processing(task_type, user, input_summary, output_json, latency_ms, status, error='', model=None, prompt_version='line-v1'):
  try:
    AIProcessingLog.objects.create(
      task_type=task_type,
      line_user_id=user.line_user_id if user else '',
      model=str(model if model is not None else getattr(settings, 'AI_MODEL', ''))[:100],
      prompt_version=prompt_version,
      input_summary=input_summary[:500],
      output_json=json.loads(json.dumps(output_json, ensure_ascii=False, default=str)),
      latency_ms=latency_ms,
      status=status,
      error=error[:1000],
    )
  except Exception:
    pass


def log_card_views(user, activities, source='line_reply', query=None):
  for activity in activities:
    record_action(user, activity, 'view_card', {
      'source': source,
      'query': query,
      'business_key': activity_business_key(activity),
    })


def record_action(user, activity, action_type, metadata=None):
  try:
    ActionLog.objects.create(user=user, activity=activity, action_type=action_type, metadata=metadata or {})
  except Exception:
    pass


def get_activity_from_postback(params):
  return Activity.objects.filter(id=params.get('activity_id')).first()


def parse_positive_int(value, default=0):
  try:
    parsed = int(value)
  except (TypeError, ValueError):
    return default
  return parsed if parsed >= 0 else default


def activity_detail_url(activity, user=None):
  if settings.PUBLIC_BASE_URL:
    params = {'action': 'view_detail'}
    if user:
      params['line_user_id'] = user.line_user_id
    return f'{settings.PUBLIC_BASE_URL}/track/activity/{activity.id}/?{urllib.parse.urlencode(params)}'
  return safe_detail_url(activity)


def tracked_calendar_url(activity, user=None):
  if settings.PUBLIC_BASE_URL:
    params = {}
    if user:
      params['line_user_id'] = user.line_user_id
    query = f'?{urllib.parse.urlencode(params)}' if params else ''
    return f'{settings.PUBLIC_BASE_URL}/track/calendar/{activity.id}/{query}'
  return google_calendar_url(activity)


def tracked_maps_url(activity, user=None):
  if settings.PUBLIC_BASE_URL:
    params = {}
    if user:
      params['line_user_id'] = user.line_user_id
    query = f'?{urllib.parse.urlencode(params)}' if params else ''
    return f'{settings.PUBLIC_BASE_URL}/track/maps/{activity.id}/{query}'
  return google_maps_url(activity.district, activity.location)


def safe_detail_url(activity):
  for detail_url in (activity.official_detail_url, activity.source_url):
    detail_url = str(detail_url or '').strip()
    if not detail_url.startswith(('http://', 'https://')):
      continue
    parsed = urllib.parse.urlparse(detail_url)
    if parsed.scheme in {'http', 'https'} and parsed.netloc:
      return detail_url
  return 'https://www.tycg.gov.tw/'


def info_row(label, value):
  return {
    'type': 'box',
    'layout': 'horizontal',
    'spacing': 'sm',
    'contents': [
      {'type': 'text', 'text': label, 'size': 'xs', 'color': '#888888', 'flex': 1},
      {'type': 'text', 'text': value, 'size': 'xs', 'color': '#333333', 'flex': 5, 'wrap': True},
    ],
  }


def format_activity_time(activity):
  if not activity.start_date:
    return '時間：詳見活動官網公告'
  start = timezone.localtime(activity.start_date).strftime('%m/%d %H:%M')
  if activity.end_date:
    end = timezone.localtime(activity.end_date).strftime('%m/%d %H:%M')
    return f'時間：{start} ~ {end}'
  return f'時間：{start}'


def format_time_range(activity):
  if not activity.start_date:
    return '請詳見活動官網公告'
  start = timezone.localtime(activity.start_date).strftime('%Y/%m/%d %H:%M')
  if activity.end_date:
    end = timezone.localtime(activity.end_date).strftime('%m/%d %H:%M')
    return f'{start} ~ {end}'
  return start


def google_maps_url(district, location):
  query = urllib.parse.quote(f'桃園市{district or ""}{location or ""}')
  return f'https://www.google.com/maps/search/?api=1&query={query}'


def google_calendar_url(activity):
  start = google_datetime(activity.start_date)
  end = google_datetime(activity.end_date) or start
  if not start:
    now = timezone.now().strftime('%Y%m%dT%H%M%SZ')
    start = end = now
  detail_url = safe_detail_url(activity)
  params = {
    'action': 'TEMPLATE',
    'text': truncate_for_url(activity.title, 80),
    'dates': f'{start}/{end}',
    'details': f'詳情：{detail_url}',
    'location': truncate_for_url(f'桃園市{activity.district or ""}{activity.location or ""}', 120),
  }
  url = 'https://calendar.google.com/calendar/render?' + urllib.parse.urlencode(params)
  if len(url) <= 950:
    return url
  params['location'] = truncate_for_url(f'桃園市{activity.district or ""}', 40)
  url = 'https://calendar.google.com/calendar/render?' + urllib.parse.urlencode(params)
  if len(url) <= 950:
    return url
  params.pop('details', None)
  return 'https://calendar.google.com/calendar/render?' + urllib.parse.urlencode(params)


def truncate_for_url(value, limit):
  text = re.sub(r'\s+', ' ', str(value or '')).strip()
  return text[:limit]


def google_datetime(value):
  if not value:
    return None
  return timezone.localtime(value).strftime('%Y%m%dT%H%M%S')


def elapsed_ms(started_at):
  return int((time.monotonic() - started_at) * 1000)
