import requests
from bs4 import BeautifulSoup
from .base import BaseCrawler


class LibraryCrawler(BaseCrawler):
    def __init__(self, list_url='https://www.typl.gov.tw'):
        self.list_url = list_url

    def crawl(self):
        events = []
        try:
            r = requests.get(self.list_url, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'lxml')
            for a in soup.find_all('a', href=True)[:10]:
                title = a.get_text(strip=True)
                url = a['href'] if a['href'].startswith('http') else self.list_url.rstrip('/') + '/' + a['href'].lstrip('/')
                e = self.standard_event()
                e.update({'title': title or '圖書館活動', 'source_agency': '桃園市立圖書館', 'source_url': url})
                events.append(e)
        except Exception:
            pass
        return events
