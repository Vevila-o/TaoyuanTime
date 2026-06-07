from datetime import timedelta
import re
from urllib.parse import parse_qs, urlparse

from django.db.models import Count, Q
from django.utils import timezone

from .models import Activity, ActivityAsset, UserProfile, Subscription, ActionLog, Tag


SOURCE_PRIORITY = {
    "tycg_events": 1,
    "culture": 2,
    "travel_openapi": 3,
    "tmofa_exhibitions": 4,
    "tmofa_events": 5,
    "library_activity_rss": 6,
    "wem_news_photo": 7,
    "sports_rss": 8,
    "agriculture": 9,
    "economic": 10,
    "youth": 11,
    "hakka": 12,
    "travel_news": 13,
    "tycg_events_rss": 30,
    "culture_rss": 31,
    "economic_rss": 32,
    "agriculture_rss": 33,
    "hakka_rss": 34,
    "hakka_json": 35,
    "youth_hot_rss": 36,
    "youth_news_rss": 37,
    "animal_rss": 38,
}

def recommend_activities_for_user(user: UserProfile, limit: int = 3):
    """
    根據使用者 preferred_tags 推薦活動（最多 limit 筆）。
    條件：status='active'、尚未過期（end_date 為 null 或 >= now）。
    排序以符合標籤數與開始時間優先。
    """
    base_qs = get_recommendation_ready_activities()
    tags = user.preferred_tags.filter(is_active=True)
    if not tags.exists():
        candidates = list(base_qs.order_by('start_date', 'id')[:max(limit * 6, limit)])
        return dedupe_activities_by_business_key(candidates, limit=limit)
    qs = (base_qs.filter(tags__in=tags)
          .annotate(match_count=Count('tags'))
          .order_by('-match_count', 'start_date')
          .distinct()[:max(limit * 6, limit)])
    return dedupe_activities_by_business_key(list(qs), limit=limit)


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
    ).filter(is_public_item=True).exclude(official_detail_url__isnull=True).exclude(official_detail_url='').exclude(official_link_status='dead')
    return qs


def get_ai_ready_activities():
    """Activities suitable for AI processing"""
    now = timezone.now()
    qs = Activity.objects.filter(status='active').filter(
        Q(end_date__isnull=True) | Q(end_date__gte=now)
    ).filter(is_activity=True, ai_ready=True).exclude(official_detail_url__isnull=True).exclude(official_detail_url='').exclude(official_link_status='dead')
    return qs


def get_recommendation_ready_activities():
    """Activities allowed into recommendation pool"""
    now = timezone.now()
    qs = Activity.objects.filter(status='active').filter(
        Q(end_date__isnull=True) | Q(end_date__gte=now)
    ).filter(is_activity=True, recommendation_ready=True).exclude(official_detail_url__isnull=True).exclude(official_detail_url='').exclude(official_link_status='dead')
    return qs


def normalize_activity_title(title):
    text = str(title or "").lower()
    text = re.sub(r"[\s　]+", "", text)
    return re.sub(r"[【】\[\]（）()《》「」『』:：\-－_｜|]", "", text)


def detail_item_id(url):
    parsed = urlparse(str(url or "").strip())
    query = parse_qs(parsed.query)
    for key in ("s", "id", "sn", "actid", "actId"):
        values = query.get(key)
        if values:
            return f"{key.lower()}:{values[0]}"
    return ""


def activity_business_key(activity):
    keys = activity_business_keys(activity)
    return keys[0] if keys else f"id:{activity.id}"


def activity_business_keys(activity):
    keys = []
    seen = set()

    def add(key):
        if key and key not in seen:
            keys.append(key)
            seen.add(key)

    for url in (getattr(activity, "official_detail_url", ""), getattr(activity, "source_url", "")):
        item_id = detail_item_id(url)
        if item_id:
            add(f"detail:{item_id}")

    title = normalize_activity_title(getattr(activity, "title", ""))
    start = getattr(activity, "start_date", None)
    place = re.sub(r"[\s　]+", "", f"{getattr(activity, 'location', '') or ''}{getattr(activity, 'district', '') or ''}")
    if title and start and place:
        add(f"title:{title}|{start.isoformat()}|{place}")

    source_key = getattr(activity, "source_key", "") or ""
    source_item_id = getattr(activity, "source_item_id", "") or ""
    if source_key and source_item_id:
        add(f"item:{source_key}:{source_item_id}")

    for url in (getattr(activity, "official_detail_url", ""), getattr(activity, "source_url", "")):
        normalized_url = str(url or "").strip().rstrip("/")
        if normalized_url:
            add(f"url:{normalized_url}")

    add(f"id:{activity.id}")
    return keys


def activity_source_rank(activity):
    source_rank = SOURCE_PRIORITY.get(getattr(activity, "source_key", "") or "", 99)
    quality_score = getattr(activity, "quality_score", None) or 0
    has_image = 0 if getattr(activity, "image_url", "") else 1
    has_summary = 0 if getattr(activity, "ai_summary", "") else 1
    return (source_rank, -quality_score, has_image, has_summary, getattr(activity, "id", 0))


