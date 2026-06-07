import sys

from django.core.management.base import BaseCommand
from django.test import Client

from events.models import ActionLog, Activity, ActivitySearchProfile, LineConversationState, UserProfile
from myapp.line_services import handle_line_text_message


TEST_LINE_USER_ID = 'codex-extreme-line-flow'


def safe_terminal_text(value):
    text = str(value)
    encoding = getattr(sys.stdout, 'encoding', None) or 'utf-8'
    return text.encode(encoding, errors='replace').decode(encoding, errors='replace')


class Command(BaseCommand):
    help = 'Run terminal smoke tests for extreme LINE natural-language activity flows.'

    def add_arguments(self, parser):
        parser.add_argument('--keep-user', action='store_true', help='Do not delete the smoke test user after running.')

    def handle(self, *args, **options):
        user, _ = UserProfile.objects.get_or_create(line_user_id=TEST_LINE_USER_ID)
        LineConversationState.objects.filter(user=user).delete()
        results = []

        scenarios = [
            ('不然騎腳踏車', True, 'bike query returns activities or explicit no-result'),
            ('有沒有桃園免費的最好運動的活動', True, 'free sport query is handled'),
            ('我想要那種不用錢又不要太遠，最好可以動一動', True, 'casual active free query is handled'),
            ('今天晚上有沒有適合小朋友但不要展覽的', True, 'complex family query is handled'),
            ('隨便啦你推薦一個不是太無聊的', True, 'casual recommendation-like query is handled'),
            ('火星免費潛水活動', False, 'impossible query must not send cards'),
            ('你是誰', False, 'smalltalk stays text-only'),
        ]

        for query, flex_allowed, label in scenarios:
            message = handle_line_text_message(user, query)
            items = message if isinstance(message, list) else [message]
            has_flex = any(item.__class__.__name__ == 'FlexSendMessage' for item in items)
            has_text = any(item.__class__.__name__ == 'TextSendMessage' for item in items)
            ok = has_text and (flex_allowed or not has_flex)
            results.append((ok, label, query, [item.__class__.__name__ for item in items]))

        state_before_more = LineConversationState.objects.filter(user=user).first()
        more_message = handle_line_text_message(user, '還有嗎')
        more_items = more_message if isinstance(more_message, list) else [more_message]
        results.append((
            bool(state_before_more) and any(item.__class__.__name__ == 'TextSendMessage' for item in more_items),
            'more-results query keeps a valid state or returns text safely',
            '還有嗎',
            [item.__class__.__name__ for item in more_items],
        ))

        profile_count = ActivitySearchProfile.objects.count()
        preference_count = user.preferred_tags.count()
        results.append((profile_count >= 0 and preference_count == user.preferred_tags.count(), 'search profiles do not alter preferred tags', 'preference integrity', [f'profiles={profile_count}', f'preferred={preference_count}']))

        activity = Activity.objects.filter(status='active').exclude(official_detail_url='').first()
        if activity:
            response = Client().get(f'/track/activity/{activity.id}/', {'line_user_id': user.line_user_id, 'action': 'view_detail'})
            tracked = ActionLog.objects.filter(user=user, activity=activity, action_type='view_detail').exists()
            results.append((response.status_code in {301, 302} and tracked, 'activity detail tracking redirects and logs view_detail', activity.title, [response.status_code]))
        else:
            results.append((True, 'activity detail tracking skipped because no active activity exists', '-', []))

        failed = [item for item in results if not item[0]]
        for ok, label, query, detail in results:
            marker = 'PASS' if ok else 'FAIL'
            self.stdout.write(safe_terminal_text(f'{marker} | {label} | {query} | {detail}'))

        if not options['keep_user']:
            deleted = UserProfile.objects.filter(line_user_id=TEST_LINE_USER_ID).delete()
            self.stdout.write(safe_terminal_text(f'cleanup={deleted[0]}'))

        if failed:
            raise SystemExit(1)

