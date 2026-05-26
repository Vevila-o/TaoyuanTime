import requests
from bs4 import BeautifulSoup
from .base import BaseCrawler


class CultureCrawler(BaseCrawler):
    def __init__(self, list_url='https://culture.tycg.gov.tw'):
        self.list_url = list_url

    def crawl(self):
        events = []
        try:
            r = requests.get(self.list_url, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'lxml')
            for li in soup.find_all('li')[:10]:
                title = li.get_text(strip=True)
                url = self.list_url
                e = self.standard_event()
                e.update({'title': title or '文化活動', 'source_agency': '文化局', 'source_url': url})
                events.append(e)
        except Exception:
            pass
        return events
