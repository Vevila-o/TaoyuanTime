from django.db import transaction
from django.utils import timezone

from events.management.commands.import_crawler_json import (
    activity_values,
    existing_tag_map,
    get_source_website,
    infer_tags,
    sync_activity_asset,
)
from events.models import Activity, ImportRun


def find_existing_activity(values):
    source_key = values.get('source_key') or ''
    source_item_id = values.get('source_item_id') or ''
    if source_key and source_item_id:
        activity = Activity.objects.filter(source_key=source_key, source_item_id=source_item_id).first()
        if activity:
            return activity

    official_url = values.get('official_detail_url') or ''
    if official_url:
        activity = Activity.objects.filter(official_detail_url=official_url).first()
        if activity:
            return activity

    source_url = values.get('source_url') or ''
    if source_url:
        return Activity.objects.filter(source_url=source_url).first()
    return None


def upsert_activity_from_crawler_item(item, *, activate=False, tag_map=None):
    source_url = item.get('source_url') or item.get('official_detail_url')
    if not source_url and not item.get('source_item_id'):
        return None, 'skipped'

    source = get_source_website(item)
    values = activity_values(item, source)
    values['source_item_id'] = item.get('source_item_id') or item.get('id') or ''
    if activate:
        values['status'] = 'active'

    activity = find_existing_activity(values)
    if activity:
        for field, value in values.items():
            setattr(activity, field, value)
        activity.save()
        result = 'updated'
    else:
        activity = Activity.objects.create(**values)
        result = 'created'

    tags = infer_tags(item, tag_map or existing_tag_map())
    activity.tags.set(tags)
    sync_activity_asset(activity, item)
    return activity, result


def import_activities_from_crawler(crawler, *, source_name='', activate=False):
    started_at = timezone.now()
    run = ImportRun.objects.create(
        run_type='crawler',
        source=source_name or crawler.__class__.__name__,
        status='running',
        started_at=started_at,
    )
    counts = {'created': 0, 'updated': 0, 'skipped': 0, 'failed': 0}
    try:
        items = crawler.crawl()
        tag_map = existing_tag_map()
        with transaction.atomic():
            for item in items:
                if source_name and not item.get('source_key'):
                    item['source_key'] = source_name
                try:
                    _, result = upsert_activity_from_crawler_item(item, activate=activate, tag_map=tag_map)
                    counts[result] += 1
                except Exception:
                    counts['failed'] += 1
        run.status = 'success' if counts['failed'] == 0 else 'partial'
    except Exception as exc:
        run.status = 'failed'
        run.error_summary = str(exc)
    finally:
        run.created_count = counts['created']
        run.updated_count = counts['updated']
        run.skipped_count = counts['skipped']
        run.failed_count = counts['failed']
        run.finished_at = timezone.now()
        run.save()
    return counts