def dedupe_activities_by_business_key(activities, limit=None):
    best_by_group = {}
    key_to_group = {}
    ordered_groups = []
    for activity in activities:
        keys = activity_business_keys(activity)
        group = next((key_to_group[key] for key in keys if key in key_to_group), None)
        if group is None:
            group = keys[0]
            ordered_groups.append(group)
        for key in keys:
            key_to_group[key] = group
        current = best_by_group.get(group)
        if current is None:
            best_by_group[group] = activity
        elif activity_source_rank(activity) < activity_source_rank(current):
            best_by_group[group] = activity
    deduped = [best_by_group[group] for group in ordered_groups]
    return deduped[:limit] if limit else deduped


def is_seed_activity(activity):
    title = getattr(activity, "title", "") or ""
    source_url = getattr(activity, "source_url", "") or ""
    official_url = getattr(activity, "official_detail_url", "") or ""
    image_url = getattr(activity, "image_url", "") or ""
    if title.startswith("測試非活動"):
        return True
    if "/sample/" in source_url or "/sample/" in official_url:
        return True
    return "placehold.co" in image_url and not (source_url or official_url)


TAOYUAN_DISTRICTS = (
    "桃園", "中壢", "平鎮", "八德", "楊梅", "蘆竹", "大溪", "龍潭", "龜山",
    "大園", "觀音", "新屋", "復興",
)

TAOYUAN_DISTRICT_ALIASES = {
    "桃園展演中心": "桃園區",
    "木育教室": "大溪區",
    "武德殿": "大溪區",
    "大溪木藝生態博物館": "大溪區",
    "大古山": "蘆竹區",
    "坑子溪": "蘆竹區",
    "阿姆坪": "大溪區",
}


def normalize_taoyuan_district(value):
    text = str(value or "").strip()
    if not text:
        return ""
    for district in TAOYUAN_DISTRICTS:
        if text == district or text == f"{district}區" or f"{district}區" in text:
            return f"{district}區"
    return ""


def infer_taoyuan_district_from_text(*texts, raw_html_path=""):
    joined = " ".join(str(text or "") for text in texts if text)
    search_text = joined
    explicit_matches = []
    for district in TAOYUAN_DISTRICTS:
        if f"桃園市{district}區" in search_text or f"{district}區" in search_text:
            explicit_matches.append(district)
    if len(set(explicit_matches)) == 1:
        return f"{explicit_matches[0]}區"

    if "wem.tycg.gov.tw" in search_text or "大溪木藝生態博物館" in search_text:
        return "大溪區"

    surface_text = " ".join(str(text or "") for text in texts[:2] if text)
    alias_matches = {
        district
        for alias, district in TAOYUAN_DISTRICT_ALIASES.items()
        if alias in surface_text
    }
    if len(alias_matches) == 1:
        return alias_matches.pop()

    soft_matches = []
    for district in TAOYUAN_DISTRICTS:
        if district == "桃園":
            continue
        if district in surface_text:
            soft_matches.append(district)
    if len(set(soft_matches)) == 1:
        return f"{soft_matches[0]}區"
    return ""


def is_test_line_user(user):
    line_user_id = getattr(user, "line_user_id", "") or ""
    return (
        line_user_id.startswith("codex")
        or line_user_id.startswith("line-test")
        or line_user_id.startswith("U_sample")
        or line_user_id == "debug-user"
    )


def log_user_action(user: UserProfile, action_type: str, activity: Activity = None, metadata: dict = None):
    """記錄使用者互動至 ActionLog"""
    ActionLog.objects.create(
        user=user,
        activity=activity,
        action_type=action_type,
        metadata=metadata or {}
    )


def backfill_activity_assets_from_images(limit=None, dry_run=True):
    qs = Activity.objects.exclude(image_url="").order_by("id")
    created = 0
    skipped = 0
    checked = 0
    for activity in qs:
        if limit and checked >= limit:
            break
        checked += 1
        url = activity.ocr_image_url or activity.image_url
        if not url:
            skipped += 1
            continue
        exists = ActivityAsset.objects.filter(activity=activity, url=url).exists()
        if exists:
            skipped += 1
            continue
        if not dry_run:
            ActivityAsset.objects.create(
                activity=activity,
                url=url,
                asset_type="poster",
                is_primary=True,
                ocr_eligible=bool(url.startswith("https://")),
                quality_warning="backfilled_from_activity_image_url",
            )
        created += 1
    return {"checked": checked, "created": created, "skipped": skipped, "dry_run": dry_run}


def get_due_subscriptions(window_hours: int = 24):
    """
    回傳需要在接下來 window_hours 小時內發送提醒的 Subscription 列表。
    條件：is_notified=False，並且 activity.start_date - remind_before_days 在 now..now+window_hours
    注意：MVP 使用 Python 層過濾，若資料量大應改為 SQL/aggregate。
    """
    now = timezone.now()
    window_end = now + timedelta(hours=window_hours)
    subs = Subscription.objects.select_related('activity', 'user').filter(is_notified=False, status='active')
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
