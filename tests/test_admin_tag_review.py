from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events.models import Activity, ActivityTagSuggestion


class AdminTagReviewTests(TestCase):
    def test_tag_review_only_shows_serviceable_recommendation_suggestions(self):
        valid = Activity.objects.create(
            title="可推薦活動",
            description="活動內容",
            status="active",
            is_activity=True,
            excluded_from_public=False,
            line_ready=True,
            recommendation_ready=True,
            official_detail_url="https://example.com/valid",
            start_date=timezone.now() + timedelta(days=3),
            end_date=timezone.now() + timedelta(days=4),
            district="中壢區",
            location="中壢藝術館",
        )
        expired = Activity.objects.create(
            title="過期活動",
            description="活動內容",
            status="active",
            is_activity=True,
            excluded_from_public=False,
            line_ready=False,
            recommendation_ready=False,
            official_detail_url="https://example.com/expired",
            start_date=timezone.now() - timedelta(days=10),
            end_date=timezone.now() - timedelta(days=1),
            district="中壢區",
            location="中壢藝術館",
        )
        inactive = Activity.objects.create(
            title="已下架活動",
            description="活動內容",
            status="inactive",
            is_activity=True,
            excluded_from_public=False,
            line_ready=False,
            recommendation_ready=False,
            official_detail_url="https://example.com/inactive",
            start_date=timezone.now() + timedelta(days=3),
            end_date=timezone.now() + timedelta(days=4),
            district="中壢區",
            location="中壢藝術館",
        )
        ActivityTagSuggestion.objects.create(activity=valid, tag_name="親子", tag_type="theme", status="pending")
        ActivityTagSuggestion.objects.create(activity=expired, tag_name="手作", tag_type="theme", status="pending")
        ActivityTagSuggestion.objects.create(activity=inactive, tag_name="音樂", tag_type="theme", status="pending")

        response = self.client.get(reverse("tagReview"))
        html = response.content.decode("utf-8")

        self.assertContains(response, valid.title)
        self.assertContains(response, "目前待審")
        self.assertContains(response, '<div class="number">1</div>', html=True)
        self.assertNotIn(expired.title, html)
        self.assertNotIn(inactive.title, html)
