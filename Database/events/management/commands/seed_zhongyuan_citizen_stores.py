from django.core.management.base import BaseCommand

from events.citizen_stores import seed_zhongyuan_citizen_stores


class Command(BaseCommand):
    help = "Seed the fixed Zhongyuan citizen-card partner stores used by the LINE demo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the fixed stores into the database. Without this flag, runs as dry-run.",
        )

    def handle(self, *args, **options):
        dry_run = not options["apply"]
        results = seed_zhongyuan_citizen_stores(dry_run=dry_run)
        created = sum(1 for item in results if item["created"])
        updated = sum(1 for item in results if item["updated"])
        mode = "DRY RUN" if dry_run else "APPLY"
        self.stdout.write(f"{mode}: Zhongyuan citizen-card stores created={created} updated={updated}")
        for item in results:
            action = "create" if item["created"] else "update"
            self.stdout.write(f"- {action}: {item['name']}")
