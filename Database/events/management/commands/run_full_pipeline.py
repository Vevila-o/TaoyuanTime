"""
run_full_pipeline.py
一鍵執行完整流程：
  1. 爬蟲 (crawler_main)
  2. 匯入 DB (import_crawler_json)
  3. 下架過期活動
  4. OCR（跳過已 success 的舊資料）
  5. AI Repair+Tag（跳過已成功標記的同版資料）

用法：
  python manage.py run_full_pipeline \
      --limit 100 \
      --primary-limit 100 --secondary-limit 100 \
      --max-runtime 60 --skip-dynamic

  加 --no-assets 跳過圖片下載（速度快很多）
  加 --source culture 只跑單一來源
"""
import os
import sys
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from events.ai_tagger import PROMPT_VERSION
from events.models import AIProcessingLog, Activity


class Command(BaseCommand):
    help = "一鍵執行：爬蟲 → 匯入 → 下架過期 → OCR → AI Repair+Tag（自動跳過已處理）"

    def add_arguments(self, parser):
        # 爬蟲參數
        parser.add_argument("--mode", default="reliability_v3",
                            choices=["probe_1hour", "reliability_v3", "custom"])
        parser.add_argument("--source", type=str, default=None,
                            help="只跑指定 source key（留空=全部）")
        parser.add_argument("--primary-limit", type=int, default=100,
                            help="每個 primary 來源最多幾筆")
        parser.add_argument("--secondary-limit", type=int, default=100,
                            help="每個 secondary 來源最多幾筆")
        parser.add_argument("--max-runtime", type=int, default=60,
                            help="爬蟲最長執行分鐘數")
        parser.add_argument("--no-assets", action="store_true",
                            help="跳過圖片下載（大幅加速）")
        parser.add_argument("--skip-dynamic", action="store_true",
                            help="跳過 DynamicFetcher 來源")
        parser.add_argument("--exclude-source", action="append", default=[],
                            help="排除特定 source key，可重複使用")

        # AI 後處理參數
        parser.add_argument("--limit", type=int, default=100,
                            help="AI Tag / OCR 最多處理幾筆活動")
        parser.add_argument("--tag-limit", type=int, default=0,
                            help="AI Tag 單獨限制（0=使用 --limit）")
        parser.add_argument("--ocr-limit", type=int, default=0,
                            help="OCR 單獨限制（0=使用 --limit）")

        # 流程控制
        parser.add_argument("--skip-crawl", action="store_true",
                            help="跳過爬蟲，直接對 DB 現有資料跑 Tag/OCR")
        parser.add_argument("--skip-tag", action="store_true",
                            help="跳過 AI Tag")
        parser.add_argument("--skip-ocr", action="store_true",
                            help="跳過 OCR")

    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        self._sep()
        self.stdout.write("🚀  完整流程開始")
        self._sep()

        limit = options["limit"]
        tag_limit = options["tag_limit"] or limit
        ocr_limit = options["ocr_limit"] or limit

        # ── 1. 爬蟲 + 匯入 ────────────────────────────────────────────
        if not options["skip_crawl"]:
            self._header("① 爬蟲 + 匯入 DB")
            self._run_crawler_pipeline(options)
        else:
            self.stdout.write("⏭  跳過爬蟲（--skip-crawl）")

        # ── 2. 下架過期 ───────────────────────────────────────────────
        self._header("② 下架過期活動")
        self._expire_activities()

        # ── 3. OCR ────────────────────────────────────────────────────
        if not options["skip_ocr"]:
            self._header(f"③ OCR（上限 {ocr_limit} 筆，跳過已成功）")
            self._run_ocr(ocr_limit)
        else:
            self.stdout.write("⏭  跳過 OCR（--skip-ocr）")

        # ── 4. AI Repair+Tag ──────────────────────────────────────────
        if not options["skip_tag"]:
            self._header(f"④ AI Repair+Tag（上限 {tag_limit} 筆，跳過同版成功）")
            self._run_tag(tag_limit)
        else:
            self.stdout.write("⏭  跳過 AI Repair+Tag（--skip-tag）")

        self._sep()
        self.stdout.write(self.style.SUCCESS("✅  完整流程結束"))
        self._sep()

    # ------------------------------------------------------------------ #
    # 爬蟲
    # ------------------------------------------------------------------ #
    def _run_crawler_pipeline(self, options):
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
            if options["no_assets"]:
                crawler_args.append("--no-assets")
            if options["skip_dynamic"]:
                crawler_args.append("--skip-dynamic")
            for sk in options["exclude_source"]:
                crawler_args.extend(["--exclude-source", sk])

            self.stdout.write(f"爬蟲參數：{' '.join(crawler_args[1:])}")
            sys.argv = crawler_args
            crawler_main()

            # 匯入 JSON → DB
            import_input = scraping_root / "data" / "output" / "activities_all.json"
            if import_input.exists():
                self.stdout.write(f"\n匯入 {import_input} ...")
                call_command("import_crawler_json", input=str(import_input), activate=True)
            else:
                self.stdout.write(self.style.WARNING(f"⚠️  找不到匯入檔：{import_input}"))
        finally:
            sys.argv = previous_argv
            os.chdir(previous_cwd)

    # ------------------------------------------------------------------ #
    # 下架過期
    # ------------------------------------------------------------------ #
    def _expire_activities(self):
        today = timezone.localdate()
        qs = Activity.objects.filter(status="active", end_date__date__lt=today)
        count = qs.update(status="inactive", updated_at=timezone.now())
        self.stdout.write(f"已下架 {count} 筆過期活動。")

    # ------------------------------------------------------------------ #
    # AI Repair+Tag —— 只選「尚未成功同版 repair+tag」的活動
    # ------------------------------------------------------------------ #
    def _run_tag(self, limit):
        already_tagged = set(
            AIProcessingLog.objects.filter(
                task_type="tagging",
                status="success",
                prompt_version=PROMPT_VERSION,
                activity_id__isnull=False,
            ).values_list("activity_id", flat=True)
        )

        candidates = (
            Activity.objects.filter(
                status="active",
                excluded_from_public=False,
                is_activity=True,
            )
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=timezone.now()))
            .exclude(id__in=already_tagged)
            .order_by("start_date", "id")[:limit]
        )

        ids = list(candidates.values_list("id", flat=True))
        if not ids:
            self.stdout.write("沒有需要 AI Repair+Tag 的活動。")
            return

        self.stdout.write(f"找到 {len(ids)} 筆待 Repair+Tag 活動，開始處理...")
        success = failed = 0
        for activity_id in ids:
            try:
                call_command(
                    "ai_tag_activities",
                    activity_id=activity_id,
                    apply=True,
                    skip_tagged_success=True,
                )
                success += 1
            except Exception as exc:
                failed += 1
                self.stdout.write(self.style.WARNING(f"  Repair+Tag 失敗 id={activity_id}: {exc}"))

        self.stdout.write(self.style.SUCCESS(
            f"AI Repair+Tag 完成：成功 {success} / 失敗 {failed} / 總計 {len(ids)}"
        ))

    # ------------------------------------------------------------------ #
    # OCR —— 只選「尚未成功 OCR」的活動
    # ------------------------------------------------------------------ #
    def _run_ocr(self, limit):
        candidates = (
            Activity.objects.filter(
                status="active",
                excluded_from_public=False,
                is_activity=True,
            )
            .exclude(ocr_status="success")
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=timezone.now()))
            .filter(
                Q(image_url__startswith="https://")
                | Q(ocr_image_url__startswith="https://")
                | Q(ocr_image_path__gt="")
                | Q(assets__ocr_eligible=True)
            )
            .order_by("start_date", "id")
            .distinct()[:limit]
        )

        ids = list(candidates.values_list("id", flat=True))
        if not ids:
            self.stdout.write("沒有需要 OCR 的活動。")
            return

        self.stdout.write(f"找到 {len(ids)} 筆待 OCR 活動，開始處理...")
        success = failed = skipped = 0
        for activity_id in ids:
            try:
                call_command("process_activity_ocr", activity_id=activity_id, limit=1)
                activity = Activity.objects.get(id=activity_id)
                if activity.ocr_status == "success":
                    success += 1
                elif activity.ocr_status and activity.ocr_status.startswith("skipped"):
                    skipped += 1
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                self.stdout.write(self.style.WARNING(f"  OCR 失敗 id={activity_id}: {exc}"))

        self.stdout.write(self.style.SUCCESS(
            f"OCR 完成：成功 {success} / 略過 {skipped} / 失敗 {failed} / 總計 {len(ids)}"
        ))

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    def _sep(self):
        self.stdout.write("=" * 60)

    def _header(self, title):
        self.stdout.write("")
        self.stdout.write(f"── {title} {'─' * max(0, 55 - len(title))}")
