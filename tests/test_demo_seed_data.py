from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from events.models import (
    Activity,
    ActivitySearchProfile,
    ActivityTagSuggestion,
    Subscription,
    UserProfile,
)


class DemoSeedDataCommandTests(TestCase):
    def test_seed_demo_data_reset_creates_reproducible_demo_records(self):
        out = StringIO()

        call_command("seed_demo_data", "--reset", stdout=out)

        demo_activities = Activity.objects.filter(source_key="demo")
        self.assertGreaterEqual(demo_activities.count(), 7)
        self.assertIn("Seeded demo data", out.getvalue())

        normal = Activity.objects.get(source_item_id="demo-normal")
        self.assertTrue(normal.line_ready)
        self.assertTrue(normal.recommendation_ready)
        self.assertTrue(normal.ai_summary)
        self.assertEqual(normal.search_profile.status, "success")

        manual = Activity.objects.get(source_item_id="demo-manual-review")
        self.assertFalse(manual.line_ready)
        self.assertFalse(manual.recommendation_ready)
        self.assertEqual(manual.final_state, "needs_review")
        self.assertEqual(manual.exclude_from_recommendation_reason, "manual_review_required")

        summary_gap = Activity.objects.get(source_item_id="demo-summary-gap")
        self.assertTrue(summary_gap.line_ready)
        self.assertTrue(summary_gap.recommendation_ready)
        self.assertEqual(summary_gap.ai_summary, "")

        self.assertEqual(Activity.objects.get(source_item_id="demo-link-error").official_link_status, "error")
        dead_link = Activity.objects.get(source_item_id="demo-link-dead")
        self.assertEqual(dead_link.official_link_status, "dead")
        self.assertTrue(dead_link.excluded_from_public)

        expired = Activity.objects.get(source_item_id="demo-expired")
        self.assertEqual(expired.status, "inactive")
        self.assertEqual(expired.final_state, "expired")

        self.assertTrue(ActivityTagSuggestion.objects.filter(activity__source_key="demo", status="pending").exists())
        self.assertTrue(UserProfile.objects.filter(line_user_id="demo-line-user").exists())
        self.assertTrue(Subscription.objects.filter(user__line_user_id="demo-line-user").exists())
        self.assertTrue(ActivitySearchProfile.objects.filter(activity__source_key="demo", status="success").exists())

    def test_cleanup_demo_data_is_dry_run_first_and_apply_deletes_demo_records(self):
        call_command("seed_demo_data", "--reset", stdout=StringIO())
        dry_run = StringIO()

        call_command("cleanup_demo_data", stdout=dry_run)

        self.assertIn("DRY RUN", dry_run.getvalue())
        self.assertTrue(Activity.objects.filter(source_key="demo").exists())
        self.assertTrue(UserProfile.objects.filter(line_user_id="demo-line-user").exists())

        apply_out = StringIO()
        call_command("cleanup_demo_data", "--apply", stdout=apply_out)

        self.assertIn("Deleted demo data", apply_out.getvalue())
        self.assertFalse(Activity.objects.filter(source_key="demo").exists())
        self.assertFalse(UserProfile.objects.filter(line_user_id__startswith="demo-").exists())
