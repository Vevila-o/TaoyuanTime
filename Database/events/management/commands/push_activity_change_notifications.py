from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from linebot import LineBotApi
from linebot.exceptions import LineBotApiError
from linebot.models import TextSendMessage

from events.models import ActivityChangeLog, PushDeliveryLog, Subscription


class Command(BaseCommand):
    help = 'Push LINE notifications for important activity changes.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        changes = (ActivityChangeLog.objects
                   .select_related('activity')
                   .filter(notify_required=True, notified_at__isnull=True)
                   .order_by('created_at')[:options['limit']])
        self.stdout.write(f'Pending changes={len(changes)} dry_run={options["dry_run"]}')
        if options['dry_run']:
            for change in changes:
                subscribers = active_subscribers(change).count()
                self.stdout.write(f'change={change.id} activity={change.activity_id} field={change.field_name} subscribers={subscribers}')
            return

        token = getattr(settings, 'LINE_CHANNEL_ACCESS_TOKEN', '')
        if not token:
            self.stderr.write('LINE_CHANNEL_ACCESS_TOKEN is not configured.')
            return

        line_bot_api = LineBotApi(token)
        sent = 0
        failed = 0
        for change in changes:
            for subscription in active_subscribers(change):
                user = subscription.user
                dedupe_key = f'activity_change:{change.id}:{user.id}'
                if PushDeliveryLog.objects.filter(notification_type='activity_change', dedupe_key=dedupe_key, status='sent').exists():
                    continue
                try:
                    line_bot_api.push_message(user.line_user_id, TextSendMessage(text=change_message(change)))
                    PushDeliveryLog.objects.create(
                        user=user,
                        activity=change.activity,
                        status='sent',
                        notification_type='activity_change',
                        dedupe_key=dedupe_key,
                        line_response='push_activity_change_notifications',
                        sent_at=timezone.now(),
                    )
                    sent += 1
                except LineBotApiError as exc:
                    failed += 1
                    PushDeliveryLog.objects.create(
                        user=user,
                        activity=change.activity,
                        status='failed',
                        notification_type='activity_change',
                        dedupe_key=dedupe_key,
                        error_message=str(exc),
                    )
                except Exception as exc:
                    failed += 1
                    PushDeliveryLog.objects.create(
                        user=user,
                        activity=change.activity,
                        status='failed',
                        notification_type='activity_change',
                        dedupe_key=dedupe_key,
                        error_message=str(exc),
                    )
            change.notified_at = timezone.now()
            change.save(update_fields=['notified_at'])

        self.stdout.write(self.style.SUCCESS(f'Done. sent={sent}, failed={failed}'))


def active_subscribers(change):
    return Subscription.objects.select_related('user').filter(
        activity=change.activity,
        status='active',
        user__push_enabled=True,
    ).exclude(user__line_user_id='')


def change_message(change):
    labels = {
        'title': '活動名稱',
        'start_date': '開始時間',
        'end_date': '結束時間',
        'location': '地點',
        'registration_url': '報名連結',
        'status': '活動狀態',
    }
    label = labels.get(change.field_name, change.field_name)
    return (
        f'您訂閱的活動有重要更新：\n'
        f'{change.activity.title}\n\n'
        f'{label} 已更新。\n'
        f'原本：{change.old_value or "官方未提供"}\n'
        f'現在：{change.new_value or "官方未提供"}'
    )
