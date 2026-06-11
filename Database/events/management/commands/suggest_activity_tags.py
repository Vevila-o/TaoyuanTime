from django.core.management.base import BaseCommand

from events.models import Activity, ActivityTagSuggestion, Tag


class Command(BaseCommand):
    help = 'Create pending ActivityTagSuggestion rows from existing Tag keywords.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=200)
        parser.add_argument('--min-confidence', type=float, default=0.65)

    def handle(self, *args, **options):
        tags = list(Tag.objects.filter(is_active=True))
        activities = Activity.objects.filter(excluded_from_public=False, is_activity=True).order_by('-updated_at')[:options['limit']]
        created = 0
        skipped = 0
        for activity in activities:
            text = f'{activity.title} {activity.description} {activity.ai_summary} {activity.raw_content}'
            current_tag_ids = set(activity.tags.values_list('id', flat=True))
            for tag in tags:
                if tag.id in current_tag_ids:
                    skipped += 1
                    continue
                if not tag.name or tag.name not in text:
                    continue
                _, was_created = ActivityTagSuggestion.objects.get_or_create(
                    activity=activity,
                    tag_name=tag.name,
                    tag_type=tag.tag_type,
                    source='rule',
                    defaults={
                        'tag': tag,
                        'confidence': options['min_confidence'],
                        'reason': f'活動文字包含既有 Tag「{tag.name}」。',
                        'status': 'pending',
                    },
                )
                if was_created:
                    created += 1
                else:
                    skipped += 1
        self.stdout.write(self.style.SUCCESS(f'Done. created={created}, skipped={skipped}'))
