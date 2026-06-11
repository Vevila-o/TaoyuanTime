import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT_DIR = Path(__file__).resolve().parents[1]
DATABASE_DIR = ROOT_DIR / "Database"
if str(DATABASE_DIR) not in sys.path:
    sys.path.insert(0, str(DATABASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from events.ai_tagger import (
    apply_safe_repairs,
    apply_deterministic_quality_filters,
    classify_warnings,
    extract_strong_region_evidence,
    normalize_ai_result,
    parse_json_object,
)
from events.management.commands.ai_tag_activities import build_audit_item, json_activity_from_item


def fake_tag(tag_id, name, tag_type):
    return SimpleNamespace(id=tag_id, name=name, tag_type=tag_type)


def tag_map(*tags):
    return {(tag.tag_type, tag.name): tag for tag in tags}


class AiTagQualityTests(unittest.TestCase):
    def test_json_activity_preserves_unknown_fee_and_ocr_fields(self):
        item = {
            "activity_uid": "front_1",
            "source_key": "culture",
            "title": "測試活動",
            "fee_type": "unknown",
            "is_free": None,
            "registration_url": "https://example.com/register",
            "ocr_text": "海報文字",
            "ocr_summary": "海報摘要",
            "ocr_status": "success",
        }

        activity = json_activity_from_item(item, 1)

        self.assertIsNone(activity.is_free)
        self.assertEqual(activity.fee_type, "unknown")
        self.assertEqual(activity.ocr_text, "海報文字")
        self.assertEqual(activity.ocr_summary, "海報摘要")
        self.assertEqual(activity.activity_uid, "front_1")
        self.assertIn("https://example.com/register", activity.registration_info)

    def test_non_whitelist_tag_goes_to_missing_not_accepted(self):
        tags = tag_map(fake_tag(1, "展覽", "activity_type"))
        result = normalize_ai_result(
            {"tags": [{"name": "不存在標籤", "tag_type": "activity_type", "confidence": 0.95}]},
            tags,
            min_confidence=0.6,
        )

        self.assertEqual(result["accepted_tags"], [])
        self.assertEqual(result["missing_tags"][0]["name"], "不存在標籤")

    def test_normalize_repairs_keeps_valid_and_rejects_unsafe_items(self):
        future_date = "2026-12-17"
        result = normalize_ai_result(
            {
                "repairs": [
                    {
                        "field": "start_date",
                        "value": future_date,
                        "confidence": 0.8,
                        "evidence_text": f"活動日期：{future_date}",
                        "evidence_source": "ocr",
                    },
                    {
                        "field": "location",
                        "value": "桃園市大溪區壹號館",
                        "confidence": 0.4,
                        "evidence_text": "活動地點：壹號館",
                        "evidence_source": "html_main",
                    },
                    {
                        "field": "unknown",
                        "value": "x",
                        "confidence": 0.9,
                        "evidence_text": "x",
                        "evidence_source": "html_main",
                    },
                    {
                        "field": "district",
                        "value": "大溪區",
                        "confidence": 0.9,
                        "evidence_text": "",
                        "evidence_source": "html_main",
                    },
                ]
            },
            {},
            min_confidence=0.6,
        )

        self.assertEqual(result["repair_suggestions"][0]["field"], "start_date")
        reject_reasons = {item["reject_reason"] for item in result["rejected_repairs"]}
        self.assertIn("confidence below 0.65", reject_reasons)
        self.assertIn("unknown_field", reject_reasons)
        self.assertIn("missing_evidence", reject_reasons)

    def test_repair_rejects_ambiguous_district_and_non_taoyuan_location(self):
        result = normalize_ai_result(
            {
                "repairs": [
                    {
                        "field": "district",
                        "value": "桃園",
                        "confidence": 0.9,
                        "evidence_text": "桃園市民可報名",
                        "evidence_source": "html_text",
                    },
                    {
                        "field": "location",
                        "value": "日本神戶市",
                        "confidence": 0.95,
                        "evidence_text": "活動地點為日本神戶市",
                        "evidence_source": "html_text",
                    },
                    {
                        "field": "district",
                        "value": "大溪",
                        "confidence": 0.95,
                        "evidence_text": "活動地點：大溪分館",
                        "evidence_source": "html_main",
                    },
                ]
            },
            {},
            min_confidence=0.6,
        )

        self.assertEqual(result["repair_suggestions"][0]["field"], "district")
        self.assertEqual(result["repair_suggestions"][0]["value"], "大溪區")
        reject_reasons = {item["reject_reason"] for item in result["rejected_repairs"]}
        self.assertIn("invalid_taoyuan_district", reject_reasons)
        self.assertIn("non_taoyuan_location", reject_reasons)

    def test_repair_rejects_registration_deadline_as_activity_date(self):
        result = normalize_ai_result(
            {
                "repairs": [
                    {
                        "field": "start_date",
                        "value": "2026-06-01T14:00:00+08:00",
                        "confidence": 0.9,
                        "evidence_text": "報名期限 2026-06-01 00:00～",
                        "evidence_source": "html_main",
                    },
                    {
                        "field": "end_date",
                        "value": "2026-11-21T16:00:00+08:00",
                        "confidence": 0.9,
                        "evidence_text": "活動時間 2026-11-21 14:00 ～ 2026-11-21 16:00",
                        "evidence_source": "html_main",
                    },
                ]
            },
            {},
            min_confidence=0.6,
        )

        self.assertEqual(result["repair_suggestions"][0]["field"], "end_date")
        self.assertEqual(
            result["rejected_repairs"][0]["reject_reason"],
            "registration_deadline_not_activity_date",
        )

    def test_safe_repairs_do_not_overwrite_existing_values(self):
        activity = SimpleNamespace(
            start_date="existing-date",
            end_date=None,
            location="既有地點",
            district="",
            registration_info="",
            registration_url="",
            fee_type="unknown",
        )
        result = {
            "repair_suggestions": [
                {
                    "field": "location",
                    "value": "新地點",
                    "confidence": 0.9,
                    "evidence_text": "地點：新地點",
                    "evidence_source": "ocr",
                },
                {
                    "field": "district",
                    "value": "大溪區",
                    "confidence": 0.9,
                    "evidence_text": "地點：大溪區",
                    "evidence_source": "ocr",
                },
            ],
            "rejected_repairs": [],
        }

        outcome = apply_safe_repairs(activity, result, dry_run=True)

        self.assertEqual(outcome["applied_repairs"][0]["field"], "district")
        self.assertEqual(outcome["rejected_repairs"][0]["reject_reason"], "existing_value_present")

    def test_mutually_exclusive_cost_tags_are_rejected(self):
        tags = tag_map(
            fake_tag(1, "免費", "cost"),
            fake_tag(2, "金額未提供", "cost"),
        )
        activity = SimpleNamespace(
            title="免費入場活動",
            description="免費入場",
            raw_content="",
            district="",
            location="",
            fee_type="unknown",
            is_free=None,
            fee_description="免費入場",
            registration_info="",
            ocr_text="",
            ocr_summary="",
        )
        result = normalize_ai_result(
            {
                "tags": [
                    {"name": "免費", "tag_type": "cost", "confidence": 0.9},
                    {"name": "金額未提供", "tag_type": "cost", "confidence": 0.95},
                ]
            },
            tags,
            min_confidence=0.6,
        )

        apply_deterministic_quality_filters(activity, result, tags)

        accepted_costs = [tag["name"] for tag in result["accepted_tags"] if tag["tag_type"] == "cost"]
        self.assertEqual(accepted_costs, ["免費"])
        self.assertTrue(any(tag.get("reject_level") == "blocking" for tag in result["rejected_tags"]))

    def test_no_discount_requires_explicit_evidence(self):
        tags = tag_map(fake_tag(1, "無優惠", "discount"))
        activity = SimpleNamespace(
            title="展覽活動",
            description="一般展覽活動",
            raw_content="",
            district="",
            location="",
            fee_type="unknown",
            is_free=None,
            fee_description="",
            registration_info="",
            ocr_text="",
            ocr_summary="",
        )
        result = normalize_ai_result(
            {"tags": [{"name": "無優惠", "tag_type": "discount", "confidence": 0.9}]},
            tags,
            min_confidence=0.6,
        )

        apply_deterministic_quality_filters(activity, result, tags)

        self.assertEqual(result["accepted_tags"], [])
        self.assertEqual(result["rejected_tags"][0]["reject_reason"], "no-discount tag lacks explicit evidence")

    def test_audit_item_fails_when_core_tag_is_missing(self):
        result = {
            "activity_id": 1,
            "activity_title": "測試活動",
            "accepted_tags": [{"name": "一般", "tag_type": "audience", "confidence": 0.9}],
            "rejected_tags": [],
            "missing_tags": [],
            "warnings": [],
            "blocking_warnings": [],
            "info_warnings": [],
            "confidence": 0.9,
        }

        item = build_audit_item(result, {("audience", "一般")}, 0.6)

        self.assertFalse(item["quality_pass"])
        self.assertIn("missing_high_confidence_core_tag", item["fail_reasons"])

    def test_ocr_conflict_warning_is_info_not_blocking(self):
        groups = classify_warnings([
            "OCR 文字將地點地址誤植為民族路，與頁面欄位縣府路不符。",
        ])

        self.assertEqual(groups["blocking_warnings"], [])
        self.assertEqual(len(groups["info_warnings"]), 1)

    def test_non_ocr_conflict_warning_stays_blocking(self):
        groups = classify_warnings([
            "AI suggested region 中壢, but title/location indicates 桃園，地區衝突。",
        ])

        self.assertEqual(len(groups["blocking_warnings"]), 1)
        self.assertEqual(groups["info_warnings"], [])

    def test_registration_field_warning_is_info_not_blocking(self):
        groups = classify_warnings([
            "registration_info 有網址顯示需報名，但 requires_registration 為 false，兩者資訊有衝突。",
        ])

        self.assertEqual(groups["blocking_warnings"], [])
        self.assertEqual(len(groups["info_warnings"]), 1)

    def test_registration_url_warning_is_info_not_blocking(self):
        groups = classify_warnings([
            "registration_info 含 URL 但 requires_registration 為 false，可能為備用連結或誤標。",
        ])

        self.assertEqual(groups["blocking_warnings"], [])
        self.assertEqual(len(groups["info_warnings"]), 1)

    def test_taoyuan_city_text_does_not_override_explicit_district(self):
        activity = SimpleNamespace(
            title="桃園市立美術館展覽",
            location="桃園市立美術館",
            district="中壢",
        )

        regions = extract_strong_region_evidence(activity, ["桃園", "中壢"])

        self.assertEqual(regions, {"中壢"})

    def test_taoyuan_city_text_alone_is_not_taoyuan_district(self):
        activity = SimpleNamespace(
            title="桃園市政府活動",
            location="桃園市立美術館",
            district="",
        )

        regions = extract_strong_region_evidence(activity, ["桃園", "中壢"])

        self.assertEqual(regions, set())

    def test_resolved_cost_warning_is_info_not_blocking(self):
        groups = classify_warnings([
            "付費與免費互斥，依票價欄位判斷為付費。",
        ])

        self.assertEqual(groups["blocking_warnings"], [])
        self.assertEqual(len(groups["info_warnings"]), 1)

    def test_chinese_activity_tag_type_maps_to_activity_type(self):
        tags = tag_map(fake_tag(1, "節慶", "activity_type"))
        result = normalize_ai_result(
            {"tags": [{"name": "節慶", "tag_type": "活動", "confidence": 0.9}]},
            tags,
            min_confidence=0.6,
        )

        self.assertEqual(result["accepted_tags"][0]["tag_type"], "activity_type")
        self.assertEqual(result["accepted_tags"][0]["name"], "節慶")

    def test_parse_json_object_repairs_missing_commas_between_items(self):
        parsed = parse_json_object(
            """
            {
              "tags": [
                {"name": "免費", "tag_type": "cost"}
                {"name": "大溪", "tag_type": "region"}
              ],
              "repairs": [
                {"field": "location", "value": "壹號館"}
                {"field": "district", "value": "大溪區"}
              ]
            }
            """
        )

        self.assertEqual(len(parsed["tags"]), 2)
        self.assertEqual(parsed["repairs"][1]["field"], "district")

    def test_mixed_registration_warning_is_info_not_blocking(self):
        groups = classify_warnings([
            "報名資訊矛盾：部分活動需網路報名，部分活動為自由參加，需依具體活動項目判斷。",
        ])

        self.assertEqual(groups["blocking_warnings"], [])
        self.assertEqual(len(groups["info_warnings"]), 1)

    def test_resolved_registration_warning_is_info_not_blocking(self):
        groups = classify_warnings([
            "免預約與需報名互斥，依 requires_registration 為 false 選免預約",
        ])

        self.assertEqual(groups["blocking_warnings"], [])
        self.assertEqual(len(groups["info_warnings"]), 1)


if __name__ == "__main__":
    unittest.main()
