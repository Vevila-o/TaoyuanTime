import json
import re
from datetime import datetime, time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from events.models import Activity, ActivityAsset, ActivityChangeLog, ImportRun, SourceWebsite, Tag
from events.services import infer_taoyuan_district_from_text, normalize_taoyuan_district
from pipeline.extract_fee import extract_registration_url


QUALITY_LEVEL_BY_SCORE = (
    (85, "high"),
    (60, "medium"),
    (0, "low"),
)


def parse_event_datetime(value, *, end_of_day=False):
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        dt = parse_datetime(text)
        if dt is None:
            parsed_date = parse_date(text)
            if parsed_date is None:
                return None
            dt = datetime.combine(parsed_date, time.max if end_of_day else time.min)
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


ROC_DATE_PATTERN = re.compile(r"(?P<year>1\d{2})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})")


def parse_roc_date(value, *, end_of_day=False):
    if not value:
        return None
    match = ROC_DATE_PATTERN.search(str(value))
    if not match:
        return None
    year = int(match.group("year")) + 1911
    month = int(match.group("month"))
    day = int(match.group("day"))
    dt = datetime.combine(datetime(year, month, day).date(), time.max if end_of_day else time.min)
    return timezone.make_aware(dt, timezone.get_current_timezone())


def infer_roc_datetimes_from_text(*texts):
    text = " ".join(str(item or "") for item in texts if item)
    start = None
    end = None
    start_match = re.search(r"(?:展覽期間起|活動期間起|期間起|起)[:：\s]*((?:1\d{2})[/-]\d{1,2}[/-]\d{1,2})", text)
    end_match = re.search(r"(?:展覽期間訖|活動期間訖|期間訖|訖|至)[:：\s]*((?:1\d{2})[/-]\d{1,2}[/-]\d{1,2})", text)
    range_match = re.search(r"((?:1\d{2})[/-]\d{1,2}[/-]\d{1,2})\s*[~～至]\s*((?:1\d{2})[/-]\d{1,2}[/-]\d{1,2})", text)
    if start_match:
        start = parse_roc_date(start_match.group(1))
    if end_match:
        end = parse_roc_date(end_match.group(1), end_of_day=True)
    if range_match:
        start = start or parse_roc_date(range_match.group(1))
        end = end or parse_roc_date(range_match.group(2), end_of_day=True)
    return start, end


def as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return default


def as_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def normalized_registration(item, source_text):
    registration_url, evidence = extract_registration_url(source_text, item.get("registration_url"))
    if evidence:
        return {
            "method": "online",
            "url": registration_url or item.get("registration_url") or "",
            "info": item.get("registration_info") or evidence,
            "requires_registration": True,
        }
    return {
        "method": "unknown",
        "url": "",
        "info": item.get("registration_info") if item.get("registration_parse_status") == "success" else "",
        "requires_registration": False,
    }


def normalize_quality_level(item):
    level = item.get("quality_level")
    if level in {"high", "medium", "low", "rejected"}:
        return level
    score = item.get("quality_score")
    if score is not None:
        try:
            numeric_score = float(score)
        except (TypeError, ValueError):
            numeric_score = None
        if numeric_score is not None:
            for threshold, mapped_level in QUALITY_LEVEL_BY_SCORE:
                if numeric_score >= threshold:
                    return mapped_level
    if level in {"usable", "ready"}:
        return "high"
    return "medium"


def get_source_website(item):
    name = item.get("source_name") or item.get("source_agency") or item.get("source_key") or "unknown"
    source_url = item.get("source_url") or item.get("official_detail_url") or ""
    source, _ = SourceWebsite.objects.get_or_create(
        name=name,
        defaults={
            "url": source_url[:200],
            "source_type": "other",
            "is_active": True,
        },
    )
    return source


def existing_tag_map():
    tags = Tag.objects.filter(is_active=True)
    return {(tag.tag_type, tag.name): tag for tag in tags}


def district_tag_name(district):
    if not district:
        return ""
    return str(district).replace("區", "").strip()


