import urllib.parse

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import FollowEvent, MessageEvent, PostbackEvent, TextMessage

from events.models import Activity
from .line_services import (
  get_or_create_line_user,
  handle_activity_postback,
  handle_line_text_message,
  record_action,
  safe_detail_url,
  google_calendar_url,
  google_maps_url,
)


line_bot_api = LineBotApi(settings.LINE_CHANNEL_ACCESS_TOKEN) if settings.LINE_CHANNEL_ACCESS_TOKEN else None
parser = WebhookParser(settings.LINE_CHANNEL_SECRET) if settings.LINE_CHANNEL_SECRET else None


@csrf_exempt
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


def dispatch_line_event(event):
  if isinstance(event, FollowEvent):
    user = get_or_create_line_user(getattr(event.source, 'user_id', ''), fetch_display_name(event.source.user_id))
    return build_preference_message(user)

  if isinstance(event, PostbackEvent):
    return handle_postback_event(event)

  if isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
    return handle_text_message(event)

  return None


def handle_postback_event(event):
  user = get_or_create_line_user(getattr(event.source, 'user_id', ''))
  params = dict(urllib.parse.parse_qsl(event.postback.data or ''))
  return handle_activity_postback(user, params.get('action'), params)


def handle_text_message(event):
  text = event.message.text.strip()
  user = get_or_create_line_user(getattr(event.source, 'user_id', ''))
  return handle_line_text_message(user, text)


def fetch_display_name(line_user_id):
  if not line_user_id or line_bot_api is None:
    return '桃園市民'
  try:
    return line_bot_api.get_profile(line_user_id).display_name
  except Exception:
    return '桃園市民'


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


def track_calendar(request, activity_id):
  activity = Activity.objects.filter(id=activity_id).first()
  if not activity:
    raise Http404('Activity not found')
  user = user_from_tracking_request(request)
  if user:
    record_action(user, activity, 'add_calendar', {'source': 'tracking_redirect', 'interested': True})
  return HttpResponseRedirect(google_calendar_url(activity))


def track_maps(request, activity_id):
  activity = Activity.objects.filter(id=activity_id).first()
  if not activity:
    raise Http404('Activity not found')
  user = user_from_tracking_request(request)
  if user:
    record_action(user, activity, 'how_to_go', {'source': 'tracking_redirect'})
  return HttpResponseRedirect(google_maps_url(activity.district, activity.location))


def user_from_tracking_request(request):
  line_user_id = request.GET.get('line_user_id') or ''
  if not line_user_id:
    return None
  return get_or_create_line_user(line_user_id)
