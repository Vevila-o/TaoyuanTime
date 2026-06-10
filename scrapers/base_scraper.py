import os
import time
import hashlib
import re
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from scrapling import Fetcher, DynamicFetcher
import json

class BaseScraper:
    def __init__(self, key, name, start_url, fetcher_type="Fetcher"):
        self.key = key
        self.name = name
        self.start_url = start_url
        self.fetcher_type = fetcher_type
        
        # Initialize the appropriate fetcher
        if self.fetcher_type == "DynamicFetcher":
            self.fetcher = DynamicFetcher()
        else:
            self.fetcher = Fetcher()

    def fetch(self, url):
        """Fetches the page content with some basic delay and error handling."""
        # Simple logging
        print(f"[{self.key}] Fetching: {url}")
        
        # Basic delay based on fetcher type
        delay = 3.0 if self.fetcher_type == "DynamicFetcher" else 1.0
        time.sleep(delay)
        
        try:
            if self.fetcher_type == "DynamicFetcher":
                return self.fetcher.fetch(url)
            else:
                return self.fetcher.get(url)
        except Exception as e:
            print(f"[{self.key}] Fetch failed for {url}: {e}")
            return None

    def fetch_list(self):
        """Fetches the main listing page."""
        return self.fetch(self.start_url)

    def parse_list(self, page):
        """
        Parses the listing page and returns a list of detail URLs.
        Must be implemented by subclasses.
        """
        raise NotImplementedError

    def fetch_detail(self, url):
        """Fetches the detail page."""
        return self.fetch(url)

    def save_raw_html(self, url, html_content):
        """Saves the raw HTML for debugging and asset extraction."""
        if not html_content:
            return None
        
        hash_str = hashlib.md5(url.encode('utf-8')).hexdigest()[:8]
        filename = f"{self.key}_{hash_str}.html"
        filepath = os.path.join("scraping", "data", "raw_html", filename)
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        return filepath

    def page_html(self, page):
        if not page:
            return ""
        for attr in ("body", "text", "html"):
            value = getattr(page, attr, None)
            if callable(value):
                try:
                    value = value()
                except Exception:
                    value = None
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="ignore")
            if isinstance(value, str) and value.strip():
                return value
        return ""

    def compact_text(self, text):
        return re.sub(r"\s+", " ", text or "").strip()

    def first_match(self, text, patterns):
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                return self.compact_text(match.group(1))
        return None

    def extract_html_metadata(self, soup):
        """
        從完整 HTML 中提取 head metadata 和 structured data。
        回傳 dict，供後續 pipeline 使用。
        不修改 soup 本身。
        """
        metadata = {
            "page_title": "",
            "meta_description": "",
            "meta_keywords": "",
            "og_title": "",
            "og_description": "",
            "og_type": "",
            "og_site_name": "",
            "structured_data": [],       # JSON-LD 物件列表
            "all_meta_tags": {},         # name/property -> content
        }

        # <title>
        if soup.title:
            metadata["page_title"] = self.compact_text(soup.title.get_text(" "))

        # <meta> 標籤 — 全部收集
        for meta in soup.find_all("meta"):
            name = meta.get("name") or meta.get("property") or ""
            content = meta.get("content") or ""
            if name and content:
                metadata["all_meta_tags"][name.lower()] = content
                if name.lower() == "description":
                    metadata["meta_description"] = self.compact_text(content)
                elif name.lower() == "keywords":
                    metadata["meta_keywords"] = self.compact_text(content)
                elif name.lower() == "og:title":
                    metadata["og_title"] = self.compact_text(content)
                elif name.lower() == "og:description":
                    metadata["og_description"] = self.compact_text(content)
                elif name.lower() == "og:type":
                    metadata["og_type"] = self.compact_text(content)
                elif name.lower() == "og:site_name":
                    metadata["og_site_name"] = self.compact_text(content)

        # JSON-LD structured data
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                if isinstance(data, list):
                    metadata["structured_data"].extend(data)
                else:
                    metadata["structured_data"].append(data)
            except (json.JSONDecodeError, TypeError):
                pass

        return metadata

    def parse_aspx_detail(self, page, parent_url):
        """
        Shared parser for TYCG News_Content.aspx pages.
        These pages expose useful labels in the body; extracting those labels
        before fallback text search prevents publication dates and random
        sentence fragments from becoming activity dates/locations.
        """
        if not page:
            return None

        html = self.page_html(page)
        soup = BeautifulSoup(html, "html.parser")
        html_metadata = self.extract_html_metadata(soup)
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()

        title = ""
        title_node = soup.select_one("h1, .title, .page-title")
        if title_node:
            title = self.compact_text(title_node.get_text(" "))
        if not title and soup.title:
            title = self.compact_text(soup.title.get_text(" "))
            if "|" in title:
                title = title.split("|")[0].strip()

        content_node = soup.select_one(".data_midelle_news_box01, .area-essay, .content, main, article") or soup.body
        description = self.compact_text(content_node.get_text(" ")) if content_node else ""

        activity_date_text = self.first_match(description, [
            r"(活動日期\s*[\(（]起[\)）]\s*[:：]\s*[0-9./\-年月日]+\s*活動日期\s*[\(（]迄[\)）]\s*[:：]\s*[0-9./\-年月日]+)",
            r"(活動時間\s*[:：]\s*[^。；;\n]+)",
            r"(比賽時間\s*[:：]\s*[^。；;\n]+)",
            r"(展覽日期\s*[:：]\s*[^。；;\n]+)",
            r"(報名期間\s*[:：]\s*[^。；;\n]+)",
        ])
        published_date_text = self.first_match(description, [
            r"(?:發布日期|上版日期)\s*[:：]\s*([0-9./\-年月日]+)",
        ])
        location_text = self.first_match(description, [
            r"(?:活動地址|活動地點|比賽地點|展覽地點|辦理地點|上課地點|施工範圍)\s*[:：]\s*([^。；;\n]+?)(?=\s*(?:發布單位|主辦單位|協辦單位|活動日期|報名|聯絡人|資料提供|$))",
        ])
        organizer = self.first_match(description, [
            r"(?:主辦單位|發布單位)\s*[:：]\s*([^。；;\n]+?)(?=\s*(?:協辦單位|活動日期|活動地址|聯絡人|資料提供|$))",
        ])
        fee_text = self.first_match(description, [
            r"(?:費用|票價|門票|報名費)\s*[:：]\s*([^。；;\n]+)",
        ])
        registration_url = self.extract_registration_url(soup, description, parent_url)

        event = self.create_base_event(
            parent_url,
            title,
            description,
            date_text=activity_date_text,
            location_text=location_text,
            fee_text=fee_text,
        )
        event["raw_content"] = description
        event["published_date_text"] = published_date_text
        event["organizer"] = organizer
        event["official_detail_url"] = parent_url
        if registration_url:
            event["registration_url"] = registration_url
            event["registration_method"] = "online"
        event["html_metadata"] = html_metadata

        if html:
            event["raw_html_path"] = self.save_raw_html(parent_url, html)
        return event

    def parse_generic_html_detail(self, page, parent_url, fallback_title=None, fallback_description=None):
        """
        Generic detail parser for official pages that do not use the ASPX
        template. It intentionally extracts only broad fields and leaves
        activity/date/location decisions to the existing pipeline.
        """
        if not page:
            return None

        html = self.page_html(page)
        soup = BeautifulSoup(html, "html.parser")
        html_metadata = self.extract_html_metadata(soup)
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
            tag.decompose()

        title = self.compact_text(fallback_title)
        if not title:
            meta_title = soup.find("meta", property="og:title")
            if meta_title:
                title = self.compact_text(meta_title.get("content"))
        if not title:
            title_node = soup.select_one("h1, .title, .page-title, .article-title")
            if title_node:
                title = self.compact_text(title_node.get_text(" "))
        if not title and soup.title:
            title = self.compact_text(soup.title.get_text(" "))
            if "|" in title:
                title = title.split("|")[0].strip()

        description = self.compact_text(fallback_description)
        if not description:
            meta_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                description = self.compact_text(meta_desc.get("content"))
        if not description:
            content_node = soup.select_one(
                "article, main, .article-content, .news-content, .detail-content, .content, .page-content"
            ) or soup.body
            description = self.compact_text(content_node.get_text(" ")) if content_node else ""

        full_text = self.compact_text(soup.get_text(" "))
        date_text = self.first_match(description, [
            r"((?:活動|展演|展覽|報名|比賽)?(?:期間|日期|時間)\s*[｜|:：]\s*[^。；;\n]+)",
            r"(將於\s*[0-9]{3,4}年[0-9]{1,2}月[0-9]{1,2}日(?:至[0-9]{1,2}月[0-9]{1,2}日)?[^。；;\n]*)",
            r"(於\s*[0-9]{3,4}年[0-9]{1,2}月[0-9]{1,2}日(?:至[0-9]{1,2}月[0-9]{1,2}日)?[^。；;\n]*)",
        ])
        published_date_text = self.first_match(full_text, [
            r"(?:發布日期|上版日期|發佈日|更新日)\s*[:：]\s*([0-9./\-年月日]+)",
        ])
        location_text = self.first_match(description, [
            r"(?:活動地址|活動地點|比賽地點|展覽地點|辦理地點|上課地點)\s*[:：]\s*([^。；;\n]+)",
            r"場\s*地\s*([^。；;\n]+?)(?:主辦單位|聯絡資訊|活動內容|$)",
            r"在(桃園市[^。；;\n]+?)(?:登場|舉辦|辦理|展開)",
        ])
        fee_text = self.first_match(description, [
            r"(?:費用|票價|門票|報名費)\s*[:：]\s*([^。；;\n]+)",
        ])
        registration_url = self.extract_registration_url(soup, description, parent_url)

        event = self.create_base_event(
            parent_url,
            title,
            description,
            date_text=date_text,
            location_text=location_text,
            fee_text=fee_text,
        )
        event["raw_content"] = description
        event["published_date_text"] = published_date_text
        event["official_detail_url"] = parent_url
        if registration_url:
            event["registration_url"] = registration_url
            event["registration_method"] = "online"
        event["html_metadata"] = html_metadata
        if html:
            event["raw_html_path"] = self.save_raw_html(parent_url, html)
        return event

    def extract_registration_url(self, soup, text, base_url):
        hints = (
            "網路報名", "報名連結", "Accupass", "Google 表單", "報名網址", "需事先報名",
            "立即報名", "線上報名", "報名期間", "報名表單", "名額限制", "額滿",
            "KKTIX", "BeClass",
        )
        host_hints = ("accupass.com", "forms.gle", "docs.google.com/forms", "kktix.com", "beclass.com")
        common_registration_page_hints = ("ActiveList.aspx", "sms=20299")
        if soup:
            soup = BeautifulSoup(str(soup), "html.parser")
            for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer", "aside"]):
                tag.decompose()
            content_root = (
                soup.select_one(".page-content, main, article, [role=main], #content, .content")
                or soup.body
                or soup
            )
            for link in content_root.select("a[href]"):
                href = link.get("href") or ""
                label = self.compact_text(link.get_text(" "))
                url = urljoin(base_url, href)
                if any(hint.lower() in url.lower() for hint in common_registration_page_hints):
                    continue
                if any(hint.lower() in url.lower() for hint in host_hints) or any(hint in label for hint in hints):
                    return url
        for match in re.finditer(r"https?://[^\s<>\"）)]+", text or ""):
            url = match.group(0).rstrip("，。；;、")
            context = text[max(0, match.start() - 30): match.end() + 30]
            if any(hint.lower() in url.lower() for hint in common_registration_page_hints):
                continue
            if any(hint.lower() in url.lower() for hint in host_hints) or any(hint in context for hint in hints):
                return url
        return None

    def create_base_event(self, url, title, description, date_text=None, location_text=None, fee_text=None):
        """Creates the initial dictionary structure that will pass through the pipeline."""
        return {
            "id": None,
            "source_name": self.name,
            "source_key": self.key,
            "source_url": url,
            "title": title,
            "official_detail_url": url,
            
            # Classification
            "status": "active",
            "content_type": "unknown",
            "item_type": "unknown",
            "is_activity": False,
            "is_public_item": False,
            "is_event_candidate": False,
            "event_confidence": 0.0,
            
            # Dates
            "date_text": date_text,
            "date_start": None,
            "date_end": None,
            "time_text": None,
            "published_date_text": None,
            "date_parse_status": "unknown",
            
            # Location
            "location_text": location_text, # intermediate field
            "location": None,
            "district": None,
            "location_parse_status": "unknown",
            
            # Details
            "organizer": None,
            "category": None,
            "description": description,
            "raw_content": description,
            "clean_description": None,
            
            # Registration
            "registration_method": None,
            "registration_url": None,
            "registration_parse_status": "unknown",
            "registration_evidence_text": "",
            
            # Fee
            "fee_raw_text": fee_text, # intermediate field
            "fee_type": "unknown",
            "fee_text": "未標示",
            "fee_evidence_text": "",
            "is_free": None,
            "fee_parse_status": "unknown",
            
            # Assets
            "poster_url": None,
            "poster_local_path": None,
            "has_assets": False,
            "asset_count": 0,
            
            # Quality
            "quality_score": 0,
            "quality_level": "unknown",
            "quality_warnings": [],
            "recommendation_ready": False,
            "exclude_from_recommendation_reason": None,
            
            # Meta
            "html_metadata": None,
            "scraped_at": datetime.now().isoformat(),
            "content_hash": None,
            "raw_html_path": None,
            "parse_warnings": []
        }

    def parse_detail(self, page, parent_url):
        """
        Parses the detail page and returns an event dict.
        Must be implemented by subclasses.
        """
        raise NotImplementedError
