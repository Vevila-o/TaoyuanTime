from abc import ABC, abstractmethod


class BaseCrawler(ABC):
    """Crawler subclasses return normalized activity dictionaries."""

    @abstractmethod
    def crawl(self):
        raise NotImplementedError

    @staticmethod
    def standard_event():
        return {
            'source_key': '',
            'source_item_id': '',
            'title': '',
            'description': '',
            'raw_content': '',
            'source_agency': '',
            'source_url': '',
            'official_detail_url': '',
            'location': '',
            'district': '',
            'start_date': None,
            'end_date': None,
            'image_url': '',
            'fee_description': '',
            'registration_info': '',
            'status': 'draft',
        }
