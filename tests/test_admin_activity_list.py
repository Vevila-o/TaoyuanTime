from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events.models import Activity


class AdminActivityListTests(TestCase):
    def test_activity_list_prioritizes_upcoming_effective_items_before_ongoing_old_items(self):
        ongoing = Activity.objects.create(
            title="已開始長期展覽",
            description="活動內容",
            status="active",
            is_activity=True,
            is_public_item=True,
            line_ready=True,
            recommendation_ready=True,
            excluded_from_public=False,
            source_url="https://example.com/ongoing",
            official_detail_url="https://example.com/ongoing",
            start_date=timezone.now() - timedelta(days=100),
            end_date=timezone.now() + timedelta(days=100),
            district="中壢區",
            location="中壢藝術館",
        )
        upcoming = Activity.objects.create(
            title="近期即將開始活動",
            description="活動內容",
            status="active",
            is_activity=True,
            is_public_item=True,
            line_ready=True,
            recommendation_ready=True,
            excluded_from_public=False,
            source_url="https://example.com/upcoming",
            official_detail_url="https://example.com/upcoming",
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            district="中壢區",
            location="中壢藝術館",
        )

        response = self.client.get(reverse("activityList"))
        html = response.content.decode("utf-8")

        self.assertLess(html.index(upcoming.title), html.index(ongoing.title))

    def test_activity_list_prioritizes_effective_items_over_stale_ready_flags(self):
        valid = Activity.objects.create(
            title="有效展示活動",
            description="活動內容",
            status="active",
            is_activity=True,
            is_public_item=True,
            line_ready=True,
            recommendation_ready=True,
            excluded_from_public=False,
            source_url="https://example.com/valid",
            official_detail_url="https://example.com/valid",
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            district="中壢區",
            location="中壢藝術館",
        )
        stale_missing_date = Activity.objects.create(
            title="缺日期但旗標漂移",
            description="活動內容",
            status="active",
            is_activity=True,
            is_public_item=True,
            line_ready=True,
            recommendation_ready=True,
            excluded_from_public=False,
            source_url="https://example.com/missing-date",
            official_detail_url="https://example.com/missing-date",
            district="中壢區",
            location="中壢藝術館",
        )
        manual_review = Activity.objects.create(
            title="需要人工審核活動",
            description="活動內容",
            status="active",
            is_activity=True,
            is_public_item=True,
            line_ready=True,
            recommendation_ready=True,
            excluded_from_public=False,
            source_url="https://example.com/manual-review",
            official_detail_url="https://example.com/manual-review",
            start_date=timezone.now() + timedelta(days=5),
            end_date=timezone.now() + timedelta(days=6),
            district="中壢區",
            location="中壢藝術館",
            exclude_from_recommendation_reason="manual_review_required",
        )

        response = self.client.get(reverse("activityList"))
        html = response.content.decode("utf-8")

        self.assertLess(html.index(valid.title), html.index(stale_missing_date.title))
        self.assertLess(html.index(valid.title), html.index(manual_review.title))
        stale_row = html[html.index(stale_missing_date.title):html.index(stale_missing_date.title) + 1200]
        manual_row = html[html.index(manual_review.title):html.index(manual_review.title) + 1200]
        self.assertNotIn("上架中", stale_row)
        self.assertIn("待補資料", stale_row)
        self.assertNotIn("上架中", manual_row)
        self.assertIn("待補資料", manual_row)

    def test_activity_list_can_filter_link_error_without_dead_link_items(self):
        link_error = Activity.objects.create(
            title="連結待確認活動",
            description="活動內容",
            status="active",
            is_activity=True,
            is_public_item=True,
            line_ready=True,
            recommendation_ready=True,
            excluded_from_public=False,
            source_url="https://example.com/error",
            official_detail_url="https://example.com/error",
            official_link_status="error",
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            district="中壢區",
            location="中壢藝術館",
        )
        Activity.objects.create(
            title="正常連結活動",
            description="活動內容",
            status="active",
            is_activity=True,
            is_public_item=True,
            line_ready=True,
            recommendation_ready=True,
            excluded_from_public=False,
            source_url="https://example.com/ok",
            official_detail_url="https://example.com/ok",
            official_link_status="ok",
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            district="中壢區",
            location="中壢藝術館",
        )
        Activity.objects.create(
            title="失效連結活動",
            description="活動內容",
            status="active",
            is_activity=True,
            is_public_item=False,
            line_ready=False,
            recommendation_ready=False,
            excluded_from_public=True,
            source_url="https://example.com/dead",
            official_detail_url="https://example.com/dead",
            official_link_status="dead",
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            district="中壢區",
            location="中壢藝術館",
        )

        response = self.client.get(reverse("activityList") + "?readiness=link_error")
        html = response.content.decode("utf-8")

        self.assertContains(response, link_error.title)
        self.assertIn("官方連結待確認", html)
        self.assertNotIn("正常連結活動", html)
        self.assertNotIn("失效連結活動", html)

    def test_activity_list_prioritizes_link_error_attention_rows(self):
        ok = Activity.objects.create(
            title="正常可推薦活動",
            description="活動內容",
            status="active",
            is_activity=True,
            is_public_item=True,
            line_ready=True,
            recommendation_ready=True,
            excluded_from_public=False,
            source_url="https://example.com/ok",
            official_detail_url="https://example.com/ok",
            official_link_status="ok",
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            district="中壢區",
            location="中壢藝術館",
        )
        link_error = Activity.objects.create(
            title="待確認但仍可保留活動",
            description="活動內容",
            status="active",
            is_activity=True,
            is_public_item=True,
            line_ready=True,
            recommendation_ready=True,
            excluded_from_public=False,
            source_url="https://example.com/error",
            official_detail_url="https://example.com/error",
            official_link_status="error",
            start_date=timezone.now() + timedelta(days=10),
            end_date=timezone.now() + timedelta(days=11),
            district="中壢區",
            location="中壢藝術館",
        )

        response = self.client.get(reverse("activityList"))
        html = response.content.decode("utf-8")

        self.assertLess(html.index(link_error.title), html.index(ok.title))
