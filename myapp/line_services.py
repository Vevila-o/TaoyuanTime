import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time as datetime_time, timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from linebot.models import FlexSendMessage, TextSendMessage

from events.models import AIProcessingLog, ActionLog, Activity, LineConversationState, PushDeliveryLog, Subscription, Tag, UserProfile
from events.ai_providers import call_json_with_fallback, call_text_with_fallback, payload_messages
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
  '市民卡', '週末', '周末', '今天', '今日', '明天', '推薦', '有啥', '有哪些',
  '想找', '找一下', '哪裡', '運動', '腳踏車', '自行車', '單車', '騎車',
  '不用錢', '免門票', '動一動', '小朋友', '兒童', '潛水', '去哪',
)
SMALLTALK_WORDS = ('你好', '嗨', 'hello', 'hi', '謝謝', '你是誰', '幫助', 'help')
PREFERENCE_COMMANDS = {'偏好設定', '設定偏好', '喜好設定'}
RECOMMENDATION_COMMANDS = {'推薦活動', '猜你喜歡', '今日推薦'}
SUBSCRIPTION_COMMANDS = {'已訂閱活動', '我的訂閱', '已訂閱'}
MORE_RESULT_WORDS = {'還有嗎', '還有沒有', '換一批', '再給我', '更多', '查看更多', '下一批'}
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
  {
    'title': '🎵 想找什麼類型的活動？',
    'tags': [
      {'name': '藝文', 'label': '🎨 藝文展覽'},
      {'name': '市集', 'label': '🛍️ 踩點市集'},
      {'name': '戶外', 'label': '🌲 戶外休閒'},
      {'name': '美食', 'label': '🍕 美食饗宴'},
      {'name': '音樂', 'label': '🎸 流行音樂'},
    ],
  },
  {
    'title': '👥 專屬合適對象',
    'tags': [
      {'name': '親子', 'label': '👨‍👩‍👧 親子同樂'},
      {'name': '學生', 'label': '🎒 學生專屬'},
      {'name': '情侶', 'label': '👩‍❤️‍👨 約會勝地'},
      {'name': '毛孩', 'label': '🐾 寵物友善'},
    ],
  },
  {
    'title': '🎁 好康與小資專區',
    'tags': [
      {'name': '免費', 'label': '💰 免費入場'},
      {'name': '市民卡', 'label': '💳 市民卡優惠'},
    ],
  },
  {
    'title': '📍 想看哪些地區？',
    'tags': [
      {'name': '桃園', 'label': '桃園'},
      {'name': '中壢', 'label': '中壢'},
      {'name': '平鎮', 'label': '平鎮'},
      {'name': '八德', 'label': '八德'},
      {'name': '楊梅', 'label': '楊梅'},
      {'name': '蘆竹', 'label': '蘆竹'},
      {'name': '大溪', 'label': '大溪'},
      {'name': '龍潭', 'label': '龍潭'},
      {'name': '龜山', 'label': '龜山'},
      {'name': '大園', 'label': '大園'},
      {'name': '觀音', 'label': '觀音'},
      {'name': '新屋', 'label': '新屋'},
      {'name': '復興', 'label': '復興'},
    ],
  },
]


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


def toggle_preference_tag(user, tag_name):
  tag = find_active_tag(tag_name)
  if not tag:
    return False
  if user.preferred_tags.filter(id=tag.id).exists():
    user.preferred_tags.remove(tag)
  else:
    user.preferred_tags.add(tag)
  return True


