from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase
from django.utils import timezone

from admin_app.diagnostics import recompute_activity_readiness
from events.models import Activity
from events.services import backfill_missing_fields


class BackfillReadinessTests(TestCase):
    def test_backfills_roc_dates_and_location_from_raw_html_then_persists(self):
        with TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "activity.html"
            html_path.write_text(
                """
                <html><body>
                <p>活動地點：桃園市大溪區壹號館 展覽期間起：114-05-17 展覽期間訖：115-12-01</p>
                </body></html>
                """,
                encoding="utf-8",
            )
            activity = Activity.objects.create(
                title="大溪展覽",
                description="活動內容",
                status="active",
                source_url="https://example.com/activity",
                official_detail_url="https://example.com/activity",
                raw_html_path=str(html_path),
                is_activity=True,
                line_ready=False,
                ai_ready=False,
                recommendation_ready=False,
            )

            self.assertTrue(backfill_missing_fields(activity))
            recompute_activity_readiness(activity, save=True)
            activity.refresh_from_db()

            self.assertEqual(timezone.localtime(activity.start_date).date().isoformat(), "2025-05-17")
            self.assertEqual(timezone.localtime(activity.end_date).date().isoformat(), "2026-12-01")
            self.assertEqual(activity.location, "桃園市大溪區壹號館")
            self.assertEqual(activity.district, "大溪區")
            self.assertTrue(activity.line_ready)
            self.assertTrue(activity.ai_ready)
            self.assertTrue(activity.recommendation_ready)
