from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from admin_app.diagnostics import recompute_activity_readiness
from events.ai_tagger import apply_safe_repairs, normalize_ai_result
from events.management.commands.ai_tag_activities import Command as AiTagCommand
from events.management.commands.run_full_pipeline import Command as FullPipelineCommand
from events.management.commands import run_queued_crawl_jobs
from events.models import AIProcessingLog, Activity, ActivityChangeLog, CrawlJob


class AiRepairPipelineTests(TestCase):
    def test_ocr_evidence_can_repair_core_fields_and_enable_readiness(self):
        activity = Activity.objects.create(
            title="大溪展覽",
            description="活動內容",
            status="active",
            is_activity=True,
            source_url="https://example.com/activity",
            official_detail_url="https://example.com/activity",
            fee_type="unknown",
            line_ready=False,
            recommendation_ready=False,
        )
        result = normalize_ai_result(
            {
                "repairs": [
                    {
                        "field": "start_date",
                        "value": (timezone.localdate() + timedelta(days=7)).isoformat(),
                        "confidence": 0.91,
                        "evidence_text": "活動日期：下週展出",
                        "evidence_source": "ocr",
                    },
                    {
                        "field": "location",
                        "value": "桃園市大溪區壹號館",
                        "confidence": 0.9,
                        "evidence_text": "活動地點：桃園市大溪區壹號館",
                        "evidence_source": "ocr",
                    },
                ]
            },
            {},
            min_confidence=0.6,
        )

        outcome = apply_safe_repairs(activity, result, dry_run=False)
        activity.refresh_from_db()
        recompute_activity_readiness(activity, save=True)
        activity.refresh_from_db()

        self.assertEqual({item["field"] for item in outcome["applied_repairs"]}, {"start_date", "location"})
        self.assertTrue(activity.start_date)
        self.assertEqual(activity.location, "桃園市大溪區壹號館")
        self.assertTrue(activity.line_ready)
        self.assertTrue(activity.recommendation_ready)
        self.assertEqual(ActivityChangeLog.objects.filter(activity=activity, source="ai_repair").count(), 2)

    def test_invalid_range_long_location_and_low_confidence_are_rejected(self):
        activity = Activity.objects.create(title="測試活動", status="active", is_activity=True)
        start = timezone.localdate() + timedelta(days=20)
        end = timezone.localdate() + timedelta(days=19)
        result = normalize_ai_result(
            {
                "repairs": [
                    {
                        "field": "start_date",
                        "value": start.isoformat(),
                        "confidence": 0.9,
                        "evidence_text": f"開始：{start.isoformat()}",
                        "evidence_source": "html_main",
                    },
                    {
                        "field": "end_date",
                        "value": end.isoformat(),
                        "confidence": 0.9,
                        "evidence_text": f"結束：{end.isoformat()}",
                        "evidence_source": "html_main",
                    },
                    {
                        "field": "location",
                        "value": "導覽" * 80,
                        "confidence": 0.9,
                        "evidence_text": "活動地點：導覽",
                        "evidence_source": "html_text",
                    },
                    {
                        "field": "district",
                        "value": "大溪區",
                        "confidence": 0.4,
                        "evidence_text": "大溪區",
                        "evidence_source": "ocr",
                    },
                ]
            },
            {},
            min_confidence=0.6,
        )

        outcome = apply_safe_repairs(activity, result, dry_run=True)

        rejected = {item["field"]: item["reject_reason"] for item in outcome["rejected_repairs"]}
        self.assertEqual(rejected["start_date"], "date_range_invalid")
        self.assertEqual(rejected["end_date"], "date_range_invalid")
        self.assertEqual(rejected["location"], "location_too_long")
        self.assertEqual(rejected["district"], "confidence below 0.65")

    def test_tag_command_candidate_pool_includes_not_recommendation_ready_and_skips_only_repair_prompt(self):
        stale = Activity.objects.create(
            title="舊 tag 成功但缺資料",
            description="活動內容",
            status="active",
            is_activity=True,
            source_url="https://example.com/old",
            recommendation_ready=False,
        )
        repaired = Activity.objects.create(
            title="同版已成功",
            description="活動內容",
            status="active",
            is_activity=True,
            source_url="https://example.com/repaired",
            recommendation_ready=False,
        )
        AIProcessingLog.objects.create(
            activity=stale,
            task_type="tagging",
            status="success",
            prompt_version="tag-v1",
        )
        AIProcessingLog.objects.create(
            activity=repaired,
            task_type="tagging",
            status="success",
            prompt_version="tag-repair-v1",
        )

        activities = AiTagCommand()._get_activities(None, 10, False, None, 0, None, True)

        self.assertIn(stale, activities)
        self.assertNotIn(repaired, activities)

    def test_repair_gaps_only_excludes_complete_directly_crawled_activity(self):
        incomplete = Activity.objects.create(
            title="缺日期活動",
            description="活動內容",
            status="active",
            is_activity=True,
            source_url="https://example.com/incomplete",
            end_date=timezone.now() + timedelta(days=7),
        )
        complete = Activity.objects.create(
            title="完整活動",
            description="活動內容",
            status="active",
            is_activity=True,
            source_url="https://example.com/complete",
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            location="桃園市大溪區壹號館",
            district="大溪區",
            fee_type="free",
        )

        activities = AiTagCommand()._get_activities(None, 10, False, None, 0, None, False, True)

        self.assertIn(incomplete, activities)
        self.assertNotIn(complete, activities)

    def test_full_pipeline_runs_ocr_before_ai_repair_tag(self):
        command = FullPipelineCommand()
        calls = []
        command._sep = lambda: None
        command._header = lambda title: None
        command._expire_activities = lambda: calls.append("expire")
        command._run_ocr = lambda limit: calls.append("ocr")
        command._run_tag = lambda limit: calls.append("tag")

        command.handle(
            skip_crawl=True,
            skip_ocr=False,
            skip_tag=False,
            limit=1,
            tag_limit=0,
            ocr_limit=0,
        )

        self.assertEqual(calls, ["expire", "ocr", "tag"])

    def test_admin_full_pipeline_job_runs_ocr_before_ai_repair_tag(self):
        job = CrawlJob.objects.create(
            title="完整更新",
            source="",
            options={"full_pipeline": True, "primary_limit": 1, "post_process_limit": 1},
        )
        calls = []

        original_run_crawler = run_queued_crawl_jobs.call_command
        original_expire = run_queued_crawl_jobs.expire_active_activities
        original_imported = run_queued_crawl_jobs.imported_activity_ids
        original_ocr = run_queued_crawl_jobs.run_ocr_stage
        original_tag = run_queued_crawl_jobs.run_ai_tag_stage
        original_search = run_queued_crawl_jobs.run_search_profile_stage
        original_summary = run_queued_crawl_jobs.run_summary_stage
        try:
            run_queued_crawl_jobs.call_command = lambda *args, **kwargs: None
            run_queued_crawl_jobs.expire_active_activities = lambda: {"message": "ok"}
            run_queued_crawl_jobs.imported_activity_ids = lambda path: []
            run_queued_crawl_jobs.run_ocr_stage = lambda task, ids, limit, cooldown: calls.append("ocr") or {"success": 1, "failed": 0}
            run_queued_crawl_jobs.run_ai_tag_stage = lambda task, ids, limit, cooldown: calls.append("tag") or {"success": 1, "failed": 0}
            run_queued_crawl_jobs.run_search_profile_stage = lambda task, ids, limit, cooldown: calls.append("search") or {"success": 1, "failed": 0}
            run_queued_crawl_jobs.run_summary_stage = lambda task, ids, limit, cooldown: calls.append("summary") or {"success": 1, "failed": 0}

            run_queued_crawl_jobs.run_full_pipeline_job(job, command=type("C", (), {"stderr": type("S", (), {"write": lambda self, msg: None})()})())
        finally:
            run_queued_crawl_jobs.call_command = original_run_crawler
            run_queued_crawl_jobs.expire_active_activities = original_expire
            run_queued_crawl_jobs.imported_activity_ids = original_imported
            run_queued_crawl_jobs.run_ocr_stage = original_ocr
            run_queued_crawl_jobs.run_ai_tag_stage = original_tag
            run_queued_crawl_jobs.run_search_profile_stage = original_search
            run_queued_crawl_jobs.run_summary_stage = original_summary

        self.assertEqual(calls, ["ocr", "tag", "search", "summary"])
