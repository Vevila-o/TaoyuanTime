import json
import time

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from events.ai_providers import call_json_with_fallback
from events.models import AIProcessingLog, Activity
from events.services import is_seed_activity


SUMMARY_MAX_LENGTH = 50


class Command(BaseCommand):
    help = 'Generate short ai_summary values for activities before LINE usage.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--activity-id', type=int)
        parser.add_argument('--force', action='store_true')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--show-targets', action='store_true')
        parser.add_argument('--include-seed', action='store_true')
        parser.add_argument(
            '--timeout-ms',
            type=int,
            default=None,
            help='Override AI_TIMEOUT_MS for this batch run.',
        )

    def handle(self, *args, **options):
        targets = summary_targets(options)
        if options["dry_run"] or options["show_targets"]:
            for activity in targets[:options["limit"]]:
                self.stdout.write(
                    f'id={activity.id} title={activity.title} source={activity.source_key or "-"} '
                    f'status={activity.status} line_ready={activity.line_ready} recommendation_ready={activity.recommendation_ready}'
                )
            if options["dry_run"]:
                self.stdout.write(self.style.SUCCESS(f'DRY RUN: target_count={min(len(targets), options["limit"])}'))
                return

        if options['timeout_ms'] is not None:
            self.stdout.write('timeout override is ignored by provider fallback; use AI_TIMEOUT_MS in .env.')

        updated = 0
        failed = 0
        for activity in targets[:options['limit']]:
            started_at = time.monotonic()
            source_text = build_source_text(activity)
            if not source_text:
                continue
            try:
                response = call_json_with_fallback(build_summary_messages(activity, source_text))
                result = response.parsed or {}
                summary = normalize_summary(result.get('summary'))
                if not summary:
                    raise ValueError('AI summary is empty')
                status = 'success'
                error = ''
            except Exception as exc:
                summary = compact_activity_summary(activity, SUMMARY_MAX_LENGTH)
                status = 'failed'
                error = str(exc)
                failed += 1

            activity.ai_summary = summary
            activity.save(update_fields=['ai_summary', 'updated_at'])
            AIProcessingLog.objects.create(
                activity=activity,
                task_type='summary',
                model=(response.model if status == 'success' else ''),
                prompt_version='summary-v1',
                input_summary=source_text[:500],
                output_json={'summary': summary},
                latency_ms=elapsed_ms(started_at),
                status=status,
                error=error[:1000],
            )
            updated += 1

        self.stdout.write(self.style.SUCCESS(f'Done. updated={updated}, failed={failed}'))


def summary_targets(options):
    now = timezone.now()
    if options.get('activity_id'):
        qs = Activity.objects.filter(id=options['activity_id'])
    else:
        qs = Activity.objects.filter(
            is_activity=True,
            status='active',
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=now)
        ).filter(
            Q(line_ready=True) | Q(recommendation_ready=True)
        ).exclude(
            official_detail_url__isnull=True
        ).exclude(
            official_detail_url=''
        )
    qs = qs.order_by('start_date', '-updated_at', 'id')
    if not options['force']:
        qs = qs.filter(ai_summary='')
    targets = list(qs)
    if not options.get('include_seed'):
        targets = [activity for activity in targets if not is_seed_activity(activity)]
    return targets


def build_source_text(activity):
    return ' '.join(filter(None, [
        activity.description,
        activity.ocr_summary,
        activity.ocr_text,
        activity.raw_content,
    ])).strip()


def build_summary_messages(activity, source_text):
    payload = {
        'activity': {
            'title': activity.title,
            'district': activity.district,
            'location': activity.location,
            'description': source_text[:1200],
        },
        'rules': [
            '只依輸入資料摘要，不可創造日期、地點、費用或活動內容',
            'summary 必須是繁體中文',
            f'summary 最多 {SUMMARY_MAX_LENGTH} 個中文字',
            'summary 適合放在 LINE 活動卡片，不要換行',
        ],
        'output_schema': {'summary': 'string'},
    }
    return [
        {
            'role': 'system',
            'content': (
                '你是桃園活動摘要器。只輸出 JSON object，不要 markdown。'
                'schema: {"summary": string}。'
            ),
        },
        {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
    ]


def normalize_summary(value):
    text = str(value or '').strip()
    text = ' '.join(text.split())
    return text[:SUMMARY_MAX_LENGTH]


def compact_activity_summary(activity, limit):
    source = build_source_text(activity) or activity.title
    text = ' '.join(str(source or '').split())
    return text[:limit]


def elapsed_ms(started_at):
    return int((time.monotonic() - started_at) * 1000)

