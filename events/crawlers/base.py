from abc import ABC, abstractmethod


class BaseCrawler(ABC):
    """Base crawler: subclasses should implement `crawl()` and return list of dicts in standard format."""

    @abstractmethod
    def crawl(self):
        """Return list of event dicts in standard format."""
        raise NotImplementedError()

    @staticmethod
    def standard_event():
        return {
            "title": "",
            "description": "",
            "raw_content": "",
            "source_agency": "",
            "source_url": "",
            "location": "",
            "district": "",
            "start_date": None,
            "end_date": None,
            "image_url": "",
            "fee_description": "",
            "registration_info": "",
        }
