from urllib.parse import urljoin
import json
import re
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper

class TravelTaoyuanScraper(BaseScraper):
    def __init__(self, key="travel", name="桃園觀光導覽網", start_url="https://travel.tycg.gov.tw/zh-tw/event", fetcher_type="DynamicFetcher"):
        super().__init__(key, name, start_url, fetcher_type)
        self.base_domain = "https://travel.tycg.gov.tw"

    def fetch_list(self):
        print(f"[{self.key}] Fetching list page with dynamic wait...")
        try:
            # Tell DynamicFetcher to wait for the event cards to render
            # Scrapling passes kwargs to Playwright page.goto or similar
            return self.fetcher.fetch(self.start_url, wait_selector=".card-list, .event-list, a[href*='/event/news/']")
        except Exception as e:
            print(f"[{self.key}] Dynamic fetch failed or timeout: {e}")
            raise e

    def parse_list(self, page):
        """Parse the event list page to extract detail URLs."""
        urls = []
        # Try to find links inside typical event wrappers
        links = page.css("a[href*='/event/news/']")
        if not links:
            # Fallback to all links
            links = page.css("a")
            
        for link in links:
            href = link.css("::attr(href)").get() or ""
            if "/event/news/" in href:
                urls.append(urljoin(self.base_domain, href))
                
        # Deduplicate list URLs
        return list(dict.fromkeys(urls))

    def parse_detail(self, page, parent_url):
        if not page: return None

        html = self.page_html(page)
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer"]):
            tag.decompose()

        title = ""
        meta_title = soup.find("meta", property="og:title")
        if meta_title:
            title = self.compact_text(meta_title.get("content"))
        if not title and soup.title:
            title = self.compact_text(soup.title.get_text(" "))
            if "|" in title:
                title = title.split("|")[0].strip()

        description = ""
        json_ld = soup.find("script", type="application/ld+json")
        if json_ld and json_ld.string:
            try:
                payload = json.loads(json_ld.string)
                description = self.compact_text(payload.get("articleBody") or payload.get("description"))
            except Exception:
                description = ""

        if not description:
            meta_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                description = self.compact_text(meta_desc.get("content"))

        if not description:
            content_node = soup.select_one("article, .article-content, .news-content, .detail-content, main")
            if content_node:
                description = self.compact_text(content_node.get_text(" "))

        date_text = self.first_match(description, [
            r"((?:活動|展演|施工|報名)?(?:期間|日期|時間)\s*[｜:：]\s*[^。；;\n]+)",
            r"(將於\s*[0-9]{3,4}年[0-9]{1,2}月[0-9]{1,2}日(?:至[0-9]{1,2}月[0-9]{1,2}日)?[^。；;\n]*)",
            r"(於\s*[0-9]{3,4}年[0-9]{1,2}月[0-9]{1,2}日(?:至[0-9]{1,2}月[0-9]{1,2}日)?[^。；;\n]*)",
        ])
        published_date_text = self.first_match(self.compact_text(soup.get_text(" ")), [
            r"(?:發佈日|更新日)\s*[：:]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
        ])
        location_text = self.first_match(description, [
            r"(?:活動地點|活動地址|比賽地點|登場|辦理|施工範圍)\s*[｜:：]?\s*([^。；;\n]+)",
            r"在(桃園市[^。；;\n]+?)(?:登場|舉辦|辦理|展開)",
        ])

        event = self.create_base_event(parent_url, title, description, date_text=date_text)
        event["location_text"] = location_text
        event["published_date_text"] = published_date_text
        event["raw_content"] = description
        event["official_detail_url"] = parent_url
        
        if html:
            event["raw_html_path"] = self.save_raw_html(parent_url, html)
                
        return event
