import json
from datetime import datetime, time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from events.models import Activity, SourceWebsite, Tag


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

    if as_bool(item.get("requires_registration"), False) or item.get("registration_method") or item.get("registration_url"):
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


def activity_values(item, source):
    source_url = item.get("source_url") or item.get("official_detail_url")
    official_url = item.get("official_detail_url") or source_url
    description = item.get("clean_description") or item.get("description") or ""
    raw_content = item.get("raw_content") or description
    fee_text = item.get("fee_text") or item.get("fee_description") or ""

    return {
        "title": item.get("title") or "活動",
        "description": description,
        "raw_content": raw_content,
        "source_agency": item.get("source_name") or item.get("source_agency") or "",
        "source_website": source,
        "source_url": source_url,
        "location": item.get("location") or item.get("location_text") or "",
        "district": item.get("district") or "",
        "start_date": parse_event_datetime(item.get("start_date") or item.get("date_start")),
        "end_date": parse_event_datetime(item.get("end_date") or item.get("date_end"), end_of_day=True),
        "image_url": item.get("image_url") or item.get("poster_url") or "",
        "is_free": as_bool(item.get("is_free"), item.get("fee_type") in {"free", "ticket_free"}),
        "requires_registration": as_bool(item.get("requires_registration"), bool(item.get("registration_method") or item.get("registration_url"))),
        "fee_description": fee_text,
        "registration_info": item.get("registration_info") or item.get("registration_method") or item.get("registration_url") or "",
        "status": item.get("status") or "draft",
        "item_type": item.get("item_type") or item.get("content_type") or "activity",
        "is_activity": as_bool(item.get("is_activity"), (item.get("item_type") or item.get("content_type") or "activity") == "activity"),
        "is_public_item": as_bool(item.get("is_public_item"), True),
        "line_ready": as_bool(item.get("line_ready"), as_bool(item.get("line_card_ready"), False)),
        "ai_ready": as_bool(item.get("ai_ready"), False),
        "recommendation_ready": as_bool(item.get("recommendation_ready"), False),
        "official_detail_url": official_url,
        "source_key": item.get("source_key") or "",
        "fee_type": item.get("fee_type") or "unknown",
        "quality_score": item.get("quality_score"),
        "quality_level": normalize_quality_level(item),
        "quality_warnings": as_text(item.get("quality_warnings")),
        "exclude_from_recommendation_reason": as_text(item.get("exclude_from_recommendation_reason")),
    }


class Command(BaseCommand):
    help = "Import normalized crawler JSON into events.Activity."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            default="../data/output/activities_public.json",
            help="Path to activities_public.json or activities_recommendation_ready.json.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate input without writing to the database.",
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

        with transaction.atomic():
            for item in items:
                source_url = item.get("source_url") or item.get("official_detail_url")
                if not source_url:
                    skipped += 1
                    continue

                source = get_source_website(item)
                values = activity_values(item, source)
                tags = infer_tags(item, tag_map)

                activity = Activity.objects.filter(source_url=source_url).first()
                if activity:
                    for field, value in values.items():
                        setattr(activity, field, value)
                    activity.save()
                    updated += 1
                else:
                    activity = Activity.objects.create(**values)
                    created += 1
                activity.tags.set(tags)

            if options["dry_run"]:
                transaction.set_rollback(True)

        mode = "DRY RUN" if options["dry_run"] else "IMPORTED"
        self.stdout.write(self.style.SUCCESS(
            f"{mode}: total={len(items)}, created={created}, updated={updated}, skipped={skipped}"
        ))
