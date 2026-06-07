from django.core.management.base import BaseCommand

from events.services import backfill_activity_assets_from_images


class Command(BaseCommand):
    help = "Backfill ActivityAsset rows from Activity.image_url / ocr_image_url."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Actually create ActivityAsset rows.")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        result = backfill_activity_assets_from_images(
            limit=options["limit"] or None,
            dry_run=not options["apply"],
        )
        mode = "APPLIED" if options["apply"] else "DRY RUN"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: checked={result['checked']} created={result['created']} skipped={result['skipped']}"
            )
        )