def get_recommended_activities(user, limit=3, use_ai=True, offset=0, exclude_subscribed=False, exclude_recently_pushed=False):
  pool_size = max(50, limit + offset + 20)
  candidates = recommend_activities_for_user(user, limit=pool_size)
  if not candidates:
    candidates = list(get_recommendation_ready_activities().order_by('start_date', 'id')[:pool_size])
  candidates = dedupe_activities_by_business_key(candidates)
  if exclude_subscribed:
    candidates = exclude_subscribed_equivalent_activities(user, candidates)
  if exclude_recently_pushed:
    candidates = exclude_recently_pushed_activities(user, candidates)
  ranked = rank_activities_for_user(user, candidates)
  ranked = blend_exploration_activity(user, rotate_recently_seen_activities(user, ranked), limit=max(limit + offset, limit))
  target_size = limit + offset
  if use_ai and len(ranked) > target_size:
    ai_limit = min(len(ranked), target_size + 10)
    ranked = rerank_activities_with_ai(user, '推薦活動', ranked, limit=ai_limit) or ranked
    ranked = blend_exploration_activity(user, rotate_recently_seen_activities(user, ranked), limit=max(limit + offset, limit))
  return ranked[offset:offset + limit]


def get_active_subscribed_activities(user, limit=10):
  now = timezone.now()
  subscriptions = (Subscription.objects
                   .select_related('activity')
                   .filter(user=user, status='active', activity__status='active')
                   .filter(Q(activity__end_date__isnull=True) | Q(activity__end_date__gte=now))
                   .order_by('activity__start_date', '-created_at')[:limit])
  return dedupe_activities_by_business_key([subscription.activity for subscription in subscriptions if subscription.activity], limit=limit)


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


def subscribed_business_keys(user, include_cancelled=False):
  qs = Subscription.objects.select_related('activity').filter(user=user)
  if not include_cancelled:
    qs = qs.filter(status='active')
  keys = set()
  for subscription in qs:
    if subscription.activity:
      keys.update(activity_business_keys(subscription.activity))
  return keys


def exclude_subscribed_equivalent_activities(user, activities):
  keys = subscribed_business_keys(user)
  if not keys:
    return activities
  return [activity for activity in activities if not keys.intersection(activity_business_keys(activity))]


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


def exclude_recently_pushed_activities(user, activities):
  keys = recent_pushed_business_keys(user)
  if not keys:
    return activities
  fresh = [activity for activity in activities if not keys.intersection(activity_business_keys(activity))]
  return fresh or activities


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


def activity_region_match(activity, preferred_regions):
  if not preferred_regions:
    return False
  district = (activity.district or '').replace('區', '')
  if district in preferred_regions:
    return True
  return any(tag.tag_type == 'region' and tag.name in preferred_regions for tag in activity.tags.all())


def subscribed_activity_score(user, activity):
  return -25 if equivalent_subscription_for_activity(user, activity) else 0


def recent_seen_penalty(user, activity):
  return -18 if recent_seen_business_keys(user).intersection(activity_business_keys(activity)) else 0


def exploration_candidates(user, activities):
  seen = recent_seen_business_keys(user)
  subscribed = subscribed_business_keys(user)
  return [
    activity for activity in activities
    if not seen.intersection(activity_business_keys(activity))
    and not subscribed.intersection(activity_business_keys(activity))
  ]


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


def high_confidence_activity_query(text):
  text = text or ''
  if is_lifestyle_activity_query(text):
    return True
  if any(term in text for term in ('活動', '推薦', '有沒有', '想看', '想找', '不用錢', '免門票')):
    return True
  if any(term in text for term in ('腳踏車', '自行車', '單車', '騎車', '運動', '動一動', '小朋友', '兒童', '孩子', '小孩', '潛水')):
    return True
  return False


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


def has_child_lifestyle_intent(compact):
  return (
    any(term in (compact or '') for term in CHILD_AUDIENCE_TERMS)
    and any(term in (compact or '') for term in CHILD_ACTIVITY_CONTEXT_TERMS)
  )


def has_rainy_lifestyle_intent(compact):
  return (
    any(term in (compact or '') for term in RAINY_ACTIVITY_TERMS)
    and any(term in (compact or '') for term in ('去哪', '哪裡', '活動', '推薦', '想找'))
  )


def has_date_lifestyle_intent(compact):
  return (
    any(term in (compact or '') for term in DATE_ACTIVITY_TERMS)
    and any(term in (compact or '') for term in ('約會', '去哪', '哪裡', '活動', '推薦', '想找'))
  )


