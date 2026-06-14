from django.db.models import Q
from django.test import TestCase
from django.urls import reverse

from events.models import Activity, Subscription, UserProfile


class AdminDashboardTests(TestCase):
    def test_dashboard_excludes_test_line_users_from_main_count(self):
        real_user = UserProfile.objects.create(line_user_id="Ureal001", display_name="真實使用者")
        UserProfile.objects.create(line_user_id="codex-smoke-user", display_name="測試使用者")
        UserProfile.objects.create(line_user_id="line-test-user", display_name="測試使用者")
        UserProfile.objects.create(line_user_id="debug-user", display_name="測試使用者")
        activity = Activity.objects.create(title="測試活動", status="active")
        Subscription.objects.create(user=real_user, activity=activity, status="active")

        response = self.client.get(reverse("dashboard"))
        html = response.content.decode("utf-8")

        self.assertContains(response, "LINE 使用者")
        self.assertContains(response, '<div class="number">1</div>', html=True)
        self.assertIn("測試 3 已排除", html)

        test_user_count = UserProfile.objects.filter(
            Q(line_user_id__startswith="codex")
            | Q(line_user_id__startswith="line-test")
            | Q(line_user_id="debug-user")
        ).count()
        self.assertEqual(test_user_count, 3)
