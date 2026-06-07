from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from linebot import LineBotApi
from linebot.exceptions import LineBotApiError
from linebot.models import FlexSendMessage

from events.models import PushDeliveryLog, UserProfile
from events.services import activity_business_key
from myapp.line_services import build_activity_carousel, get_recommended_activities


class Command(BaseCommand):
    help = 'Push periodic personalized activity recommendations to LINE users.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--limit-users', type=int, default=200)

    def handle(self, *args, **options):
        users = due_users()[:options['limit_users']]
        self.stdout.write(f'Due users={len(users)} dry_run={options["dry_run"]}')
        if options['dry_run']:
            for user in users:
                activities = get_recommended_activities(
                    user,
                    limit=3,
                    use_ai=False,
                    exclude_subscribed=True,
                    exclude_recently_pushed=True,
                )
                self.stdout.write(f'user={user.line_user_id} activities={len(activities)}')
            return

        token = getattr(settings, 'LINE_CHANNEL_ACCESS_TOKEN', '')
        if not token:
            self.stderr.write('LINE_CHANNEL_ACCESS_TOKEN is not configured.')
            return

        line_bot_api = LineBotApi(token)
        pushed = 0
        failed = 0
        for user in users:
            activities = get_recommended_activities(
                user,
                limit=3,
                use_ai=False,
                exclude_subscribed=True,
                exclude_recently_pushed=True,
            )
            if not activities:
                continue
            business_keys = [activity_business_key(activity) for activity in activities]
            already_sent = PushDeliveryLog.objects.filter(
                user=user,
                notification_type='recommendation',
                status='sent',
                dedupe_key__in=[
                    f'recommendation:{user.id}:{key}:{timezone.localdate().isoformat()}'
                    for key in business_keys
                ],
            ).exists()
            if already_sent:
                continue
            try:
                line_bot_api.push_message(
                    user.line_user_id,
                    FlexSendMessage(
                        alt_text='今日桃園活動推薦',
                        contents=build_activity_carousel(activities, user=user),
                    ),
                )
                user.last_recommend_pushed_at = timezone.now()
                user.save(update_fields=['last_recommend_pushed_at', 'updated_at'])
                for activity in activities:
                    key = activity_business_key(activity)
                    PushDeliveryLog.objects.create(
                        user=user,
                        activity=activity,
                        status='sent',
                        notification_type='recommendation',
                        dedupe_key=f'recommendation:{user.id}:{key}:{timezone.localdate().isoformat()}',
                        line_response='push_recommendations',
                        sent_at=timezone.now(),
                    )
                pushed += 1
            except LineBotApiError as exc:
                failed += 1
                PushDeliveryLog.objects.create(
                    user=user,
                    status='failed',
                    notification_type='recommendation',
                    dedupe_key=f'recommendation:{user.id}:failed:{timezone.localdate().isoformat()}',
                    error_message=str(exc),
                )
            except Exception as exc:
                failed += 1
                PushDeliveryLog.objects.create(
                    user=user,
                    status='failed',
                    notification_type='recommendation',
                    dedupe_key=f'recommendation:{user.id}:failed:{timezone.localdate().isoformat()}',
                    error_message=str(exc),
                )

        self.stdout.write(self.style.SUCCESS(f'Done. pushed={pushed}, failed={failed}'))


def due_users():
    now = timezone.now()
    candidates = UserProfile.objects.filter(
        push_enabled=True,
        recommend_push_enabled=True,
    ).exclude(line_user_id='')
    users = []
    for user in candidates:
        interval = user.recommend_push_interval_days or 3
        last_pushed = user.last_recommend_pushed_at
        if last_pushed is None or last_pushed <= now - timedelta(days=interval):
            users.append(user)
    return users
