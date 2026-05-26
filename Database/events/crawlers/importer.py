from django.utils import timezone
from events.models import Activity, SourceWebsite


def import_activities_from_crawler(crawler, source_name=None):
    """
    Accept a crawler instance, call crawl(), and import returned events (list of dict).
    Returns: {'created': n, 'skipped': m}
    """
    created = 0
    skipped = 0
    items = []
    try:
        items = crawler.crawl()
    except Exception:
        return {'created': 0, 'skipped': 0}

    for itm in items:
        src_url = itm.get('source_url') or itm.get('url')
        if not src_url:
            skipped += 1
            continue
        if Activity.objects.filter(source_url=src_url).exists():
            skipped += 1
            continue
        # find SourceWebsite by name if provided
        sw = None
        if source_name:
            sw = SourceWebsite.objects.filter(name__icontains=source_name).first()
        # heuristics for new fields
        item_type = itm.get('item_type') or 'activity'
        is_activity = itm.get('is_activity') if ('is_activity' in itm) else (item_type == 'activity')
        is_public_item = itm.get('is_public_item', True)
        line_ready = itm.get('line_ready') if ('line_ready' in itm) else bool(itm.get('image_url') and itm.get('start_date'))
        raw = itm.get('raw_content', '')
        ai_ready = itm.get('ai_ready') if ('ai_ready' in itm) else (bool(raw and len(raw) > 50))
        recommendation_ready = itm.get('recommendation_ready', False)
        official_detail_url = itm.get('official_detail_url') or src_url
        source_key = itm.get('source_key') or (source_name or '')

        # fee_type heuristic
        fee_type = itm.get('fee_type')
        if not fee_type:
            is_free = itm.get('is_free')
            if is_free is True:
                fee_type = 'free'
            elif is_free is False:
                fee_type = 'paid'
            else:
                fd = (itm.get('fee_description') or '')
                fee_type = 'free' if '免費' in fd else 'unknown'

        # quality heuristic
        quality_score = itm.get('quality_score')
        if quality_score is None:
            # simple scoring: missing start_date or description lowers quality
            if not itm.get('start_date') or not itm.get('description'):
                quality_level = itm.get('quality_level') or 'low'
            else:
                quality_level = itm.get('quality_level') or 'medium'
        else:
            # derive level from score
            try:
                s = float(quality_score)
                if s >= 85:
                    quality_level = 'high'
                elif s >= 60:
                    quality_level = 'medium'
                else:
                    quality_level = 'low'
            except Exception:
                quality_level = itm.get('quality_level') or 'medium'

        quality_warnings = itm.get('quality_warnings','')
        exclude_from_recommendation_reason = itm.get('exclude_from_recommendation_reason','')

        act = Activity.objects.create(
            title=itm.get('title') or '活動',
            description=itm.get('description',''),
            raw_content=raw,
            source_agency=itm.get('source_agency',''),
            source_url=src_url,
            source_website=sw,
            location=itm.get('location',''),
            district=itm.get('district',''),
            start_date=itm.get('start_date'),
            end_date=itm.get('end_date'),
            image_url=itm.get('image_url',''),
            fee_description=itm.get('fee_description',''),
            registration_info=itm.get('registration_info',''),
            status='draft',
            # new fields
            item_type=item_type,
            is_activity=is_activity,
            is_public_item=is_public_item,
            line_ready=line_ready,
            ai_ready=ai_ready,
            recommendation_ready=recommendation_ready,
            official_detail_url=official_detail_url,
            source_key=source_key,
            fee_type=fee_type,
            quality_score=quality_score,
            quality_level=quality_level,
            quality_warnings=quality_warnings,
            exclude_from_recommendation_reason=exclude_from_recommendation_reason,
        )
        created += 1
    return {'created': created, 'skipped': skipped}
