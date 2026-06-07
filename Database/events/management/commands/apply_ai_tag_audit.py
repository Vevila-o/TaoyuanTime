import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from events.models import Activity, Tag


def active_tag_map():
    return {(tag.tag_type, tag.name): tag for tag in Tag.objects.filter(is_active=True)}


def find_activity(item):
    source_url = item.get("activity_id") or ""
    if not source_url:
        return None
    return Activity.objects.filter(
        Q(source_url=source_url) | Q(official_detail_url=source_url)
    ).first()


class Command(BaseCommand):
    help = "Apply accepted tags from ai_tag_quality_report.json to matching activities."

    def add_arguments(self, parser):
        parser.add_argument(
            "--audit",
            default="scraping/data/output/ai_tag_quality_report.json",
            help="Path to ai_tag_quality_report.json.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report without writing Activity.tags.",
        )

    def handle(self, *args, **options):
        audit_path = Path(options["audit"])
        if not audit_path.is_absolute():
            audit_path = Path.cwd() / audit_path
        if not audit_path.exists():
            raise CommandError(f"Audit file not found: {audit_path}")

        try:
            payload = json.loads(audit_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON: {exc}") from exc

        items = payload.get("items") or []
        if not isinstance(items, list):
            raise CommandError("Audit JSON must contain an items list.")

        tag_map = active_tag_map()
        matched = 0
        missing_activities = 0
        applied = 0
        missing_tags = []

        with transaction.atomic():
            for item in items:
                activity = find_activity(item)
                if not activity:
                    missing_activities += 1
                    continue

                matched += 1
                tags = []
                for raw_tag in item.get("accepted_tags") or []:
                    key = (raw_tag.get("tag_type"), raw_tag.get("name"))
                    tag = tag_map.get(key)
                    if tag:
                        tags.append(tag)
                    else:
                        missing_tags.append(f"{key[0]}:{key[1]}")

                if tags:
                    activity.tags.add(*tags)
                    applied += len(tags)

            if options["dry_run"]:
                transaction.set_rollback(True)

        mode = "DRY RUN" if options["dry_run"] else "APPLIED"
        self.stdout.write(self.style.SUCCESS(
            f"{mode}: audit_items={len(items)}, matched_activities={matched}, "
            f"missing_activities={missing_activities}, tags_applied={applied}, "
            f"missing_tags={len(missing_tags)}"
        ))
        if missing_tags:
            unique_missing = sorted(set(missing_tags))
            self.stdout.write("Missing tags: " + ", ".join(unique_missing))
