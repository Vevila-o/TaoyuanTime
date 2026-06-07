from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone
from linebot import LineBotApi
from linebot.exceptions import LineBotApiError
from linebot.models import FlexSendMessage, TextSendMessage

from events.models import PushDeliveryLog, UserProfile
from events.services import activity_business_key
from myapp.line_services import build_activity_carousel


@dataclass
class PushResult:
    users: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    error: str = ""


def select_campaign_audience(campaign):
    rule = campaign.audience_rule or {}
    rule_type = rule.get('type', 'all_push_enabled')
    qs = UserProfile.objects.filter(push_enabled=True).exclude(line_user_id='')
    if rule_type == 'preferred_tags' and campaign.activity_id:
        tags = campaign.activity.tags.all()
        if tags.exists():
            return qs.filter(preferred_tags__in=tags).distinct()
    if rule_type == 'subscribers' and campaign.activity_id:
        return qs.filter(subscriptions__activity=campaign.activity, subscriptions__status='active').distinct()
    return qs


def build_campaign_message(campaign, user=None):
    if campaign.activity_id:
        return FlexSendMessage(
            alt_text=campaign.title,
            contents=build_activity_carousel([campaign.activity], user=user),
        )
    text = campaign.message or campaign.title
    return TextSendMessage(text=text)


def send_campaign(campaign, dry_run=False):
    users = select_campaign_audience(campaign)
    result = PushResult(users=users.count())
    if dry_run:
        for user in users:
            dedupe_key = campaign_dedupe_key(campaign, user)
            if PushDeliveryLog.objects.filter(notification_type='campaign', dedupe_key=dedupe_key, status='sent').exists():
                result.skipped += 1
        return result

    token = getattr(settings, 'LINE_CHANNEL_ACCESS_TOKEN', '')
    if not token:
        result.error = 'LINE_CHANNEL_ACCESS_TOKEN is not configured.'
        return result

    line_bot_api = LineBotApi(token)
    campaign.status = 'sending'
    campaign.save(update_fields=['status', 'updated_at'])

    for user in users:
        dedupe_key = campaign_dedupe_key(campaign, user)
        if PushDeliveryLog.objects.filter(notification_type='campaign', dedupe_key=dedupe_key, status='sent').exists():
            result.skipped += 1
            continue
        message = build_campaign_message(campaign, user=user)
        try:
            line_bot_api.push_message(user.line_user_id, message)
            PushDeliveryLog.objects.create(
                campaign=campaign,
                user=user,
                activity=campaign.activity,
                status='sent',
                notification_type='campaign',
                dedupe_key=dedupe_key,
                line_response='ok',
                sent_at=timezone.now(),
            )
            result.sent += 1
        except LineBotApiError as exc:
            record_campaign_failure(campaign, user, dedupe_key, exc)
            result.failed += 1
        except Exception as exc:
            record_campaign_failure(campaign, user, dedupe_key, exc)
            result.failed += 1

    campaign.status = 'sent' if result.failed == 0 else 'failed'
    campaign.save(update_fields=['status', 'updated_at'])
    return result


def campaign_dedupe_key(campaign, user):
    if campaign.activity_id:
        return f'campaign_activity:{activity_business_key(campaign.activity)}:{user.id}'
    return f'campaign:{campaign.id}:{user.id}'


def record_campaign_failure(campaign, user, dedupe_key, exc):
    PushDeliveryLog.objects.create(
        campaign=campaign,
        user=user,
        activity=campaign.activity,
        status='failed',
        notification_type='campaign',
        dedupe_key=dedupe_key,
        error_message=str(exc),
    )