def build_query_help_message():
  return TextSendMessage(
    text='我可以幫你找桃園活動。你可以試試：\n'
         '- 中壢免費活動\n'
         '- 週末親子活動\n'
         '- 桃園藝文展覽\n\n'
         '也可以點選單的「設定偏好」或「猜你喜歡」。'
  )


def handle_line_text_message(user, text):
  text = (text or '').strip()
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

  state = get_valid_conversation_state(user)
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


def handle_more_results_text(user, text, state):
  if not state:
    activities = get_recommended_activities(user, limit=3, exclude_subscribed=True)
    log_card_views(user, activities, source='line_more_without_context', query=text)
    save_conversation_state(user, 'recommendation', '推薦活動', {'mode': 'recommendation'}, activities, offset=len(activities))
    return build_activity_carousel_message(activities, alt_text='更多桃園活動', user=user, query_context='推薦活動', include_intro=True)

  offset = state.offset or len(state.last_activity_ids or []) or 3
  conditions = deserialize_conditions(state.conditions or {})
  if conditions.get('mode') == 'recommendation' or state.intent == 'recommendation':
    activities = get_recommended_activities(user, limit=3, offset=offset, exclude_subscribed=True)
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


def handle_refined_search_text(user, text, state):
  base_conditions = deserialize_conditions(state.conditions or {}) if state else {}
  if base_conditions.get('mode'):
    base_conditions = {}
  refined = merge_search_conditions(base_conditions, extract_conditions_from_message(user, text))
  query = combine_context_query(state.last_query if state else '', text)
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


def classify_line_intent(user, text, state=None):
  fallback = rule_classify_line_intent(text, state=state)
  # Deterministic control phrases should not be overridden by the model.
  if fallback in {'more_results', 'refine_search', 'unsupported_chat'}:
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


def normalize_line_intent(value, fallback):
  intent = str(value or '').strip()
  allowed = {'activity_search', 'more_results', 'refine_search', 'preference_help', 'subscription_help', 'unsupported_chat'}
  return intent if intent in allowed else fallback


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
  if state and looks_like_refinement(text) and not high_confidence_activity_query(text):
    return 'refine_search'
  if is_activity_query(text) or contains_known_tag(text):
    return 'activity_search'
  return 'unsupported_chat'


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


def contains_known_tag(text):
  if not text:
    return False
  return Tag.objects.filter(is_active=True, name__in=[tag for tag in Tag.objects.filter(is_active=True).values_list('name', flat=True) if tag and tag in text]).exists()


def combine_context_query(previous, current):
  previous = (previous or '').strip()
  current = (current or '').strip()
  if not previous:
    return current
  if not current or previous == current or previous.endswith(f'，{current}'):
    return previous
  return f'{previous}，{current}'


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
  merged['tag_names'] = tag_names
  return apply_nearby_preference(None, merged)


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


def serialize_conditions(conditions):
  result = {}
  for key, value in (conditions or {}).items():
    if key in {'start_date', 'end_date'} and hasattr(value, 'isoformat'):
      result[key] = value.isoformat()
    else:
      result[key] = value
  return result


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


def search_activities_for_line(user, query, limit=3, offset=0, conditions=None, return_conditions=False):
  query = (query or '').strip()
  if not query:
    return ([], conditions or {}) if return_conditions else []

  conditions = deserialize_conditions(conditions) if conditions is not None else extract_conditions_from_message(user, query)
  if force_no_result_query(query, conditions):
    return ([], conditions) if return_conditions else []
  pool_size = max(30, limit + offset + 10)
  candidates = query_activities_by_conditions(conditions, limit=pool_size)
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
  if len(ranked) > target_size:
    ai_limit = min(len(ranked), target_size + 10)
    ranked = rerank_activities_with_ai(user, query, ranked, limit=ai_limit) or ranked
    ranked = rotate_recently_seen_activities(user, ranked)
  if strict_district_requested(query, conditions):
    district = conditions.get('district') or ''
    ranked = [activity for activity in ranked if district in (activity.district or '')]
  result = ranked[offset:offset + limit]
  return (result, conditions) if return_conditions else result


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


