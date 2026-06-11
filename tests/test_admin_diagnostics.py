import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from admin_app.diagnostics import activity_exposure_diagnostic, recompute_activity_readiness
from events.models import Activity


class AdminDiagnosticsTests(TestCase):
    def test_stale_missing_date_and_location_warnings_are_hidden_when_fields_exist(self):
        activity = Activity.objects.create(
            title="大溪戶外演出",
            description="活動內容",
            status="active",
            is_activity=True,
            is_public_item=False,
            line_ready=False,
            recommendation_ready=False,
            source_url="https://example.com/activity",
            official_detail_url="https://example.com/activity",
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            district="大溪區",
            location="壹號館",
            quality_warnings=json.dumps(["missing_activity_date", "missing_location"], ensure_ascii=False),
        )

        diagnostic = activity_exposure_diagnostic(activity)

        self.assertNotIn("missing_activity_date", diagnostic["quality_warnings"])
        self.assertNotIn("missing_location", diagnostic["quality_warnings"])
        self.assertNotIn("缺活動日期", diagnostic["line"]["reasons"])
        self.assertNotIn("缺地點", diagnostic["line"]["reasons"])

    def test_recompute_clears_stale_warnings_and_updates_final_state(self):
        activity = Activity.objects.create(
            title="完整活動",
            description="活動內容",
            status="active",
            is_activity=True,
            is_public_item=False,
            line_ready=False,
            recommendation_ready=False,
            source_url="https://example.com/activity",
            official_detail_url="https://example.com/activity",
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            district="大溪區",
            location="壹號館",
            quality_warnings=json.dumps(["missing_activity_date", "missing_location"], ensure_ascii=False),
        )

        recompute_activity_readiness(activity, save=True)
        activity.refresh_from_db()

        self.assertTrue(activity.line_ready)
        self.assertTrue(activity.recommendation_ready)
        self.assertTrue(activity.is_public_item)
        self.assertEqual(activity.final_state, "published")
        self.assertNotIn("missing_activity_date", activity.quality_warnings)
        self.assertNotIn("missing_location", activity.quality_warnings)

    def test_recompute_keeps_manual_inactive_separate_from_expired(self):
        activity = Activity.objects.create(
            title="已下架活動",
            description="活動內容",
            status="inactive",
            is_activity=True,
            source_url="https://example.com/activity",
            official_detail_url="https://example.com/activity",
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            district="大溪區",
            location="壹號館",
        )

        recompute_activity_readiness(activity, save=True)
        activity.refresh_from_db()

        self.assertFalse(activity.line_ready)
        self.assertFalse(activity.recommendation_ready)
        self.assertEqual(activity.final_state, "inactive")

    def test_recompute_save_persists_backfilled_core_fields(self):
        activity = Activity.objects.create(
            title="回填活動",
            description="活動內容",
            status="active",
            is_activity=True,
            source_url="https://example.com/activity",
            official_detail_url="https://example.com/activity",
        )
        activity.start_date = timezone.now() + timedelta(days=7)
        activity.end_date = timezone.now() + timedelta(days=8)
        activity.location = "壹號館"
        activity.district = "大溪區"

        recompute_activity_readiness(activity, save=True)
        activity.refresh_from_db()

        self.assertIsNotNone(activity.start_date)
        self.assertEqual(activity.location, "壹號館")
        self.assertEqual(activity.district, "大溪區")
        self.assertTrue(activity.line_ready)
