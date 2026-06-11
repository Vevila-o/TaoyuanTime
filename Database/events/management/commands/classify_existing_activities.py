from collections import Counter

from django.core.management.base import BaseCommand

from events.models import Activity
from pipeline.public_exclusion import apply_public_exclusion, final_state_for_event


class Command(BaseCommand):
    help = "Classify existing Activity rows and mark non-activities as excluded from public surfaces."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Persist changes. Without this, only reports counts.")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        limit = int(options.get("limit") or 0)
        qs = Activity.objects.order_by("id")
        if limit:
            qs = qs[:limit]

        checked = 0
        changed = 0
        reasons = Counter()
        examples = []

        for activity in qs:
            checked += 1
            event = {
                "title": activity.title,
                "clean_description": activity.description,
                "description": activity.description,
                "raw_content": activity.raw_content,
                "item_type": activity.item_type,
                "content_type": activity.item_type,
                "is_activity": activity.is_activity,
                "excluded_from_public": activity.excluded_from_public,
                "exclude_reason": activity.exclude_reason,
                "status": activity.status,
                "line_ready": activity.line_ready,
                "ai_ready": activity.ai_ready,
                "recommendation_ready": activity.recommendation_ready,
                "quality_warnings": [],
            }
            apply_public_exclusion(event)
            if not event.get("excluded_from_public"):
                continue

            reasons[event.get("exclude_reason") or "excluded_from_public"] += 1
            if not activity.excluded_from_public:
                changed += 1
                if len(examples) < 10:
                    examples.append(f"#{activity.id} {activity.title[:80]} ({event.get('exclude_reason')})")
                if apply_changes:
                    activity.item_type = event.get("item_type") or activity.item_type
                    activity.is_activity = False
                    activity.is_public_item = False
                    activity.line_ready = False
                    activity.ai_ready = False
                    activity.recommendation_ready = False
                    activity.excluded_from_public = True
                    activity.exclude_reason = event.get("exclude_reason") or "excluded_from_public"
                    activity.final_state = final_state_for_event(event)
                    activity.save(update_fields=[
                        "item_type",
                        "is_activity",
                        "is_public_item",
                        "line_ready",
                        "ai_ready",
                        "recommendation_ready",
                        "excluded_from_public",
                        "exclude_reason",
                        "final_state",
                        "updated_at",
                    ])

        mode = "APPLIED" if apply_changes else "DRY RUN"
        self.stdout.write(self.style.SUCCESS(f"{mode}: checked={checked}, newly_excluded={changed}"))
        if reasons:
            self.stdout.write("Reasons:")
            for reason, count in reasons.most_common():
                self.stdout.write(f"- {reason}: {count}")
        if examples:
            self.stdout.write("Examples:")
            for item in examples:
                self.stdout.write(f"- {item}")