def build_no_result_message(query=''):
  suffix = f'「{query}」' if query else '目前條件'
  return TextSendMessage(text=f'目前沒有找到符合{suffix}的活動，可以改查地區、活動類型或免費活動。')


def build_activity_intro_text(activities, query_context='推薦活動', user=None):
  count = len(activities)
  notice = next((getattr(activity, '_line_notice', '') for activity in activities if getattr(activity, '_line_notice', '')), '')
  if notice:
    return f'{notice}\n我先整理 {count} 個相近活動給你參考，詳細時間地點請以官方頁為準。'
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
          '你是桃園活動 LINE 助手。請用繁體中文回覆 1 到 2 句，最多 70 字。'
          '只能根據候選活動摘要說話，不可編造不存在的活動、日期、地點。'
          '如果 notice 空白，不能說沒有完全符合。'
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


def normalize_line_intro(text):
  text = re.sub(r'\s+', ' ', (text or '').strip())
  text = text.replace('沒有完全符合', '先整理')
  if len(text) > 90:
    text = text[:90].rstrip('，,。 ') + '。'
  return text


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


def compact_activity_summary(activity, limit=SUMMARY_MAX_LENGTH):
  text = activity.ai_summary or activity.description or '暫無活動摘要介紹。'
  text = re.sub(r'\s+', ' ', text).strip()
  if len(text) <= limit:
    return text
  return text[:limit].rstrip() + '...'


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


def is_line_safe_image_url(url):
  if not url or not str(url).startswith('https://'):
    return False
  if not str(url).isascii():
    return False
  parsed = urllib.parse.urlparse(str(url))
  return bool(parsed.scheme == 'https' and parsed.netloc)


def is_placeholder_image_url(url):
  parsed = urllib.parse.urlparse(str(url))
  return parsed.netloc.lower() in PLACEHOLDER_IMAGE_HOSTS


def default_remote_image_url(activity):
  if activity is None:
    return REMOTE_DEFAULT_IMAGES[0]
  seed = getattr(activity, 'id', None) or sum(ord(char) for char in (activity.title or ''))
  return REMOTE_DEFAULT_IMAGES[seed % len(REMOTE_DEFAULT_IMAGES)]


def choose_fallback_image(activity, image_urls):
  seed = getattr(activity, 'id', None) or sum(ord(char) for char in (activity.title or ''))
  return image_urls[seed % len(image_urls)]


def infer_fallback_image_key(activity):
  text = f'{activity.title or ""} {activity.description or ""}'
  for keyword, image_key in FALLBACK_IMAGE_KEYWORDS:
    if keyword in text:
      return image_key
  return ''


def static_line_image_url(file_name):
  if settings.PUBLIC_BASE_URL:
    return f'{settings.PUBLIC_BASE_URL}/static/img/line/{file_name}'
  return default_remote_image_url(None)


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


def set_subscription_reminder_days(user, activity_id, days_value):
  days = parse_positive_int(days_value, default=1)
  if days not in {1, 3, 5}:
    return TextSendMessage(text='提醒天數只能設定為 5 天、3 天或 1 天前。')
  activity = Activity.objects.filter(id=activity_id).first()
  subscription = equivalent_subscription_for_activity(user, activity) if activity else None
  if not subscription:
    return TextSendMessage(text='請先訂閱此活動，再設定提醒時間。')
  subscription.remind_before_days = days
  subscription.is_notified = False
  subscription.save(update_fields=['remind_before_days', 'is_notified'])
  return TextSendMessage(text=f'已設定為活動開始前 {days} 天提醒。')


def subscribe_activity(user, activity_id, source_action='subscribe_activity'):
  activity = Activity.objects.filter(id=activity_id).first()
  if not activity:
    return TextSendMessage(text='找不到這筆活動，可能已經下架或資料更新。')
  now = timezone.now()
  if activity.status != 'active' or (activity.end_date and activity.end_date < now):
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