def infer_tags(item, tag_map):
    tags = []

    explicit_tags = item.get("tags") or []
    if isinstance(explicit_tags, str):
        explicit_tags = [explicit_tags]
    for name in explicit_tags:
        for tag_type in ("region", "activity_type", "audience", "cost", "discount", "time"):
            tag = tag_map.get((tag_type, str(name).strip()))
            if tag and tag not in tags:
                tags.append(tag)

    region_name = district_tag_name(item.get("district"))
    region_tag = tag_map.get(("region", region_name))
    if region_tag and region_tag not in tags:
        tags.append(region_tag)

    registration_text = " ".join([
        str(item.get("registration_info") or ""),
        str(item.get("clean_description") or ""),
        str(item.get("description") or ""),
        str(item.get("raw_content") or ""),
    ])
    _, registration_evidence = extract_registration_url(registration_text, item.get("registration_url"))
    if registration_evidence:
        registration_tag = tag_map.get(("cost", "需報名"))
        if registration_tag and registration_tag not in tags:
            tags.append(registration_tag)

    fee_type = item.get("fee_type")
    is_free = item.get("is_free")
    if fee_type in {"free", "ticket_free"} or is_free is True:
        cost_name = "免費"
    elif fee_type == "paid" or is_free is False:
        cost_name = "付費"
    else:
        cost_name = "金額未提供"
    cost_tag = tag_map.get(("cost", cost_name))
    if cost_tag and cost_tag not in tags:
        tags.append(cost_tag)

    text = f"{item.get('title') or ''} {item.get('description') or ''} {item.get('clean_description') or ''}"
    for (tag_type, name), tag in tag_map.items():
        if tag_type == "activity_type" and name in text and tag not in tags:
            tags.append(tag)
    return tags


def sync_activity_asset(activity, item):
    image_url = item.get("image_url") or item.get("poster_url") or item.get("ocr_image_url") or ""
    if not image_url:
        return
    ActivityAsset.objects.update_or_create(
        activity=activity,
        url=image_url,
        defaults={
            "asset_type": "poster",
            "is_primary": True,
            "ocr_eligible": bool(item.get("ocr_ready") or item.get("ocr_image_url")),
            "quality_warning": as_text(item.get("asset_warning") or ""),
        },
    )


def activity_values(item, source):
    source_url = item.get("source_url") or item.get("official_detail_url")
    official_url = item.get("official_detail_url") or source_url
    description = item.get("clean_description") or item.get("description") or ""
    raw_content = item.get("raw_content") or description
    fee_text = item.get("fee_text") or item.get("fee_description") or ""
    registration = normalized_registration(
        item,
        " ".join([
            str(item.get("registration_info") or ""),
            str(item.get("clean_description") or ""),
            str(item.get("description") or ""),
            str(item.get("raw_content") or ""),
        ]),
    )

    district = normalize_taoyuan_district(item.get("district"))
    if not district:
        district = infer_taoyuan_district_from_text(
            item.get("location") or item.get("location_text") or "",
            item.get("title") or "",
            item.get("description") or "",
            item.get("clean_description") or "",
            item.get("raw_content") or "",
            item.get("official_detail_url") or "",
            item.get("source_url") or "",
            raw_html_path=item.get("raw_html_path") or "",
        )

    start_dt = parse_event_datetime(item.get("start_date") or item.get("date_start"))
    end_dt = parse_event_datetime(item.get("end_date") or item.get("date_end"), end_of_day=True)
    if not start_dt or not end_dt:
        inferred_start, inferred_end = infer_roc_datetimes_from_text(
            item.get("title") or "",
            item.get("location") or item.get("location_text") or "",
            item.get("description") or "",
            item.get("clean_description") or "",
            item.get("raw_content") or "",
        )
        start_dt = start_dt or inferred_start
        end_dt = end_dt or inferred_end

    return {
        "title": item.get("title") or "活動",
        "description": description,
        "raw_content": raw_content,
        "source_agency": item.get("source_name") or item.get("source_agency") or "",
        "source_website": source,
        "source_url": source_url,
        "location": item.get("location") or item.get("location_text") or "",
        "district": district,
        "start_date": start_dt,
        "end_date": end_dt,
        "image_url": item.get("image_url") or item.get("poster_url") or "",
        "is_free": as_bool(item.get("is_free"), item.get("fee_type") in {"free", "ticket_free"}),
        "requires_registration": registration["requires_registration"],
        "fee_description": fee_text,
        "registration_info": registration["info"],
        "registration_url": registration["url"],
        "status": item.get("status") or "draft",
        "item_type": item.get("item_type") or item.get("content_type") or "activity",
        "is_activity": as_bool(item.get("is_activity"), (item.get("item_type") or item.get("content_type") or "activity") == "activity"),
        "is_public_item": as_bool(item.get("is_public_item"), True),
        "line_ready": as_bool(item.get("line_ready"), as_bool(item.get("line_card_ready"), False)),
        "ai_ready": as_bool(item.get("ai_ready"), False),
        "recommendation_ready": as_bool(item.get("recommendation_ready"), False),
        "official_detail_url": official_url,
        "source_key": item.get("source_key") or "",
        "source_item_id": item.get("source_item_id") or item.get("id") or "",
        "ocr_ready": as_bool(item.get("ocr_ready"), False),
        "ocr_image_url": item.get("ocr_image_url") or "",
        "ocr_image_path": item.get("ocr_image_path") or "",
        "ocr_text": item.get("ocr_text") or "",
        "ocr_summary": item.get("ocr_summary") or "",
        "ocr_confidence": item.get("ocr_confidence"),
        "ocr_status": item.get("ocr_status") or "",
        "ocr_warnings": as_text(item.get("ocr_warnings")),
        "fee_type": item.get("fee_type") or "unknown",
        "quality_score": item.get("quality_score"),
        "quality_level": normalize_quality_level(item),
        "quality_warnings": as_text(item.get("quality_warnings")),
        "exclude_from_recommendation_reason": as_text(item.get("exclude_from_recommendation_reason")),
        "content_hash": item.get("content_hash") or "",
        "raw_html_path": item.get("raw_html_path") or "",
        "last_seen_at": timezone.now(),
        "organizer": item.get("organizer") or item.get("source_name") or "",
    }


