from django.core.management.base import BaseCommand
from events.crawlers.tycg import TycgCrawler
from events.crawlers.culture import CultureCrawler
from events.crawlers.library import LibraryCrawler
from events.crawlers.importer import import_activities_from_crawler


class Command(BaseCommand):
    help = 'Run example crawlers and import activities (non-blocking)'

    def handle(self, *args, **options):
        crawlers = [
            (TycgCrawler(), '觀光導覽網'),
            (CultureCrawler(), '文化局'),
            (LibraryCrawler(), '圖書館'),
        ]
        for crawler, name in crawlers:
            try:
                res = import_activities_from_crawler(crawler, source_name=name)
                self.stdout.write(self.style.SUCCESS(f'Crawler {name}: created={res.get("created")}, skipped={res.get("skipped")}'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'Crawler {name} failed: {e}'))
