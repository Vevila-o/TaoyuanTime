from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from events.models import Activity


class Command(BaseCommand):
    help = "Run safe backend-admin smoke checks for demo and local testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--host",
            default="127.0.0.1",
            help="HTTP_HOST used by Django test client.",
        )

    def handle(self, *args, **options):
        client = Client(HTTP_HOST=options["host"])
        checks = [
            ("dashboard", reverse("dashboard")),
            ("operations", reverse("operations")),
            ("operation jobs", reverse("operationJobs")),
            ("line simulator", reverse("lineQuerySimulator")),
            ("activity filters", reverse("activityList") + "?readiness=link_dead"),
            ("link error filter", reverse("activityList") + "?readiness=link_error"),
            ("tag review", reverse("tagReview")),
            ("push management", reverse("pushManagement")),
            ("users", reverse("userManagement")),
            ("crawl jobs", reverse("crawlJobs")),
            ("activity changes", reverse("activityChanges")),
        ]

        failures = []
        for label, url in checks:
            response = client.get(url)
            ok = response.status_code == 200
            marker = "PASS" if ok else "FAIL"
            self.stdout.write(f"{marker} | {label} | {url} | HTTP {response.status_code}")
            if not ok:
                failures.append((label, url, response.status_code))

        now = timezone.now()
        expired_active = Activity.objects.filter(
            status="active",
            excluded_from_public=False,
            end_date__lt=now,
        ).exclude(source_key="demo").count()
        self.stdout.write(f"{'PASS' if expired_active == 0 else 'FAIL'} | expired active | count={expired_active}")
        if expired_active:
            failures.append(("expired active", "database", expired_active))

        missing_ai_summaries = (
            Activity.objects.filter(
                status="active",
                excluded_from_public=False,
                is_activity=True,
            )
            .filter(Q(line_ready=True) | Q(recommendation_ready=True))
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=now))
            .filter(Q(ai_summary__isnull=True) | Q(ai_summary=""))
            .exclude(official_detail_url="")
            .exclude(official_detail_url__isnull=True)
            .exclude(official_link_status="dead")
            .exclude(source_key="demo")
            .count()
        )
        self.stdout.write(f"{'PASS' if missing_ai_summaries == 0 else 'FAIL'} | missing ai summaries | count={missing_ai_summaries}")
        if missing_ai_summaries:
            failures.append(("missing ai summaries", "database", missing_ai_summaries))

        if failures:
            detail = ", ".join(f"{label} {status}" for label, _, status in failures)
            raise CommandError(f"Admin backend smoke failed: {detail}")
