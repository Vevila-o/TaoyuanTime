import unittest
from unittest.mock import patch

from scraping.scripts import build_health_report


OFFICIAL_URL = "https://culture.tycg.gov.tw/home.jsp?id=93&parentpath=0,16&mcustomize=activity_view.jsp&dataserno=1"


def run_report(events, source_summary=None):
    def fake_load_json(path, default):
        if path == build_health_report.EVENTS_PATH:
            return events
        if path == build_health_report.RUN_SUMMARY_PATH:
            failed_sources = sum(1 for item in (source_summary or []) if item.get("status") == "failed")
            return {"run_id": "test", "success_sources": 1, "failed_sources": failed_sources}
        if path == build_health_report.SOURCE_SUMMARY_PATH:
            return source_summary or []
        return default

    with patch.object(build_health_report, "load_json", side_effect=fake_load_json):
        with patch.object(build_health_report, "db_schema_ok", return_value=(True, [])):
            return build_health_report.build_report()


def metric_by_name(report, section, name):
    return next(metric for metric in report[section] if metric["name"] == name)


class HealthReportTests(unittest.TestCase):
    def test_ai_and_recommendation_denominators_use_serviceable_active_items(self):
        events = [
            {
                "source_key": "culture",
                "content_type": "activity",
                "is_activity": True,
                "date_start": "2099-01-10",
                "location": "桃園展演中心",
                "official_detail_url": OFFICIAL_URL,
                "ai_ready": True,
                "ai_input_text": "完整活動描述",
                "line_card_ready": True,
                "search_ready": True,
                "recommendation_ready": True,
                "quality_level": "usable",
            },
            {
                "source_key": "culture",
                "content_type": "activity",
                "is_activity": True,
                "date_start": "2000-01-10",
                "location": "桃園展演中心",
                "official_detail_url": OFFICIAL_URL,
                "ai_ready": False,
                "freshness_status": "expired",
            },
            {
                "source_key": "culture",
                "content_type": "activity",
                "is_activity": True,
                "location": "桃園展演中心",
                "official_detail_url": OFFICIAL_URL,
                "ai_ready": False,
            },
            {
                "source_key": "culture",
                "content_type": "activity",
                "is_activity": True,
                "date_start": "2099-01-10",
                "location": "桃園展演中心",
                "official_detail_url": OFFICIAL_URL,
                "ai_ready": False,
                "manual_review_required": True,
            },
        ]

        report = run_report(events)
        ai_metric = metric_by_name(report, "ai_function_metrics", "ai_input_ready")
        recommendation_metric = metric_by_name(report, "ai_function_metrics", "recommendation_ready")

        self.assertEqual(report["totals"]["serviceable_active_items"], 1)
        self.assertEqual(report["totals"]["expired_items"], 1)
        self.assertEqual(report["totals"]["needs_review_or_incomplete_items"], 2)
        self.assertEqual(ai_metric["total"], 1)
        self.assertEqual(ai_metric["passed"], 1)
        self.assertEqual(recommendation_metric["total"], 1)
        self.assertEqual(recommendation_metric["passed"], 1)

    def test_recommendation_pool_purity_still_fails_for_non_activity(self):
        events = [
            {
                "source_key": "culture",
                "content_type": "announcement",
                "is_activity": False,
                "date_start": "2099-01-10",
                "location": "桃園展演中心",
                "official_detail_url": OFFICIAL_URL,
                "recommendation_ready": True,
            }
        ]

        report = run_report(events)
        purity_metric = metric_by_name(report, "health_metrics", "recommendation_pool_purity")

        self.assertEqual(purity_metric["status"], "FAIL")
        self.assertIn("health", report["failed_sections"])

    def test_public_pool_missing_required_fields_still_fails(self):
        events = [
            {
                "source_key": "culture",
                "content_type": "activity",
                "is_activity": True,
                "is_public_item": True,
                "line_card_ready": True,
                "quality_level": "usable",
            }
        ]

        report = run_report(events)
        official_metric = metric_by_name(report, "basic_function_metrics", "official_detail_url")
        date_metric = metric_by_name(report, "basic_function_metrics", "date_calendar_ready")
        location_metric = metric_by_name(report, "basic_function_metrics", "location_ready")

        self.assertEqual(official_metric["status"], "FAIL")
        self.assertEqual(date_metric["status"], "FAIL")
        self.assertEqual(location_metric["status"], "FAIL")
        self.assertIn("basic_function_metrics", report["failed_sections"])

    def test_new_official_activity_domains_count_as_grounded_urls(self):
        events = [
            {
                "source_key": "library_activity_rss",
                "content_type": "activity",
                "is_activity": True,
                "is_public_item": True,
                "date_start": "2099-01-10",
                "location": "桃園市立圖書館",
                "official_detail_url": "https://www.typl.gov.tw/zh-tw/Activity/Content/9631",
                "line_card_ready": True,
                "search_ready": True,
                "recommendation_ready": True,
                "quality_level": "usable",
            },
            {
                "source_key": "tmofa_exhibitions",
                "content_type": "activity",
                "is_activity": True,
                "is_public_item": True,
                "date_start": "2099-01-10",
                "location": "橫山書法藝術館",
                "official_detail_url": "https://tmofa.tycg.gov.tw/ch/exhibitions/current-exhibitions/154",
                "line_card_ready": True,
                "search_ready": True,
                "recommendation_ready": True,
                "quality_level": "usable",
            },
        ]

        report = run_report(events)
        official_metric = metric_by_name(report, "basic_function_metrics", "official_detail_url")

        self.assertEqual(official_metric["status"], "PASS")
        self.assertEqual(official_metric["passed"], 2)

    def test_filtered_source_failure_is_warning_not_health_failure(self):
        events = [
            {
                "source_key": "culture",
                "content_type": "activity",
                "is_activity": True,
                "date_start": "2099-01-10",
                "location": "桃園展演中心",
                "official_detail_url": OFFICIAL_URL,
                "ai_ready": True,
                "ai_input_text": "完整活動描述",
                "line_card_ready": True,
                "search_ready": True,
                "recommendation_ready": True,
                "quality_level": "usable",
            }
        ]
        source_summary = [
            {"source_key": "culture", "status": "success", "items_created": 1},
            {"source_key": "travel_news", "status": "failed", "items_created": 0, "major_issues": ["timeout"]},
        ]

        report = run_report(events, source_summary)
        crawler_metric = metric_by_name(report, "health_metrics", "crawler_run_completed")

        self.assertEqual(crawler_metric["status"], "PASS")
        self.assertIn("travel_news", crawler_metric["details"]["filtered_failed_sources"])
        self.assertNotIn("health", report["failed_sections"])


if __name__ == "__main__":
    unittest.main()
