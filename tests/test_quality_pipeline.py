import os
import sqlite3
import tempfile
import unittest
import json
from pathlib import Path

from PIL import Image

from pipeline.asset_downloader import read_image_dimensions
from pipeline.asset_validator import validate_assets
from pipeline.classify_content import classify_content
from pipeline.extract_dates import extract_dates
from pipeline.extract_fee import extract_fee
from pipeline.extract_location import extract_location
from pipeline.line_card_readiness import check_line_card_readiness
from pipeline.compute_readiness import compute_readiness
from pipeline.normalize_text import normalize_text
from pipeline.save_sqlite import save_to_sqlite
from pipeline.save_json import save_to_json


class QualityPipelineTests(unittest.TestCase):
    def test_non_activity_is_not_recommendation_ready(self):
        event = {
            "title": "6月1日起工廠校正起跑，請桃園工廠業者多利用線上申報省時又便利",
            "clean_description": "將於115年6月1日至7月10日展開年度工廠校正及營運調查。",
            "source_url": "https://edb.tycg.gov.tw/News_Content.aspx?n=3749&s=1623022",
            "date_start": "2026-06-01",
            "location": "桃園市政府",
        }

        event = classify_content(event)
        event = check_line_card_readiness(event)

        self.assertEqual(event["content_type"], "announcement")
        self.assertFalse(event["line_card_ready"])
        self.assertFalse(event["recommendation_ready"])
        self.assertEqual(event["exclude_from_recommendation_reason"], "not_activity")

    def test_penalty_list_is_publicly_excluded_even_with_date_and_location(self):
        event = {
            "title": "違反發展觀光條例經裁罰之非法旅宿名單至115年5月31日止",
            "clean_description": "裁罰名單公告，地點桃園市政府。",
            "source_url": "https://example.com/penalty",
            "date_start": "2026-05-31",
            "location": "桃園市政府",
            "quality_level": "usable",
        }

        event = compute_readiness(check_line_card_readiness(classify_content(event)))

        self.assertEqual(event["content_type"], "penalty_list")
        self.assertTrue(event["excluded_from_public"])
        self.assertEqual(event["exclude_reason"], "penalty_list")
        self.assertEqual(event["final_state"], "non_activity")
        self.assertFalse(event["line_ready"])
        self.assertFalse(event["recommendation_ready"])
        self.assertFalse(event["published"])

    def test_venue_notice_is_publicly_excluded_even_when_it_mentions_activity(self):
        event = {
            "title": "【公告】中路運動公園網球場配合活動暫停對外開放時間",
            "clean_description": "公告網球場因活動暫停開放，請民眾留意。",
            "source_url": "https://example.com/venue",
            "date_start": "2026-06-20",
            "location": "中路運動公園",
            "quality_level": "usable",
        }

        event = compute_readiness(check_line_card_readiness(classify_content(event)))

        self.assertEqual(event["content_type"], "venue_notice")
        self.assertTrue(event["excluded_from_public"])
        self.assertFalse(event["line_ready"])
        self.assertEqual(event["exclude_from_recommendation_reason"], "venue_notice")

    def test_news_promo_without_activity_fields_is_publicly_excluded(self):
        event = {
            "title": "舒華現身香港、新加坡 桃園觀光廣告海外再掀話題",
            "clean_description": "桃園觀光宣傳成果新聞，海外廣告引發討論。",
            "source_url": "https://example.com/news",
            "date_start": "2026-06-20",
            "location": "桃園市",
            "quality_level": "usable",
        }

        event = compute_readiness(check_line_card_readiness(classify_content(event)))

        self.assertEqual(event["content_type"], "news")
        self.assertTrue(event["excluded_from_public"])
        self.assertFalse(event["recommendation_ready"])

    def test_location_rejects_sentence_fragment(self):
        event = {
            "title": "YOUNG桃下一步｜提名桃企抽禮物活動開跑",
            "clean_description": "③ ＠三位好友，並留言：「YOUNG桃下一步」。115/5/22進行公告。",
        }

        event = extract_location(event)

        self.assertIsNone(event["location"])
        self.assertEqual(event["location_parse_status"], "failed")

    def test_date_range_with_partial_end_date(self):
        event = {
            "title": "2026國際馬術節桃園登場",
            "date_text": "活動時間：2026年5月22日至5月31日",
            "clean_description": "",
        }

        event = extract_dates(event)

        self.assertEqual(event["date_start"], "2026-05-22")
        self.assertEqual(event["date_end"], "2026-05-31")
        self.assertEqual(event["date_parse_status"], "success")

    def test_month_day_range_uses_traceable_year(self):
        event = {
            "title": "2026桃園夏日活動",
            "date_text": "活動期間：5/22-5/31",
            "clean_description": "",
        }

        event = extract_dates(event)

        self.assertEqual(event["date_start"], "2026-05-22")
        self.assertEqual(event["date_end"], "2026-05-31")

    def test_location_rejects_bad_location_text_fragment(self):
        event = {
            "title": "青年活動新聞",
            "location_text": "桃園市政府青年事務局局長侯佳齡表示，近年運動娛樂與商業演出市場",
            "clean_description": "",
        }

        event = extract_location(event)

        self.assertIsNone(event["location"])
        self.assertEqual(event["location_parse_status"], "failed")

    def test_known_venue_fills_district(self):
        event = {
            "title": "中壢音樂會",
            "location_text": "中壢藝術館第1展覽室",
            "clean_description": "",
        }

        event = extract_location(event)

        self.assertEqual(event["location"], "中壢藝術館第1展覽室")
        self.assertEqual(event["district"], "中壢區")

    def test_policy_news_is_not_recommendation_ready(self):
        event = {
            "title": "桃市首創光電指引 串聯中央修法補強管理缺口",
            "clean_description": "桃園市正式公布太陽光電設施設置指引，補強中央修法管理缺口。",
            "source_url": "https://edb.tycg.gov.tw/News_Content.aspx?n=3749&s=1622047",
            "date_start": "2026-06-01",
            "location": "桃園市政府",
        }

        event = classify_content(event)
        event = check_line_card_readiness(event)

        self.assertEqual(event["content_type"], "policy")
        self.assertFalse(event["line_card_ready"])
        self.assertFalse(event["recommendation_ready"])

    def test_fee_amount_requires_fee_context(self):
        event = {
            "title": "財報公告",
            "clean_description": "企業務必完成商業決算及財報承認，違規最重罰30萬元。",
        }

        event = extract_fee(event)

        self.assertEqual(event["fee_type"], "unknown")
        self.assertIsNone(event["is_free"])

    def test_paid_and_registration_url_are_extracted(self):
        event = {
            "title": "售票活動",
            "clean_description": "OPENTIX售票，票價400元，報名網址：https://www.opentix.life/event/12345",
        }

        event = extract_fee(event)

        self.assertEqual(event["fee_type"], "paid")
        self.assertEqual(event["fee_evidence_text"], "票價")
        self.assertEqual(event["registration_method"], "online")
        self.assertEqual(event["registration_url"], "https://www.opentix.life/event/12345")
        self.assertEqual(event["registration_parse_status"], "success")

    def test_common_culture_registration_page_is_not_activity_registration(self):
        event = {
            "title": "文化局活動",
            "registration_url": "https://culture.tycg.gov.tw/ActiveList.aspx?n=23648&sms=20299",
            "registration_method": "online",
            "clean_description": "活動日期：115-06-01 活動地址：桃園展演中心。",
        }

        event = extract_fee(event)

        self.assertEqual(event["registration_method"], "unknown")
        self.assertIsNone(event["registration_url"])
        self.assertEqual(event["registration_parse_status"], "not_found")

    def test_fee_evidence_and_mixed_fee_are_preserved(self):
        event = {
            "title": "部分收費活動",
            "clean_description": "主展免費入場，工作坊報名費300元。",
        }

        event = extract_fee(event)

        self.assertEqual(event["fee_type"], "mixed")
        self.assertIsNone(event["is_free"])
        self.assertIn("免費入場", event["fee_evidence_text"])
        self.assertIn("報名費", event["fee_evidence_text"])

    def test_volunteer_recruitment_is_not_activity(self):
        event = {
            "title": "115全民運志工／賽場服務生招募",
            "clean_description": "桃園市立桃園高級中等學校辦理志工與賽場服務生招募。",
        }

        event = classify_content(event)

        self.assertEqual(event["content_type"], "recruitment")
        self.assertFalse(event["is_activity"])

    def test_volunteer_platform_training_is_not_public_activity(self):
        event = {
            "title": "轉知本府辦理「桃園市志願服務整合資訊平台(以下簡稱桃園志工網)」教育訓練",
            "clean_description": "請貴單位志工業務承辦人、督導或幹部等單位管理者踴躍報名參加。",
        }

        event = classify_content(event)
        event = check_line_card_readiness(event)

        self.assertEqual(event["content_type"], "admin_notice")
        self.assertFalse(event["is_activity"])
        self.assertFalse(event["recommendation_ready"])

    def test_sqlite_quality_columns_are_added(self):
        event = {
            "source_name": "桃園觀光導覽網 OpenAPI",
            "source_key": "travel_openapi",
            "source_url": "https://travel.tycg.gov.tw/zh-tw/event/calendardetail/1",
            "official_detail_url": "https://travel.tycg.gov.tw/zh-tw/event/calendardetail/1",
            "title": "測試活動",
            "content_type": "activity",
            "item_type": "activity",
            "is_activity": True,
            "line_ready": True,
            "line_card_ready": True,
            "search_ready": True,
            "ai_ready": True,
            "recommendation_ready": True,
            "quality_warnings": [],
        }

        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            db_path = os.path.join(tmpdir, "activities.db")
            save_to_sqlite([event], filepath=db_path)
            conn = sqlite3.connect(db_path)
            try:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(activities)").fetchall()}
            finally:
                conn.close()

        for column in {
            "official_detail_url",
            "status",
            "item_type",
            "is_activity",
            "is_public_item",
            "line_ready",
            "recommendation_ready",
            "excluded_from_public",
            "exclude_reason",
            "final_state",
            "quality_warnings",
            "exclude_from_recommendation_reason",
            "fee_type",
            "fee_evidence_text",
            "registration_parse_status",
            "registration_evidence_text",
            "activity_uid",
            "source_item_id",
            "ocr_ready",
            "ocr_text",
            "ocr_status",
        }:
            self.assertIn(column, columns)

    def test_front_facing_json_outputs_share_same_activity_ids(self):
        common = {
            "source_name": "桃園市政府文化局",
            "source_key": "culture",
            "source_url": "https://culture.tycg.gov.tw/News_Content.aspx?n=11099&s=1",
            "official_detail_url": "https://culture.tycg.gov.tw/News_Content.aspx?n=11099&s=1",
            "content_type": "activity",
            "item_type": "activity",
            "is_activity": True,
            "quality_level": "usable",
            "quality_score": 95,
            "date_start": "2099-01-01",
            "location": "桃園展演中心",
            "district": "桃園區",
            "line_ready": True,
            "line_card_ready": True,
            "search_ready": True,
            "is_public_item": True,
            "recommendation_ready": True,
            "ai_ready": True,
            "quality_warnings": [],
        }
        events = [
            {**common, "title": "完整前台活動", "activity_uid": "front_ok", "ai_input_text": "完整活動描述"},
            {**common, "title": "缺 AI 活動", "activity_uid": "front_missing_ai", "ai_ready": False},
            {**common, "title": "AI 但不可推薦", "activity_uid": "front_ai_only", "recommendation_ready": False},
        ]

        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            save_to_json(events, output_dir=tmpdir)
            outputs = {}
            for filename in {
                "activities_public.json",
                "activities_recommendation_ready.json",
                "activities_ai_ready.json",
                "ai_searchable_activities.json",
            }:
                with open(os.path.join(tmpdir, filename), "r", encoding="utf-8") as f:
                    outputs[filename] = {item["activity_uid"] for item in json.load(f)}

        public_ids = outputs["activities_public.json"]
        self.assertEqual(len(public_ids), 1)
        self.assertEqual(outputs["activities_recommendation_ready.json"], public_ids)
        self.assertEqual(outputs["activities_ai_ready.json"], public_ids)
        self.assertEqual(outputs["ai_searchable_activities.json"], public_ids)

    def test_qr_image_is_not_line_or_ocr_candidate(self):
        event = {
            "title": "音樂會",
            "quality_warnings": [],
            "extracted_assets": [
                {
                    "url": "https://example.com/qrcode.png",
                    "local_path": "data/assets/images/qrcode.png",
                    "status": "downloaded",
                    "ext": ".png",
                    "width": 266,
                    "height": 265,
                    "alt_text": "",
                    "link_text": "",
                }
            ],
        }

        event = validate_assets(event)
        asset = event["extracted_assets"][0]

        self.assertEqual(asset["image_role"], "qr_or_icon")
        self.assertFalse(asset["line_image_candidate"])
        self.assertFalse(asset["ocr_candidate"])
        self.assertTrue(event["use_default_image"])
        self.assertIsNone(event["poster_local_path"])

    def test_poster_image_becomes_primary_line_and_ocr_candidate(self):
        event = {
            "title": "展覽活動",
            "quality_warnings": [],
            "extracted_assets": [
                {
                    "url": "https://example.com/poster.jpg",
                    "local_path": "data/assets/images/poster.jpg",
                    "status": "downloaded",
                    "ext": ".jpg",
                    "width": 900,
                    "height": 1280,
                    "alt_text": "活動海報",
                    "link_text": "活動海報電子檔",
                }
            ],
        }

        event = validate_assets(event)
        asset = event["extracted_assets"][0]

        self.assertEqual(asset["image_role"], "poster")
        self.assertTrue(asset["line_image_candidate"])
        self.assertTrue(asset["line_card_candidate"])
        self.assertTrue(asset["ocr_candidate"])
        self.assertEqual(event["poster_local_path"], "data/assets/images/poster.jpg")
        self.assertFalse(event["use_default_image"])

    def test_existing_local_image_dimensions_are_read(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            image_path = Path(tmpdir) / "poster.png"
            Image.new("RGB", (640, 360), "white").save(image_path)

            width, height = read_image_dimensions(image_path)

        self.assertEqual((width, height), (640, 360))

    def test_normalize_text_truncates_adjacent_activity_tail_noise(self):
        event = {
            "description": (
                "職男人生4-笑の祭典 活動日期(起)：115-06-12 活動日期(迄)：115-06-14 "
                "活動地址：桃園市中壢區中壢藝術館音樂廳 職男人生系列是以日式搞笑風格為主的表演，"
                "內容包含漫才和短劇兩種形式，邀請觀眾一同進入捧腹大笑的世界。 "
                "回上一頁 回最上面 大成國民中學第二十屆... 桃園市國樂團-民歌風..."
            )
        }

        event = normalize_text(event)

        self.assertIn("職男人生系列", event["clean_description"])
        self.assertNotIn("大成國民中學", event["clean_description"])
        self.assertNotIn("桃園市國樂團", event["clean_description"])

    def test_normalize_text_truncates_related_image_footer(self):
        event = {
            "description": (
                "或躍在淵陳志淵六十首展將於桃園市政府文化局二、三樓畫廊展出，"
                "展覽呈現書法藝術從古典文本走向現代空間的轉化歷程，歡迎市民大眾參觀。"
                "本次展覽分為兩大展區，呈現藝術家對在地生活與傳統文本的重新詮釋。 "
                "相關圖片 海報 上版日期：115-04-29 下版日期：115-06-14 回上一頁 回最上面"
            )
        }

        event = normalize_text(event)

        self.assertIn("書法藝術", event["clean_description"])
        self.assertNotIn("上版日期", event["clean_description"])
        self.assertNotIn("下版日期", event["clean_description"])

    def test_timed_slash_date_range_is_parsed(self):
        event = {
            "title": "夏令營",
            "clean_description": "場次: 夏令營 第一梯次 2026/07/14 09:30 ~ 2026/07/17 16:00 場 地 桃園市兒童美術館",
        }

        event = extract_dates(event)

        self.assertEqual(event["date_start"], "2026-07-14")
        self.assertEqual(event["date_end"], "2026-07-17")


if __name__ == "__main__":
    unittest.main()
