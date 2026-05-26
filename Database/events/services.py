from django.utils import timezone
from django.db.models import Count, Q
from .models import Activity, UserProfile, Subscription, ActionLog, Tag
from datetime import timedelta


def recommend_activities_for_user(user: UserProfile, limit: int = 3):
    """
    根據使用者 preferred_tags 推薦活動（最多 limit 筆）。
    條件：status='active'、尚未過期（end_date 為 null 或 >= now）。
    排序以符合標籤數與開始時間優先。
    """
    # use recommendation-ready queryset
    base_qs = get_recommendation_ready_activities()
    tags = user.preferred_tags.filter(is_active=True)
    if not tags.exists():
        return list(base_qs.order_by('start_date')[:limit])
    qs = (base_qs.filter(tags__in=tags)
          .annotate(match_count=Count('tags'))
          .order_by('-match_count', 'start_date')
          .distinct()[:limit])
    return list(qs)


def search_activities_by_conditions(district=None, tag_names=None, is_free=None, start_date=None, end_date=None, limit=3, ai_mode: bool = False):
    """
    搜尋活動條件：district(字串包含)、tag_names (list of tag names)、is_free (bool)、start_date/end_date (datetime/date)
    只回傳 status='active' 且尚未過期的活動。
    """
    # choose base queryset: AI mode uses AI-ready activities, otherwise public items
    qs = get_ai_ready_activities() if ai_mode else get_public_items()
    if district:
        qs = qs.filter(district__icontains=district)
    if is_free is not None:
        qs = qs.filter(is_free=is_free)
    if start_date:
        qs = qs.filter(start_date__gte=start_date)
    if end_date:
        qs = qs.filter(end_date__lte=end_date)
    if tag_names:
        tags = Tag.objects.filter(name__in=tag_names, is_active=True)
        if tags.exists():
            qs = qs.filter(tags__in=tags)
        else:
            return []
    return list(qs.distinct().order_by('start_date')[:limit])


def get_public_items():
    """Items that are public and have official detail page"""
    now = timezone.now()
    qs = Activity.objects.filter(status='active').filter(
        Q(end_date__isnull=True) | Q(end_date__gte=now)
    ).filter(is_public_item=True).exclude(official_detail_url__isnull=True).exclude(official_detail_url='')
    return qs


def get_ai_ready_activities():
    """Activities suitable for AI processing"""
    now = timezone.now()
    qs = Activity.objects.filter(status='active').filter(
        Q(end_date__isnull=True) | Q(end_date__gte=now)
    ).filter(is_activity=True, ai_ready=True).exclude(official_detail_url__isnull=True).exclude(official_detail_url='')
    return qs


def get_recommendation_ready_activities():
    """Activities allowed into recommendation pool"""
    now = timezone.now()
    qs = Activity.objects.filter(status='active').filter(
        Q(end_date__isnull=True) | Q(end_date__gte=now)
    ).filter(is_activity=True, recommendation_ready=True).exclude(official_detail_url__isnull=True).exclude(official_detail_url='')
    return qs


def log_user_action(user: UserProfile, action_type: str, activity: Activity = None, metadata: dict = None):
    """記錄使用者互動至 ActionLog"""
    ActionLog.objects.create(
        user=user,
        activity=activity,
        action_type=action_type,
        metadata=metadata or {}
    )


def get_due_subscriptions(window_hours: int = 24):
    """
    回傳需要在接下來 window_hours 小時內發送提醒的 Subscription 列表。
    條件：is_notified=False，並且 activity.start_date - remind_before_days 在 now..now+window_hours
    注意：MVP 使用 Python 層過濾，若資料量大應改為 SQL/aggregate。
    """
    now = timezone.now()
    window_end = now + timedelta(hours=window_hours)
    subs = Subscription.objects.select_related('activity', 'user').filter(is_notified=False)
    due = []
    for s in subs:
        if not s.activity or not s.activity.start_date:
            continue
        remind_time = s.activity.start_date - timedelta(days=s.remind_before_days)
        if now <= remind_time <= window_end:
            due.append(s)
    return due


def get_line_card_payload(activity: Activity) -> dict:
    """Return a clean payload dict for LINE card usage.

    Only return payload if activity.line_ready is True.
    """
    if not getattr(activity, 'line_ready', False):
        return None
    return {
        'title': activity.title,
        'description': activity.description or '',
        'district': activity.district,
        'location': activity.location,
        'start_date': activity.start_date.isoformat() if activity.start_date else None,
        'end_date': activity.end_date.isoformat() if activity.end_date else None,
        'image_url': activity.image_url,
        'source_url': activity.source_url,
        'tags': [t.name for t in activity.tags.all()],
        'is_free': activity.is_free,
        'requires_registration': activity.requires_registration,
    }