IMPORTANT_CHANGE_FIELDS = {"title", "start_date", "end_date", "location", "registration_url", "status"}


def apply_manual_overrides(activity, values):
    if not activity or not activity.manual_verified:
        return values
    overrides = activity.manual_overrides or []
    if isinstance(overrides, str):
        overrides = [name.strip() for name in overrides.split(",") if name.strip()]
    protected = set(overrides)
    return {field: value for field, value in values.items() if field not in protected}


def record_activity_changes(activity, values, source):
    for field in IMPORTANT_CHANGE_FIELDS:
        if field not in values:
            continue
        old_value = getattr(activity, field, None)
        new_value = values[field]
        if str(old_value or "") == str(new_value or ""):
            continue
        ActivityChangeLog.objects.create(
            activity=activity,
            field_name=field,
            old_value=str(old_value or ""),
            new_value=str(new_value or ""),
            source=source or activity.source_key or "crawler_import",
            notify_required=True,
            metadata={"reason": "crawler_import_important_field_changed"},
        )


class Command(BaseCommand):
    help = "Import normalized crawler JSON into events.Activity."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            default="scraping/data/output/activities_public.json",
            help="Path to activities_public.json or activities_recommendation_ready.json.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate input without writing to the database.",
        )
        parser.add_argument(
            "--activate",
            action="store_true",
            help="Import activities as active so they are immediately available to LINE.",
        )

    def handle(self, *args, **options):
        input_path = Path(options["input"])
        if not input_path.is_absolute():
            input_path = Path.cwd() / input_path
        if not input_path.exists():
            raise CommandError(f"Input file not found: {input_path}")

        try:
            items = json.loads(input_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON: {exc}") from exc

        if not isinstance(items, list):
            raise CommandError("Input JSON must be a list of activity objects.")

        tag_map = existing_tag_map()
        created = 0
        updated = 0
        skipped = 0
        import_run = None
        if not options["dry_run"]:
            import_run = ImportRun.objects.create(
                run_type="json_import",
                source="import_crawler_json",
                input_path=str(input_path),
                status="running",
                metadata={"activate": bool(options["activate"])},
            )

        try:
            with transaction.atomic():
                for item in items:
                    source_url = item.get("source_url") or item.get("official_detail_url")
                    if not source_url:
                        skipped += 1
                        continue

                    source = get_source_website(item)
                    values = activity_values(item, source)
                    if options["activate"]:
                        values["status"] = "active"
                    tags = infer_tags(item, tag_map)

                    activity = None
                    if values.get("source_key") and values.get("source_item_id"):
                        activity = Activity.objects.filter(
                            source_key=values["source_key"],
                            source_item_id=values["source_item_id"],
                        ).first()
                    if not activity and values.get("official_detail_url"):
                        activity = Activity.objects.filter(official_detail_url=values["official_detail_url"]).first()
                    if not activity:
                        activity = Activity.objects.filter(source_url=source_url).first()
                    if activity:
                        values = apply_manual_overrides(activity, values)
                        record_activity_changes(activity, values, values.get("source_key") or "import_crawler_json")
                        for field, value in values.items():
                            setattr(activity, field, value)
                        activity.save()
                        updated += 1
                    else:
                        activity = Activity.objects.create(**values)
                        created += 1
                    activity.tags.set(tags)
                    sync_activity_asset(activity, item)

                if options["dry_run"]:
                    transaction.set_rollback(True)
        except Exception as exc:
            if import_run:
                import_run.status = "failed"
                import_run.error_summary = str(exc)
                import_run.finished_at = timezone.now()
                import_run.save(update_fields=["status", "error_summary", "finished_at"])
            raise

        if import_run:
            import_run.created_count = created
            import_run.updated_count = updated
            import_run.skipped_count = skipped
            import_run.status = "success"
            import_run.finished_at = timezone.now()
            import_run.save(update_fields=[
                "created_count",
                "updated_count",
                "skipped_count",
                "status",
                "finished_at",
            ])

        mode = "DRY RUN" if options["dry_run"] else "IMPORTED"
        self.stdout.write(self.style.SUCCESS(
            f"{mode}: total={len(items)}, created={created}, updated={updated}, skipped={skipped}"
        ))
