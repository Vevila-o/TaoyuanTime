from django.core.management.base import BaseCommand
from django.db.models import Q

from events.models import Activity, UserProfile


class Command(BaseCommand):
    help = "Dry-run-first cleanup for seed/sample activities and local test LINE users."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Actually delete matched seed/test records.")
        parser.add_argument("--limit-preview", type=int, default=20)

    def handle(self, *args, **options):
        activity_qs = seed_activity_queryset()
        user_qs = test_user_queryset()

        self.stdout.write(f"Seed/sample activities={activity_qs.count()}")
        for activity in activity_qs.order_by("id")[: options["limit_preview"]]:
            self.stdout.write(f"  activity id={activity.id} title={activity.title}")

        self.stdout.write(f"Test LINE users={user_qs.count()}")
        for user in user_qs.order_by("id")[: options["limit_preview"]]:
            self.stdout.write(f"  user id={user.id} line_user_id={user.line_user_id}")

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("DRY RUN only. Re-run with --apply to delete these records."))
            return

        activity_count = activity_qs.count()
        user_count = user_qs.count()
        activity_qs.delete()
        user_qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted seed/sample activities={activity_count}, test users={user_count}"))


def seed_activity_queryset():
    return Activity.objects.filter(
        Q(title__startswith="測試非活動")
        | Q(source_url__contains="/sample/")
        | Q(official_detail_url__contains="/sample/")
        | (Q(image_url__icontains="placehold.co") & Q(source_url="") & Q(official_detail_url=""))
    )


def test_user_queryset():
    return UserProfile.objects.filter(
        Q(line_user_id__startswith="codex")
        | Q(line_user_id__startswith="line-test")
        | Q(line_user_id__startswith="U_sample")
        | Q(line_user_id="debug-user")
    )
