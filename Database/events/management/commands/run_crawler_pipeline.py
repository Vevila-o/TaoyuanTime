import os
import sys
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the integrated crawler pipeline and optionally import its output into events.Activity."

    def add_arguments(self, parser):
        parser.add_argument("--mode", default="reliability_v3", choices=["probe_1hour", "reliability_v3", "custom"])
        parser.add_argument("--source", type=str, help="Run a specific source key from config/sources.yaml.")
        parser.add_argument("--primary-limit", type=int, default=1)
        parser.add_argument("--secondary-limit", type=int, default=1)
        parser.add_argument("--max-runtime", type=int, default=150, help="Max crawler runtime in minutes.")
        parser.add_argument("--resume", action="store_true")
        parser.add_argument("--no-assets", action="store_true")
        parser.add_argument("--ocr", action="store_true")
        parser.add_argument("--ocr-limit", type=int, default=0)
        parser.add_argument("--skip-dynamic", action="store_true")
        parser.add_argument("--exclude-source", action="append", default=[])
        parser.add_argument("--no-import", action="store_true", help="Only write crawler JSON/SQLite outputs.")
        parser.add_argument("--activate", action="store_true", help="Import output as active activities.")
        parser.add_argument(
            "--import-input",
            default="data/output/activities_all.json",
            help="Crawler output JSON relative to TaoyuanTime/scraping after a successful run.",
        )

    def handle(self, *args, **options):
        project_root = Path(settings.BASE_DIR)
        scraping_root = project_root / "scraping"
        previous_cwd = Path.cwd()
        previous_argv = sys.argv[:]
        try:
            os.chdir(project_root)
            for path in (str(scraping_root), str(project_root)):
                if path not in sys.path:
                    sys.path.insert(0, path)
            from crawler_main import main as crawler_main

            crawler_args = [
                "crawler_main.py",
                "--mode", options["mode"],
                "--primary-limit", str(options["primary_limit"]),
                "--secondary-limit", str(options["secondary_limit"]),
                "--max-runtime", str(options["max_runtime"]),
            ]
            if options.get("source"):
                crawler_args.extend(["--source", options["source"]])
            if options["resume"]:
                crawler_args.append("--resume")
            if options["no_assets"]:
                crawler_args.append("--no-assets")
            if options["ocr"]:
                crawler_args.append("--ocr")
            if options["ocr_limit"]:
                crawler_args.extend(["--ocr-limit", str(options["ocr_limit"])])
            if options["skip_dynamic"]:
                crawler_args.append("--skip-dynamic")
            for source_key in options["exclude_source"]:
                crawler_args.extend(["--exclude-source", source_key])

            self.stdout.write("Running crawler pipeline...")
            sys.argv = crawler_args
            crawler_main()

            if options["no_import"]:
                self.stdout.write(self.style.SUCCESS("Crawler pipeline finished. Import skipped."))
                return

            import_input = Path(options["import_input"])
            if not import_input.is_absolute():
                import_input = scraping_root / import_input
            self.stdout.write(f"Importing crawler output: {import_input}")
            call_command("import_crawler_json", input=str(import_input), activate=options["activate"])
            self.stdout.write(self.style.SUCCESS("Crawler pipeline finished and imported."))
        finally:
            sys.argv = previous_argv
            os.chdir(previous_cwd)