def build_subscription_success_message(activity, subscription, created):
  title = f'訂閱成功！將於前 {subscription.remind_before_days} 天通知' if created else '您先前已訂閱過此活動'
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


def reminder_button(activity, days):
  return {
    'type': 'button',
    'style': 'secondary',
    'height': 'sm',
    'action': {
      'type': 'postback',
      'label': f'{days} 天前提醒',
      'data': f'action=set_reminder_days&activity_id={activity.id}&days={days}',
    },
  }


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


def extract_conditions_from_message(user, query):
  started_at = time.monotonic()
  fallback = rule_extract_conditions(query)
  try:
    payload = {
      'message': query,
      'allowed_districts': list(DISTRICTS),
      'allowed_tags': list(Tag.objects.filter(is_active=True).values_list('name', flat=True)[:200]),
      'output_schema': {
        'district': 'one district name without 區, or empty string',
        'tag_names': 'array of existing allowed tag names',
        'is_free': 'true, false, or null',
        'soft_topics': 'array of broad search topics, can include non-tag natural words',
        'related_terms': 'array of synonyms or related search terms',
        'keyword': 'short keyword if needed',
        'relax_order': 'array of fields to relax, for example keyword, is_free, soft_topics, district',
      },
      'examples': [
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
          'message': '週末中壢免費親子活動',
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
      ],
    }
    response = call_json_with_fallback(
      payload_messages(
        '你是桃園活動查詢搜尋計畫產生器。只輸出 JSON，不要解釋。'
        '你的任務是把活動相關口語轉成資料庫查詢條件，不可推薦或創造活動。'
        'district/tag_names 只能使用允許清單；tag_names 是正式篩選條件。'
        'soft_topics/related_terms 只作 ActivitySearchProfile 搜尋語意，不是正式 tag、不要放入使用者偏好。'
        '口語句要寬鬆處理；像「桃園的」「有沒有桃園活動」只抽 district=桃園，不要把語助詞放進 keyword。'
        '「我想帶小孩玩」這類生活語境可用 tag_names=親子，並把兒童/小朋友/家庭/放電放進 related_terms。'
        '「心情好差」「你會陪我聊天嗎」不是活動查詢，通常不應進到此搜尋計畫。',
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

  is_free = (conditions or {}).get('is_free')
  if is_free is not None:
    qs = qs.filter(is_free=bool(is_free))

  start_date = (conditions or {}).get('start_date')
  end_date = (conditions or {}).get('end_date')
  if start_date:
    qs = qs.filter(start_date__gte=start_date)
  if end_date:
    qs = qs.filter(start_date__lte=end_date)

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
    'soft_topics': soft_topics,
    'related_terms': related_terms,
  })
  conditions = {
    'district': district,
    'tag_names': tag_names,
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
  return terms


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
  strict_terms = set(strict_topic_terms(conditions))
  primary_terms = set(merge_query_terms(
    conditions.get('keyword'),
    conditions.get('soft_topics'),
    [term for term in (conditions.get('related_terms') or []) if term not in {'運動', '戶外'} and term not in WEAK_SEMANTIC_TERMS],
    limit=40,
  ))
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
    for term in terms:
      if not term:
        continue
      term_score = 0
      if term in title:
        term_score += 30
        if term in primary_terms:
          strict_surface_match = True
      if term in activity_tags:
        term_score += 22
        if term in primary_terms:
          strict_surface_match = True
      if tag_names and term in tag_names and term in activity_tags:
        term_score += 12
      if term in profile_text:
        term_score += 18
        if term in primary_terms and term in profile_terms_text:
          strict_surface_match = True
      if term in summary:
        term_score += 12
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
        continue
      activity._semantic_matches = matched_terms[:6]
      activity._semantic_relaxed = primary_score == 0
      if activity._semantic_relaxed:
        activity._line_notice = '先推薦相近活動。'
      scored.append((activity, score))
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
    return sorted(activities, key=lambda activity: (activity.start_date or timezone.now(), activity.id))
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
    return type_score + region_score + audience_score + cost_score + discount_score + action_score + seen_penalty + subscribed_penalty + date_score

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
