import hashlib
import json
import re
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper


URL_KEYWORDS = ("url", "link", "href", "網址", "連結")
TITLE_KEYWORDS = ("title", "name", "subject", "標題", "名稱")
DATE_KEYWORDS = ("pubdate", "published", "date", "上版日期", "發布日期")
DESCRIPTION_KEYWORDS = ("description", "summary", "content", "內容", "說明")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _local_name(tag):
    return str(tag or "").split("}", 1)[-1].lower()


def _compact(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _looks_like_url(value):
    text = str(value or "").strip()
    return text.startswith("http://") or text.startswith("https://") or "News_Content.aspx" in text


def _fetch_with_requests(source_key, url):
    print(f"[{source_key}] Fetching: {url}")
    session = requests.Session()
    session.trust_env = False
    response = session.get(
        url,
        timeout=30,
        verify=False,
        headers={
            "User-Agent": "Mozilla/5.0 TaoyuanActivityCrawler/1.0",
            "Accept": "application/rss+xml, application/xml, text/xml, text/html, application/json, */*",
        },
    )
    response.raise_for_status()
    if not response.encoding or response.encoding.lower() in {"iso-8859-1", "windows-1252"}:
        response.encoding = response.apparent_encoding or "utf-8-sig"
    if response.content.startswith(b"\xef\xbb\xbf"):
        response.encoding = "utf-8-sig"
    return SimpleNamespace(body=response.text)


class RssOpenDataScraper(BaseScraper):
    def __init__(self, key, name, start_url, fetcher_type="RssOpenDataFetcher"):
        super().__init__(key, name, start_url, fetcher_type)
        self.base_domain = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}"
        self.feed_items_by_url = {}
        self.parse_warnings = []

    def fetch(self, url):
        return _fetch_with_requests(self.key, url)

    def fetch_list(self):
        try:
            return self.fetch(self.start_url)
        except Exception as exc:
            self.parse_warnings.append({"warning": "rss_list_fetch_failed", "error": str(exc)})
            return SimpleNamespace(body="")

    def parse_list(self, page):
        self.feed_items_by_url = {}
        self.parse_warnings = list(self.parse_warnings)
        raw = self.page_html(page)
        if not raw:
            return []
        text = raw.lstrip("\ufeff").strip()
        items = []
        if text.startswith("{") or text.startswith("["):
            items = self._parse_json_items(text)
        else:
            items = self._parse_xml_items(text)

        urls = []
        for item in items:
            url = item.get("link")
            if not url and _looks_like_url(item.get("guid")):
                url = item.get("guid")
            if not url:
                self.parse_warnings.append({"warning": "rss_no_detail_url", "title": item.get("title")})
                continue
            url = urljoin(self.start_url, url)
            urls.append(url)
            item["link"] = url
            self.feed_items_by_url[url] = item
        return list(dict.fromkeys(urls))

    def parse_detail(self, page, parent_url):
        item = self.feed_items_by_url.get(parent_url, {})
        if "News_Content.aspx" in parent_url or "Active_Content.aspx" in parent_url or "Activity_Content.aspx" in parent_url:
            event = self.parse_aspx_detail(page, parent_url)
        else:
            event = self.parse_generic_html_detail(
                page,
                parent_url,
                fallback_title=item.get("title"),
                fallback_description=item.get("description"),
            )
        if not event:
            return None
        self._apply_feed_metadata(event, item, parent_url)
        return event

    def _parse_xml_items(self, text):
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            soup = BeautifulSoup(text, "html.parser")
            links = []
            for link in soup.select("a[href]"):
                href = link.get("href") or ""
                if href:
                    links.append({
                        "title": _compact(link.get_text(" ")),
                        "link": urljoin(self.start_url, href),
                    })
            return links

        parsed = []
        for node in root.iter():
            name = _local_name(node.tag)
            if name not in {"item", "entry"}:
                continue
            parsed.append(self._xml_item_to_dict(node))
        return parsed

    def _xml_item_to_dict(self, node):
        item = {
            "title": "",
            "link": "",
            "guid": "",
            "pubDate": "",
            "description": "",
        }
        for child in list(node):
            name = _local_name(child.tag)
            text = _compact("".join(child.itertext()))
            if name == "title":
                item["title"] = text
            elif name == "link":
                item["link"] = child.attrib.get("href") or text
            elif name in {"guid", "id"}:
                item["guid"] = text
            elif name in {"pubdate", "published", "updated"}:
                item["pubDate"] = text
            elif name in {"description", "summary", "content"}:
                item["description"] = text
        return item

    def _parse_json_items(self, text):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            self.parse_warnings.append({"warning": "opendata_json_parse_failed"})
            return []
        rows = []
        self._collect_json_rows(payload, rows)
        return rows

    def _collect_json_rows(self, value, rows):
        if isinstance(value, list):
            for item in value:
                self._collect_json_rows(item, rows)
            return
        if not isinstance(value, dict):
            return

        flat = {str(k).lower(): v for k, v in value.items()}
        link = self._first_matching_value(flat, URL_KEYWORDS, must_look_like_url=True)
        if link:
            rows.append({
                "title": self._first_matching_value(flat, TITLE_KEYWORDS) or "",
                "link": link,
                "guid": str(value.get("guid") or value.get("id") or link),
                "pubDate": self._first_matching_value(flat, DATE_KEYWORDS) or "",
                "description": self._first_matching_value(flat, DESCRIPTION_KEYWORDS) or "",
            })
            return

        for child in value.values():
            self._collect_json_rows(child, rows)

    def _first_matching_value(self, flat, keywords, must_look_like_url=False):
        for key, value in flat.items():
            if any(keyword.lower() in key for keyword in keywords):
                if value in (None, "", [], {}):
                    continue
                if isinstance(value, (list, dict)):
                    continue
                text = str(value).strip()
                if must_look_like_url and not _looks_like_url(text):
                    continue
                return text
        return None

    def _apply_feed_metadata(self, event, item, parent_url):
        guid = item.get("guid") or parent_url
        event["source_item_id"] = hashlib.md5(str(guid).encode("utf-8")).hexdigest()[:12]
        event["rss_url"] = self.start_url
        event["rss_published_at"] = item.get("pubDate") or ""
        event["rss_summary"] = item.get("description") or ""
        event["raw_feed_item"] = json.dumps(item, ensure_ascii=False)
        if item.get("pubDate") and not event.get("published_date_text"):
            event["published_date_text"] = item.get("pubDate")
        if item.get("description"):
            event.setdefault("parse_warnings", []).append("rss_summary_used_for_trace")
        return event


