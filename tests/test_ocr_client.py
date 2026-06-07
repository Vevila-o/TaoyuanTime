import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pipeline.ocr_client import OcrConfig, build_ocr_payload, call_ocr, encode_image_data_url


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"ocr_text":"活動時間 5/31","ocr_summary":"活動海報",'
                            '"confidence":0.91,"warnings":[]}'
                        )
                    }
                }
            ]
        }


class FakeSession:
    def __init__(self):
        self.payload = None

    def post(self, url, *, json, headers, timeout):
        self.payload = json
        return FakeResponse()


class BrokenJsonResponse(FakeResponse):
    def json(self):
        return {
            "choices": [
                {"message": {"content": "活動名稱：測試活動\n時間：5/31"}}
            ]
        }


class BrokenJsonSession(FakeSession):
    def post(self, url, *, json, headers, timeout):
        self.payload = json
        return BrokenJsonResponse()


class OcrClientTests(unittest.TestCase):
    def test_encode_image_data_url_uses_base64_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "poster.jpg"
            Image.new("RGB", (320, 240), "white").save(image_path)

            data_url = encode_image_data_url(image_path)

        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))

    def test_call_ocr_uses_mixed_content_and_parses_response(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "poster.png"
            Image.new("RGB", (320, 240), "white").save(image_path)
            session = FakeSession()
            config = OcrConfig(
                base_url="http://ocr.example/v1",
                api_key="test",
                model="qwen",
                timeout_ms=30000,
            )

            result = call_ocr(image_path, session=session, config=config)

        content = session.payload["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[1]["type"], "image_url")
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(result["ocr_text"], "活動時間 5/31")
        self.assertEqual(result["ocr_summary"], "活動海報")
        self.assertEqual(result["ocr_confidence"], 0.91)

    def test_build_ocr_payload_defaults_to_json_object_response(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "poster.png"
            Image.new("RGB", (320, 240), "white").save(image_path)
            config = OcrConfig(
                base_url="http://ocr.example/v1",
                api_key="test",
                model="qwen",
                timeout_ms=30000,
            )

            payload = build_ocr_payload(image_path, config=config)

        self.assertEqual(payload["model"], "qwen")
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_call_ocr_falls_back_to_raw_text_when_json_is_broken(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "poster.png"
            Image.new("RGB", (320, 240), "white").save(image_path)
            config = OcrConfig(
                base_url="http://ocr.example/v1",
                api_key="test",
                model="qwen",
                timeout_ms=30000,
            )

            result = call_ocr(image_path, session=BrokenJsonSession(), config=config)

        self.assertIn("活動名稱", result["ocr_text"])
        self.assertEqual(result["ocr_warnings"], ["ocr_response_not_json"])


if __name__ == "__main__":
    unittest.main()
