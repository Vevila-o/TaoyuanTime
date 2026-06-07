from django.core.management.base import BaseCommand
from django.utils import timezone

from events.models import Activity


class Command(BaseCommand):
    help = "Dry-run-first archive for active activities whose end_date has passed."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Actually set matched activities to inactive.")
        parser.add_argument("--limit-preview", type=int, default=20)

    def handle(self, *args, **options):
        qs = Activity.objects.filter(status="active", end_date__lt=timezone.now()).order_by("end_date", "id")
        self.stdout.write(f"Expired active activities={qs.count()}")
        for activity in qs[: options["limit_preview"]]:
            self.stdout.write(f"  activity id={activity.id} end={activity.end_date:%Y-%m-%d} title={activity.title}")

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("DRY RUN only. Re-run with --apply to set these activities inactive."))
            return

        count = qs.update(status="inactive")
        self.stdout.write(self.style.SUCCESS(f"Archived expired activities={count}"))