class HtmlListScraper(BaseScraper):
    def __init__(self, key, name, start_url, fetcher_type="HtmlListFetcher"):
        super().__init__(key, name, start_url, fetcher_type)
        parsed = urlparse(start_url)
        self.base_domain = f"{parsed.scheme}://{parsed.netloc}"
        self.start_path = parsed.path
        self.link_items_by_url = {}

    def fetch(self, url):
        return _fetch_with_requests(self.key, url)

    def fetch_list(self):
        try:
            return self.fetch(self.start_url)
        except Exception:
            return SimpleNamespace(body="")

    def parse_list(self, page):
        html = self.page_html(page)
        if not html:
            return []
        self.link_items_by_url = {}
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        for link in soup.select("a[href]"):
            href = (link.get("href") or "").strip()
            if not href or href.startswith("#") or href.lower().startswith(("javascript:", "mailto:", "tel:")):
                continue
            url = urljoin(self.start_url, href)
            parsed = urlparse(url)
            if not self._allowed_detail_host(parsed.netloc.lower()):
                continue
            path = parsed.path.lower()
            if self._is_likely_detail_path(path):
                urls.append(url)
                self.link_items_by_url[url] = {
                    "title": self._clean_link_title(_compact(link.get_text(" "))),
                    "description": _compact(link.get_text(" ")),
                }
        return list(dict.fromkeys(urls))

    def parse_detail(self, page, parent_url):
        if "News_Content.aspx" in parent_url or "Active_Content.aspx" in parent_url or "Activity_Content.aspx" in parent_url:
            return self.parse_aspx_detail(page, parent_url)
        item = self.link_items_by_url.get(parent_url, {})
        return self.parse_generic_html_detail(
            page,
            parent_url,
            fallback_title=item.get("title"),
        )

    def _allowed_detail_host(self, host):
        if host == urlparse(self.base_domain).netloc.lower():
            return True
        return self.key == "tmofa_events" and host == "event.culture.tw"

    def _clean_link_title(self, label):
        text = _compact(label)
        text = re.sub(r"\s*\d{4}/\d{1,2}/\d{1,2}.*$", "", text).strip()
        text = re.sub(r"\s*地點.*$", "", text).strip()
        return text or label

    def _is_likely_detail_path(self, path):
        if self.key == "tmofa_events":
            if not (
                re.search(r"/ch/events/current-events/\d+$", path.rstrip("/"))
                or path.rstrip("/") == "/mocweb/reg/tmofa/detail.init.ctr"
            ):
                return False
            return True
        elif self.key == "tmofa_exhibitions":
            if not re.search(r"/ch/exhibitions/current-exhibitions/\d+$", path.rstrip("/")):
                return False
            return True
        elif self.key == "wem_news_photo":
            return "news_photo_content.aspx" in path or "photo_news_content_museums.aspx" in path

        listing_paths = (
            "current-events",
            "past-events",
            "upcoming-events",
            "current-exhibitions",
            "past-exhibitions",
            "upcoming-exhibitions",
            "online-panoramic-exhibitions",
        )
        if any(path.rstrip("/").endswith(f"/{listing}") for listing in listing_paths):
            return False
        tokens = (
            "news_content",
            "active_content",
            "activity_content",
            "news_photo",
            "event",
            "events",
            "exhibition",
            "exhibitions",
            "activity",
        )
        if any(token in path for token in ("open-call", "online-art", "popular-events")):
            return False
        return any(token in path for token in tokens) and path != self.start_path.lower()
