from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from linebot import LineBotApi
from linebot.exceptions import LineBotApiError
from linebot.models import FlexSendMessage

from events.models import PushDeliveryLog
from events.services import get_due_subscriptions, log_user_action
from myapp.line_services import build_activity_carousel


class Command(BaseCommand):
    help = 'Push LINE reminders for due activity subscriptions.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--window-hours',
            type=int,
            default=24,
            help='Reminder lookup window in hours.',
        )

    def handle(self, *args, **options):
        token = getattr(settings, 'LINE_CHANNEL_ACCESS_TOKEN', '')
        if not token:
            self.stderr.write('LINE_CHANNEL_ACCESS_TOKEN is not configured.')
            return

        line_bot_api = LineBotApi(token)
        due_subscriptions = get_due_subscriptions(window_hours=options['window_hours'])
        self.stdout.write(f'Found {len(due_subscriptions)} due subscriptions.')

        pushed = 0
        failed = 0
        for subscription in due_subscriptions:
            user = subscription.user
            activity = subscription.activity
            if not user or not activity or not user.line_user_id:
                continue
            dedupe_key = f'reminder:{subscription.id}:{activity.id}:{subscription.remind_before_days}:{activity.start_date:%Y%m%d%H%M}' if activity.start_date else f'reminder:{subscription.id}:{activity.id}'
            if PushDeliveryLog.objects.filter(notification_type='subscription_reminder', dedupe_key=dedupe_key, status='sent').exists():
                continue

            try:
                line_bot_api.push_message(
                    user.line_user_id,
                    FlexSendMessage(
                        alt_text=f'{subscription.remind_before_days} 天後活動開始，提醒您：{activity.title}',
                        contents=build_activity_carousel([activity], user=user),
                    ),
                )
                subscription.is_notified = True
                subscription.last_notified_at = timezone.now()
                subscription.save(update_fields=['is_notified', 'last_notified_at'])
                PushDeliveryLog.objects.create(
                    user=user,
                    activity=activity,
                    status='sent',
                    notification_type='subscription_reminder',
                    dedupe_key=dedupe_key,
                    line_response='push_activity_reminders',
                    sent_at=timezone.now(),
                )
                log_user_action(
                    user=user,
                    action_type='view_card',
                    activity=activity,
                    metadata={'source': 'push_activity_reminders', 'event': 'push_reminder'},
                )
                pushed += 1
            except LineBotApiError as exc:
                failed += 1
                PushDeliveryLog.objects.create(
                    user=user,
                    activity=activity,
                    status='failed',
                    notification_type='subscription_reminder',
                    dedupe_key=dedupe_key,
                    error_message=str(exc),
                )
                self.stderr.write(f'LINE push failed for user={user.line_user_id}: {exc}')
            except Exception as exc:
                failed += 1
                PushDeliveryLog.objects.create(
                    user=user,
                    activity=activity,
                    status='failed',
                    notification_type='subscription_reminder',
                    dedupe_key=dedupe_key,
                    error_message=str(exc),
                )
                self.stderr.write(f'Reminder failed for user={user.line_user_id}: {exc}')

        self.stdout.write(self.style.SUCCESS(f'Done. pushed={pushed}, failed={failed}'))
