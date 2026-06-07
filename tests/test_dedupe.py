import unittest

from pipeline.dedupe import deduplicate


class DedupeTests(unittest.TestCase):
    def test_keeps_canonical_source_when_rss_mirror_duplicates(self):
        canonical = {
            "source_key": "tycg_events",
            "source_url": "https://www.tycg.gov.tw/News_Content.aspx?n=8&s=1618809",
            "official_detail_url": "https://www.tycg.gov.tw/News_Content.aspx?n=8&s=1618809",
            "title": "活動 A",
            "date_start": "2026-06-01",
            "location": "桃園展演中心",
            "clean_description": "描述",
            "quality_score": 95,
            "quality_warnings": [],
        }
        mirror = {
            "source_key": "tycg_events_rss",
            "source_url": "https://travel.tycg.gov.tw/zh-tw/event/calendardetail/6709",
            "official_detail_url": "https://www.tycg.gov.tw/News_Content.aspx?n=8&s=1618809",
            "title": "活動 A",
            "date_start": "2026-06-01",
            "location": "桃園展演中心",
            "clean_description": "描述",
            "quality_score": 80,
            "quality_warnings": [],
        }

        events = deduplicate([mirror, canonical])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source_key"], "tycg_events")
        self.assertIn("cross_source_duplicate_merged", events[0]["quality_warnings"])
        self.assertTrue(events[0].get("duplicate_source_keys"))

    def test_cross_source_fallback_key_merges_without_url(self):
        left = {
            "source_key": "culture",
            "title": "活動 B",
            "date_start": "2026-07-01",
            "location": "中壢藝術館",
            "clean_description": "描述 B",
            "quality_score": 90,
            "quality_warnings": [],
        }
        right = {
            "source_key": "culture_rss",
            "title": "活動 B",
            "date_start": "2026-07-01",
            "district": "中壢區",
            "location": "中壢藝術館",
            "clean_description": "描述 B",
            "quality_score": 70,
            "quality_warnings": [],
        }

        events = deduplicate([left, right])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source_key"], "culture")

    def test_event_culture_act_id_keeps_distinct_events(self):
        first = {
            "source_key": "tmofa_events",
            "source_url": "https://event.culture.tw/mocweb/reg/TMOFA/Detail.init.ctr?actId=60027",
            "official_detail_url": "https://event.culture.tw/mocweb/reg/TMOFA/Detail.init.ctr?actId=60027",
            "title": "活動 C",
            "date_start": "2026-07-14",
            "location": "桃園市兒童美術館",
            "clean_description": "描述 C",
            "quality_score": 90,
        }
        second = {
            "source_key": "tmofa_events",
            "source_url": "https://event.culture.tw/mocweb/reg/TMOFA/Detail.init.ctr?actId=60033",
            "official_detail_url": "https://event.culture.tw/mocweb/reg/TMOFA/Detail.init.ctr?actId=60033",
            "title": "活動 D",
            "date_start": "2026-06-07",
            "location": "桃園市立美術館",
            "clean_description": "描述 D",
            "quality_score": 90,
        }

        events = deduplicate([first, second])

        self.assertEqual(len(events), 2)
        self.assertEqual({event["source_item_id"] for event in events}, {"60027", "60033"})


if __name__ == "__main__":
    unittest.main()
