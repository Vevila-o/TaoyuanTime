from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from events.models import Activity


class AdminBackendSmokeCommandTests(TestCase):
    def test_smoke_admin_backend_runs_safe_checks(self):
        out = StringIO()

        call_command("smoke_admin_backend", stdout=out)

        output = out.getvalue()
        self.assertIn("PASS | dashboard", output)
        self.assertIn("PASS | line simulator", output)
        self.assertIn("PASS | activity filters", output)
        self.assertIn("PASS | link error filter", output)
        self.assertIn("PASS | expired active", output)
        self.assertIn("PASS | missing ai summaries", output)

    def test_smoke_admin_backend_ignores_intentional_demo_summary_gap(self):
        Activity.objects.create(
            title="[DEMO] 摘要缺口展示",
            description="用來展示營運工具的摘要缺口。",
            status="active",
            is_activity=True,
            is_public_item=True,
            line_ready=True,
            recommendation_ready=True,
            source_key="demo",
            source_item_id="demo-summary-gap",
            source_url="https://example.com/demo/summary-gap",
            official_detail_url="https://example.com/demo/summary-gap",
            start_date=timezone.now() + timezone.timedelta(days=3),
            end_date=timezone.now() + timezone.timedelta(days=4),
            district="中壢區",
            location="中壢展演中心",
            ai_summary="",
        )
        out = StringIO()

        call_command("smoke_admin_backend", stdout=out)

        self.assertIn("PASS | missing ai summaries | count=0", out.getvalue())
