import unittest
from unittest.mock import patch

from scraping.scripts import build_source_health_check


def build(events, source_summary, health_report=None):
    health_report = health_report or {"overall_status": "PASS", "totals": {}, "source_quality_summary": []}

    def fake_load_json(path, default):
        if path == build_source_health_check.EVENTS_PATH:
            return events
        if path == build_source_health_check.SOURCE_SUMMARY_PATH:
            return source_summary
        if path == build_source_health_check.HEALTH_REPORT_PATH:
            return health_report
        return default

    with patch.object(build_source_health_check, "load_json", side_effect=fake_load_json):
        return build_source_health_check.build_source_health()


class SourceHealthTests(unittest.TestCase):
    def test_deduped_out_source_not_reported_as_no_data(self):
        report = build(
            events=[],
            source_summary=[
                {
                    "source_key": "tycg_events_rss",
                    "source_name": "RSS",
                    "items_created": 12,
                    "list_items_found": 30,
                    "status": "success",
                    "major_issues": [],
                }
            ],
        )
        src = report["sources"][0]
        self.assertEqual(src["raw_total"], 12)
        self.assertEqual(src["total"], 0)
        self.assertEqual(src["parse_status"], "deduped_out")
        self.assertEqual(src["health_level"], "deduped_only")

    def test_no_list_items_status_is_exposed(self):
        report = build(
            events=[],
            source_summary=[
                {
                    "source_key": "culture_rss",
                    "source_name": "Culture RSS",
                    "items_created": 0,
                    "list_items_found": 0,
                    "status": "no_data",
                    "major_issues": ["no_list_items_found"],
                }
            ],
        )
        src = report["sources"][0]
        self.assertEqual(src["parse_status"], "no_list_items")
        self.assertEqual(src["health_level"], "no_data")

    def test_rss_fetch_failure_status_is_exposed(self):
        report = build(
            events=[],
            source_summary=[
                {
                    "source_key": "tycg_events_rss",
                    "source_name": "RSS",
                    "items_created": 0,
                    "list_items_found": 0,
                    "status": "no_data",
                    "major_issues": ["rss_list_fetch_failed: timeout"],
                }
            ],
        )
        src = report["sources"][0]
        self.assertEqual(src["parse_status"], "fetch_failed")


if __name__ == "__main__":
    unittest.main()
