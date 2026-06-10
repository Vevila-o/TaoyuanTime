from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from events.models import (
    AIProcessingLog,
    Activity,
    ActivityChangeLog,
    ActivitySearchProfile,
    ActivityTagSuggestion,
    AdminAuditLog,
    PushDeliveryLog,
    Subscription,
)


class Command(BaseCommand):
    help = "Delete crawler/imported activity data while preserving users, tags, stores, and citizen-card data."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", action="store_true", help="Required to actually delete activity data.")
        parser.add_argument("--dry-run", action="store_true", help="Show counts without deleting anything.")

    def handle(self, *args, **options):
        if not options["confirm"] and not options["dry_run"]:
            raise CommandError("Use --dry-run to preview or --confirm to delete activity data.")

        counts = {
            "activities": Activity.objects.count(),
            "subscriptions": Subscription.objects.count(),
            "push_delivery_logs_with_activity": PushDeliveryLog.objects.exclude(activity__isnull=True).count(),
            "admin_audit_logs_with_activity": AdminAuditLog.objects.exclude(activity__isnull=True).count(),
            "activity_change_logs": ActivityChangeLog.objects.count(),
            "activity_search_profiles": ActivitySearchProfile.objects.count(),
            "activity_tag_suggestions": ActivityTagSuggestion.objects.count(),
            "ai_processing_logs": AIProcessingLog.objects.count(),
        }

        for label, count in counts.items():
            self.stdout.write(f"{label}: {count}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("DRY RUN: no data deleted."))
            return

        with transaction.atomic():
            PushDeliveryLog.objects.exclude(activity__isnull=True).delete()
            AdminAuditLog.objects.exclude(activity__isnull=True).delete()
            AIProcessingLog.objects.all().delete()
            Activity.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("Activity data reset complete. UserProfile, Tag, Store, and citizen-card data were preserved."))
