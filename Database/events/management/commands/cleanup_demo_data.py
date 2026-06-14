from django.core.management.base import BaseCommand

from events.models import Activity, UserProfile


class Command(BaseCommand):
    help = "Dry-run-first cleanup for deterministic demo records."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Actually delete matched demo records.")
        parser.add_argument("--limit-preview", type=int, default=20)

    def handle(self, *args, **options):
        activity_qs = demo_activity_queryset()
        user_qs = demo_user_queryset()

        self.stdout.write(f"Demo activities={activity_qs.count()}")
        for activity in activity_qs.order_by("id")[: options["limit_preview"]]:
            self.stdout.write(f"  activity id={activity.id} source_item_id={activity.source_item_id} title={activity.title}")

        self.stdout.write(f"Demo LINE users={user_qs.count()}")
        for user in user_qs.order_by("id")[: options["limit_preview"]]:
            self.stdout.write(f"  user id={user.id} line_user_id={user.line_user_id}")

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("DRY RUN only. Re-run with --apply to delete these records."))
            return

        activity_count = activity_qs.count()
        user_count = user_qs.count()
        activity_qs.delete()
        user_qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted demo data: activities={activity_count}, users={user_count}"))


def demo_activity_queryset():
    return Activity.objects.filter(source_key="demo")


def demo_user_queryset():
    return UserProfile.objects.filter(line_user_id__startswith="demo-")
