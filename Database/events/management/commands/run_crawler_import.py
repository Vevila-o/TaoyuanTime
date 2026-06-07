import importlib

from django.core.management.base import BaseCommand, CommandError

from events.crawlers.importer import import_activities_from_crawler


class Command(BaseCommand):
    help = 'Run a crawler class and upsert returned activities into events.Activity.'

    def add_arguments(self, parser):
        parser.add_argument('crawler_class', help='Python path, for example events.crawlers.my_source.MyCrawler')
        parser.add_argument('--source-name', default='')
        parser.add_argument('--activate', action='store_true')

    def handle(self, *args, **options):
        crawler_class = load_crawler_class(options['crawler_class'])
        crawler = crawler_class()
        counts = import_activities_from_crawler(
            crawler,
            source_name=options['source_name'],
            activate=options['activate'],
        )
        self.stdout.write(self.style.SUCCESS(
            f"Done. created={counts['created']}, updated={counts['updated']}, "
            f"skipped={counts['skipped']}, failed={counts['failed']}"
        ))


def load_crawler_class(path):
    module_name, sep, class_name = path.rpartition('.')
    if not sep:
        raise CommandError('crawler_class must be a full Python path like package.module.ClassName')
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise CommandError(f'Cannot import module {module_name}: {exc}') from exc
    try:
        return getattr(module, class_name)
    except AttributeError as exc:
        raise CommandError(f'Module {module_name} has no class {class_name}') from exc
