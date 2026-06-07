import json
import re
import time
from html import unescape
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from .base_scraper import BaseScraper


class TravelOpenApiFetcher(BaseScraper):
    BASE_URL = "https://travel.tycg.gov.tw/open-api"
    OFFICIAL_HOSTS = {
        "travel.tycg.gov.tw",
        "www.tycg.gov.tw",
        "culture.tycg.gov.tw",
        "agriculture.tycg.gov.tw",
        "youth.tycg.gov.tw",
        "edb.tycg.gov.tw",
        "www.hakka.tycg.gov.tw",
        "hakka.tycg.gov.tw",
    }
    EVENT_SOURCE_NAME = "桃園觀光導覽網 OpenAPI"

    def __init__(
        self,
        key="travel_openapi",
        name="桃園觀光導覽網 OpenAPI",
        start_url=BASE_URL,
        fetcher_type="TravelOpenApiFetcher",
        lang="zh-tw",
    ):
        super().__init__(key, name, start_url, fetcher_type)
        self.lang = lang
        self.records = {}
        self.ordered_keys = []

    def fetch_list(self):
        merged = {}
        ordered_keys = []

        for endpoint in self.endpoint_configs():
            url = self.build_api_url(endpoint)
            print(f"[{self.key}] Fetching OpenAPI endpoint: {url}")
            payload = self.fetch_json(url)
            records = self.extract_records(payload)
            print(f"[{self.key}] {endpoint['kind']} records: {len(records)}")

            for record in records:
                normalized = self.normalize_record(record, endpoint, url)
                if not normalized:
                    continue
                dedupe_key = self.dedupe_key(normalized)
                existing = merged.get(dedupe_key)
                if not existing:
                    merged[dedupe_key] = normalized
                    ordered_keys.append(dedupe_key)
                    continue
                if normalized["source_rank"] < existing["source_rank"]:
                    merged[dedupe_key] = self.merge_records(normalized, existing)
                else:
                    merged[dedupe_key] = self.merge_records(existing, normalized)

        self.write_attractions_sample()
        self.records = merged
        self.ordered_keys = sorted(ordered_keys, key=lambda key: self.record_freshness_sort_key(merged[key]))
        return {"keys": ordered_keys}

    def endpoint_configs(self):
        current_year = datetime.now().year
        return [
            {
                "kind": "calendar",
                "priority": 1,
                "path": "/{lang}/Event/Calendar",
                "params": {"year": str(current_year), "page": "1"},
            },
            {
                "kind": "calendar",
                "priority": 1,
                "path": "/{lang}/Event/Calendar",
                "params": {"year": str(current_year + 1), "page": "1"},
            },
            {
                "kind": "activity",
                "priority": 2,
                "path": "/{lang}/Event/Activity",
                "params": {},
            },
            {
                "kind": "news",
                "priority": 3,
                "path": "/{lang}/Event/News",
                "params": {"page": "1"},
            },
        ]

    def parse_list(self, page):
        if not page:
            return []
        return [f"travel_openapi://{key}" for key in self.ordered_keys]

    def record_freshness_sort_key(self, record):
        today = datetime.now().date()
        start = self.parse_api_date(record.get("Start"))
        end = self.parse_api_date(record.get("End")) or start
        start_date = datetime.strptime(start, "%Y-%m-%d").date() if start else None
        end_date = datetime.strptime(end, "%Y-%m-%d").date() if end else None
        if end_date and end_date < today:
            return (3, (today - end_date).days, record.get("Name") or "")
        if start_date and start_date <= today <= (end_date or start_date):
            return (0, 0, record.get("Name") or "")
        if start_date and start_date > today:
            return (1, (start_date - today).days, record.get("Name") or "")
        return (2, 999999, record.get("Name") or "")

    def fetch_detail(self, url):
        key = url.replace("travel_openapi://", "", 1)
        return self.records.get(key)

    def parse_detail(self, record, parent_url):
        if not record:
            return None

        title = record.get("Name") or ""
        description = self.clean_api_text(record.get("Description") or title)
        official_detail_url = self.official_detail_url(record)
        source_url = official_detail_url or self.unique_api_record_url(record, parent_url)
        warning_flags = []
        if record.get("_external_detail_url") and not self.is_official_url(official_detail_url):
            warning_flags.append("external_detail_url")

        date_start = self.parse_api_date(record.get("Start"))
        date_end = self.parse_api_date(record.get("End")) or date_start
        date_text = self.build_date_text(record.get("Start"), record.get("End"))
        location = self.location_from_record(record)
        poster_url = self.first_image_url(record)
        registration_url = self.first_registration_url(record)
        category = self.category_from_record(record)
        endpoint_kind = record.get("_endpoint_kind")

        detail = None
        if official_detail_url and (not date_start or not location or len(description) < 80):
            detail = self.fetch_official_detail(official_detail_url)
        if detail:
            if len(detail.get("description") or "") > len(description):
                description = detail["description"]
            date_text = date_text or detail.get("date_text")
            location = location or detail.get("location_text")
            registration_url = registration_url or detail.get("registration_url")

        district = record.get("District") or self.district_from_text(location)

        event = self.create_base_event(
            source_url,
            title,
            description,
            date_text=date_text,
            location_text=location,
            fee_text=record.get("Ticket") or None,
        )
        event.update(
            {
                "source_name": self.EVENT_SOURCE_NAME,
                "source_key": self.key,
                "source_url": source_url,
                "api_request_url": record.get("_request_url"),
                "official_detail_url": official_detail_url,
                "title": title,
                "description": description,
                "raw_content": description,
                "clean_description": description,
                "date_text": date_text,
                "date_start": date_start,
                "date_end": date_end,
                "time_text": self.time_text(record.get("Start"), record.get("End")),
                "location": location,
                "location_text": location,
                "district": district,
                "category": category,
                "poster_url": poster_url,
                "registration_url": registration_url,
                "fee_text": record.get("Ticket") or "未標示",
                "item_type": "activity" if endpoint_kind in {"calendar", "activity"} else "unknown",
                "content_type": "activity" if endpoint_kind in {"calendar", "activity"} else "unknown",
                "is_activity": endpoint_kind in {"calendar", "activity"},
                "is_event_candidate": endpoint_kind in {"calendar", "activity"},
                "force_activity_classification": endpoint_kind in {"calendar", "activity"},
                "event_confidence": 1.0 if endpoint_kind in {"calendar", "activity"} else 0.0,
                "travel_openapi_endpoint": endpoint_kind,
                "travel_openapi_id": record.get("Id"),
                "has_assets": bool(poster_url),
                "asset_count": 1 if poster_url else 0,
                "quality_warnings": warning_flags,
            }
        )
        if not date_start:
            event["recommendation_ready"] = False
            event["exclude_from_recommendation_reason"] = "missing_date"
        if endpoint_kind == "news":
            event["manual_review_required"] = True
            event["exclude_from_recommendation_reason"] = "filtered_news_source"

        return event

    def fetch_official_detail(self, url):
        if not self.is_official_url(url):
            return None
        request = Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "Mozilla/5.0 travel-openapi-detail/1.0",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                html = response.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            print(f"[{self.key}] Detail fallback failed for {url}: {exc}")
            return None

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer"]):
            tag.decompose()

        description = ""
        meta_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            description = self.clean_api_text(meta_desc.get("content"))
        if not description:
            content_node = soup.select_one("article, .article-content, .news-content, .detail-content, main") or soup.body
            if content_node:
                description = self.clean_api_text(content_node.get_text(" "))

        date_text = self.first_match(description, [
            r"((?:活動|展演|報名)?(?:期間|日期|時間)\s*[｜:：]\s*[^。；;\n]+)",
            r"(將於\s*[0-9]{3,4}年[0-9]{1,2}月[0-9]{1,2}日(?:至[0-9]{1,2}月[0-9]{1,2}日)?[^。；;\n]*)",
            r"(今\([0-9]{1,2}\)起至[0-9]{1,2}月[0-9]{1,2}日[^。；;\n]*)",
        ])
        location_text = self.first_match(description, [
            r"(?:活動地點|活動地址|比賽地點|展覽地點|晚會地點)\s*[｜:：]\s*([^。；;\n]+)",
            r"橫跨([^。；;\n]{2,80}(?:區域|園區|公園|操場))",
            r"在(桃園市[^。；;\n]+?)(?:登場|舉辦|辦理|展開)",
        ])

        return {
            "description": description,
            "date_text": date_text,
            "location_text": location_text,
            "registration_url": self.extract_registration_url(soup, description, url),
        }

    def write_attractions_sample(self):
        endpoint = {
            "kind": "attraction",
            "path": "/{lang}/Travel/Attraction",
            "params": {"page": "1"},
        }
        url = self.build_api_url(endpoint)
        payload = self.fetch_json(url)
        records = self.extract_records(payload)
        if not records:
            return
        import os

        output_path = os.path.join("scraping", "data", "output", "travel_attractions_sample.json")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "source": "travel_openapi",
                    "endpoint": endpoint["path"],
                    "request_url": url,
                    "sample_count": len(records[:20]),
                    "records": records[:20],
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
            f.write("\n")

    def build_api_url(self, endpoint):
        path = endpoint["path"].replace("{lang}", self.lang)
        url = f"{self.BASE_URL}{path}"
        params = endpoint.get("params") or {}
        if params:
            url = f"{url}?{urlencode(params)}"
        return url

    def fetch_json(self, url):
        time.sleep(0.5)
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 travel-openapi-fetcher/1.0",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                text = response.read().decode("utf-8-sig", errors="replace")
                return json.loads(text)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            print(f"[{self.key}] OpenAPI fetch failed for {url}: {exc}")
            return None

    def extract_records(self, payload):
        if not isinstance(payload, dict):
            return []
        infos = payload.get("Infos") or payload.get("infos")
        if isinstance(infos, dict):
            records = infos.get("Info") or infos.get("info")
            if isinstance(records, list):
                return [r for r in records if isinstance(r, dict)]
            if isinstance(records, dict):
                return [records]
        return []

    def normalize_record(self, record, endpoint, request_url):
        if not record.get("Id") and not record.get("Name"):
            return None
        normalized = dict(record)
        normalized["_endpoint_kind"] = endpoint["kind"]
        normalized["_source_rank"] = endpoint["priority"]
        normalized["_request_url"] = request_url
        normalized["source_rank"] = endpoint["priority"]
        return normalized

    def dedupe_key(self, record):
        if record.get("Id"):
            return f"id:{record['Id']}"
        title = self.compact_text(record.get("Name") or "")
        start = self.parse_api_date(record.get("Start")) or ""
        end = self.parse_api_date(record.get("End")) or ""
        return f"name-date:{title}|{start}|{end}"

    def merge_records(self, primary, secondary):
        merged = dict(primary)
        for key, value in secondary.items():
            if key.startswith("_"):
                continue
            if self.is_empty(merged.get(key)) and not self.is_empty(value):
                merged[key] = value
        if self.is_empty(merged.get("Description")) and not self.is_empty(secondary.get("Description")):
            merged["Description"] = secondary.get("Description")
        if self.is_empty(self.first_image_url(merged)) and self.first_image_url(secondary):
            merged["Image"] = secondary.get("Image")
            merged["Images"] = secondary.get("Images")
        return merged

    def is_empty(self, value):
        return value is None or value == "" or value == [] or value == {}

    def parse_api_date(self, value):
        if not value:
            return None
        match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", str(value))
        if not match:
            return None
        year, month, day = [int(part) for part in match.groups()]
        try:
            datetime(year, month, day)
        except ValueError:
            return None
        return f"{year:04d}-{month:02d}-{day:02d}"

    def build_date_text(self, start, end):
        if start and end:
            return f"{start} 至 {end}"
        return start or end or None

    def time_text(self, start, end):
        times = []
        for value in (start, end):
            match = re.search(r"\d{1,2}:\d{2}(?::\d{2})?", str(value or ""))
            if match:
                times.append(match.group(0))
        return " - ".join(times) if times else None

    def official_detail_url(self, record):
        for key in ("TYWebsite", "Website"):
            value = record.get(key)
            if not value:
                continue
            url = self.normalize_url(value)
            if self.is_official_url(url):
                record.pop("_external_detail_url", None)
                return url
        if record.get("Id"):
            return f"https://travel.tycg.gov.tw/{self.lang}/event/calendardetail/{record['Id']}"
        return record.get("_request_url")

    def unique_api_record_url(self, record, parent_url):
        record_id = record.get("Id")
        if record_id and record.get("_request_url"):
            return f"{record['_request_url']}#id={record_id}"
        return parent_url

    def normalize_url(self, value):
        url = str(value).strip()
        if not url:
            return None
        if url.startswith("//"):
            return "https:" + url
        if not url.startswith("http://") and not url.startswith("https://"):
            return "https://" + url.lstrip("/")
        return url

    def is_official_url(self, url):
        if not url:
            return False
        host = urlparse(url).netloc.lower()
        return host in self.OFFICIAL_HOSTS or host.endswith(".tycg.gov.tw")

    def location_from_record(self, record):
        if record.get("Address"):
            district = record.get("District") or ""
            return self.compact_text(f"{district}{record.get('Address')}")
        title = record.get("Name") or ""
        description = self.clean_api_text(record.get("Description") or "")
        for label in ("活動地點", "展覽地點", "晚會地點", "地點"):
            value = self.extract_labeled_value(description, label)
            if value:
                return value
        known_locations = {
            "宇內溪": "復興區宇內溪溫泉",
            "Horse來了": "中原文創園區",
            "管樂嘉年華": "桃園市",
            "珍珠海岸": "桃園濱海地區",
        }
        combined = f"{title} {description}"
        for keyword, location in known_locations.items():
            if keyword in combined:
                return location
        venue_match = re.search(
            r"(桃園市[^。；;\n]{2,60}(?:館|中心|公園|園區|廣場|球場|大池|路|街|號))",
            description,
        )
        if venue_match:
            return self.compact_text(venue_match.group(1))
        return None

    def clean_api_text(self, value):
        text = unescape(str(value or ""))
        text = text.replace("\r", " ").replace("\n", " ")
        return self.compact_text(text)

    def extract_labeled_value(self, text, label):
        pattern = rf"{re.escape(label)}\s*[｜:：]\s*(.+)"
        match = re.search(pattern, text)
        if not match:
            return None
        value = match.group(1)
        stop_patterns = [
            r"《",
            r"✨",
            r"🆓",
            r"🏮",
            r"🍵",
            r"🌱",
            r"💡",
            r"🔎",
            r"➋",
            r"活動日期\s*[｜:：]",
            r"活動期間\s*[｜:：]",
            r"活動時間\s*[｜:：]",
            r"展覽日期\s*[｜:：]",
            r"展覽時間\s*[｜:：]",
            r"燈區路線\s*[｜:：]",
            r"點燈時間\s*[｜:：]",
            r"入場方式\s*[｜:：]",
            r"團隊介紹\s*[｜:：]",
            r"交通方式\s*[｜:：]",
            r"官網\s*[｜:：]",
            r"主題活動\s*[｜:：]",
            r"邀請",
            r"，(?=邀請|感受|活動|展覽|整體)",
            r"工作，",
            r"[。；;]",
        ]
        stop_positions = []
        for stop_pattern in stop_patterns:
            stop_match = re.search(stop_pattern, value)
            if stop_match:
                stop_positions.append(stop_match.start())
        if stop_positions:
            value = value[: min(stop_positions)]
        value = self.compact_text(value)
        return value if 2 <= len(value) <= 120 else None

    def district_from_text(self, text):
        if not text:
            return None
        for district in [
            "桃園區", "中壢區", "平鎮區", "八德區", "楊梅區", "大溪區", "蘆竹區",
            "大園區", "龜山區", "新屋區", "觀音區", "復興區", "龍潭區",
        ]:
            if district in text:
                return district
        return None

    def first_image_url(self, record):
        image = record.get("Image")
        if isinstance(image, dict) and image.get("Src"):
            return image.get("Src")
        images = record.get("Images")
        if isinstance(images, dict):
            nested = images.get("Image")
            if isinstance(nested, list):
                for item in nested:
                    if isinstance(item, dict) and item.get("Src"):
                        return item.get("Src")
            if isinstance(nested, dict) and nested.get("Src"):
                return nested.get("Src")
        return None

    def first_registration_url(self, record):
        links = record.get("Links")
        if isinstance(links, dict):
            link = links.get("Link")
            if isinstance(link, list):
                for item in link:
                    if isinstance(item, dict) and item.get("Src"):
                        return item.get("Src")
            if isinstance(link, dict) and link.get("Src"):
                return link.get("Src")
        return None

    def category_from_record(self, record):
        classes = record.get("Classes")
        if isinstance(classes, dict):
            cls = classes.get("Class")
            if isinstance(cls, list):
                return "、".join(str(item) for item in cls if item)
            if cls:
                return str(cls)
        return record.get("_endpoint_kind")
