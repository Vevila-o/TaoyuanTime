import requests
from bs4 import BeautifulSoup
from .base import BaseCrawler


class TycgCrawler(BaseCrawler):
    """Simple crawler for travel.tycg.gov.tw (example). Returns list of event dicts."""

    def __init__(self, list_url='https://travel.tycg.gov.tw'):
        self.list_url = list_url

    def crawl(self):
        events = []
        try:
            r = requests.get(self.list_url, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'lxml')
            # naive example: find links with class 'event'
            for a in soup.find_all('a', href=True)[:10]:
                title = a.get_text(strip=True)
                href = a['href']
                url = href if href.startswith('http') else self.list_url.rstrip('/') + '/' + href.lstrip('/')
                e = self.standard_event()
                e.update({'title': title or '活動', 'source_agency': '桃園觀光導覽網', 'source_url': url})
                events.append(e)
        except Exception:
            pass
        return events
