import sys
from django.core.management.base import BaseCommand
from django.db import transaction
from events.models import Activity
from events.services import backfill_missing_fields
from admin_app.diagnostics import recompute_activity_readiness

class Command(BaseCommand):
    help = "重新套用 HTML/OCR 備用資料回填與狀態重算邏輯至現有活動"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="不寫入資料庫，只印出會被改變的活動",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="強制重算所有活動，否則預設只重算 line_ready=False 的活動",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]

        if force:
            qs = Activity.objects.all()
        else:
            qs = Activity.objects.filter(line_ready=False)

        total = qs.count()
        self.stdout.write(f"找到 {total} 筆活動準備進行重算...")

        updated_count = 0
        with transaction.atomic():
            for idx, activity in enumerate(qs, 1):
                old_line_ready = activity.line_ready
                old_ai_ready = activity.ai_ready
                old_recommendation_ready = activity.recommendation_ready
                old_is_public_item = activity.is_public_item
                old_final_state = activity.final_state
                old_quality_warnings = activity.quality_warnings
                old_start = activity.start_date
                old_end = activity.end_date
                old_location = activity.location
                old_district = activity.district

                # 1. 執行補缺邏輯 (HTML + OCR)
                backfill_missing_fields(activity)
                
                # 2. 狀態重算
                recompute_activity_readiness(activity, save=False)

                changed = (
                    old_line_ready != activity.line_ready or
                    old_ai_ready != activity.ai_ready or
                    old_recommendation_ready != activity.recommendation_ready or
                    old_is_public_item != activity.is_public_item or
                    old_final_state != activity.final_state or
                    old_quality_warnings != activity.quality_warnings or
                    old_start != activity.start_date or
                    old_end != activity.end_date or
                    old_location != activity.location or
                    old_district != activity.district
                )

                if changed:
                    updated_count += 1
                    msg = (
                        f"[{idx}/{total}] 更新 ID:{activity.id} ({activity.title[:15]}...) \n"
                        f"  Date: {old_start} -> {activity.start_date} \n"
                        f"  End: {old_end} -> {activity.end_date} \n"
                        f"  Location: {old_location} -> {activity.location} \n"
                        f"  District: {old_district} -> {activity.district} \n"
                        f"  Line Ready: {old_line_ready} -> {activity.line_ready} \n"
                        f"  AI Ready: {old_ai_ready} -> {activity.ai_ready} \n"
                        f"  Final State: {old_final_state} -> {activity.final_state}"
                    )
                    self.stdout.write(self.style.SUCCESS(msg))
                
                if not dry_run and changed:
                    activity.save(update_fields=[
                        "start_date", "end_date", "location", "district",
                        "line_ready", "recommendation_ready", 
                        "is_public_item", "ai_ready", "final_state", "quality_warnings", "updated_at"
                    ])

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING(f"\n[DRY RUN] 測試結束。共有 {updated_count} 筆資料會被更新。"))
            else:
                self.stdout.write(self.style.SUCCESS(f"\n[SUCCESS] 處理完成。共更新了 {updated_count} 筆活動狀態！"))
