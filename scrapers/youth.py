from urllib.parse import urljoin
from .base_scraper import BaseScraper

class YouthScraper(BaseScraper):
    def __init__(self, key="youth", name="桃園市政府青年事務局", start_url="https://youth.tycg.gov.tw/News.aspx?n=5622&sms=11012", fetcher_type="Fetcher"):
        super().__init__(key, name, start_url, fetcher_type)
        self.base_domain = "https://youth.tycg.gov.tw"

    def parse_list(self, page):
        if not page: return []
        urls = []
        for link in page.css("a"):
            href = link.css("::attr(href)").get() or ""
            if "News_Content.aspx" in href:
                urls.append(urljoin(self.base_domain, href))
        return list(dict.fromkeys(urls))

    def parse_detail(self, page, parent_url):
        return self.parse_aspx_detail(page, parent_url)
