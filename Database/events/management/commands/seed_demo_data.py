from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from admin_app.diagnostics import recompute_activity_readiness
from events.models import (
    Activity,
    ActivitySearchProfile,
    ActivityTagSuggestion,
    SourceWebsite,
    Subscription,
    Tag,
    UserProfile,
)


class Command(BaseCommand):
    help = "Create deterministic demo records for backend and LINE presentation rehearsal."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete old demo records before seeding.")

    def handle(self, *args, **options):
        if options["reset"]:
            Activity.objects.filter(source_key="demo").delete()
            UserProfile.objects.filter(line_user_id__startswith="demo-").delete()

        source, _ = SourceWebsite.objects.get_or_create(
            name="DEMO 展示資料來源",
            defaults={
                "url": "https://demo.local/taoyuan-events",
                "source_type": "department",
                "is_active": True,
            },
        )
        tags = ensure_demo_tags()
        now = timezone.now()

        normal = upsert_activity(
            "demo-normal",
            source,
            title="[DEMO] 中壢免費親子手作市集",
            description="中壢週末親子手作、市集與小型表演，適合展示 LINE 推薦卡片、追問與訂閱。",
            start_date=now + timedelta(days=5),
            end_date=now + timedelta(days=5, hours=3),
            district="中壢區",
            location="中壢展演中心",
            ai_summary="中壢週末親子手作市集，適合家庭一起體驗手作與市集活動。",
            is_free=True,
            fee_type="free",
            fee_description="免費入場",
            image_url="https://images.unsplash.com/photo-1472162072942-cd5147eb3902?w=800&h=520&fit=crop&auto=format",
            official_link_status="ok",
        )
        normal.tags.set([tags["親子"], tags["手作"], tags["免費"], tags["中壢"]])
        ActivitySearchProfile.objects.update_or_create(
            activity=normal,
            defaults={
                "search_text": "中壢 免費 親子 手作 市集 小朋友 家庭",
                "keywords": ["中壢", "免費", "手作"],
                "topics": ["親子", "市集"],
                "synonyms": ["小朋友", "家庭"],
                "status": "success",
                "provider_model": "demo",
            },
        )
        ActivityTagSuggestion.objects.update_or_create(
            activity=normal,
            tag_name="市集",
            tag_type="activity_type",
            source="demo",
            defaults={
                "tag": tags["市集"],
                "confidence": 0.92,
                "reason": "Demo 用 pending tag，展示 Tag 審核流程。",
                "status": "pending",
            },
        )

        manual = upsert_activity(
            "demo-manual-review",
            source,
            title="[DEMO] 待審核抽獎活動",
            description="資料需要人工確認，展示 manual_review_required 不會進 LINE 或推薦池。",
            start_date=now + timedelta(days=8),
            end_date=now + timedelta(days=9),
            district="桃園區",
            location="桃園市政府前廣場",
            ai_summary="待人工審核的抽獎活動。",
            official_link_status="ok",
            exclude_from_recommendation_reason="manual_review_required",
        )
        recompute_activity_readiness(manual, save=True)

        summary_gap = upsert_activity(
            "demo-summary-gap",
            source,
            title="[DEMO] AI 摘要待補活動",
            description="這筆資料故意留空 AI 摘要，用於展示營運工具摘要缺口。",
            start_date=now + timedelta(days=12),
            end_date=now + timedelta(days=12, hours=2),
            district="平鎮區",
            location="平鎮圖書館",
            ai_summary="",
            official_link_status="ok",
        )
        summary_gap.tags.set([tags["藝文"], tags["免費"]])

        link_error = upsert_activity(
            "demo-link-error",
            source,
            title="[DEMO] 官方連結待確認活動",
            description="官方連結暫時 timeout/error，但不等於 dead link，展示待確認篩選。",
            start_date=now + timedelta(days=15),
            end_date=now + timedelta(days=15, hours=2),
            district="八德區",
            location="八德藝文中心",
            ai_summary="官方連結待確認的藝文活動。",
            official_link_status="error",
            official_link_error="demo timeout",
        )

        dead_link = upsert_activity(
            "demo-link-dead",
            source,
            title="[DEMO] 官方連結失效活動",
            description="官方頁 404，展示 dead link 退出公開與推薦池。",
            start_date=now + timedelta(days=18),
            end_date=now + timedelta(days=18, hours=2),
            district="大溪區",
            location="大溪老街",
            ai_summary="官方連結失效活動。",
            official_link_status="dead",
        )
        recompute_activity_readiness(dead_link, save=True)

        expired = upsert_activity(
            "demo-expired",
            source,
            title="[DEMO] 過期自動下架活動",
            description="故意建立過期 active，再透過 readiness 重算變 inactive。",
            start_date=now - timedelta(days=10),
            end_date=now - timedelta(days=1),
            district="龜山區",
            location="龜山公園",
            ai_summary="過期活動展示。",
            official_link_status="ok",
        )
        recompute_activity_readiness(expired, save=True)

        fallback = upsert_activity(
            "demo-fallback-image",
            source,
            title="[DEMO] 圖片 fallback 展示活動",
            description="故意不放圖片，展示圖片 fallback 與品質提醒。",
            start_date=now + timedelta(days=21),
            end_date=now + timedelta(days=21, hours=2),
            district="蘆竹區",
            location="蘆竹親子館",
            ai_summary="圖片 fallback 展示活動。",
            image_url="",
            official_link_status="ok",
        )
        fallback.tags.set([tags["親子"], tags["藝文"]])

        user, _ = UserProfile.objects.update_or_create(
            line_user_id="demo-line-user",
            defaults={
                "display_name": "Demo 展示使用者",
                "push_enabled": True,
                "recommend_push_enabled": True,
                "default_remind_before_days": 1,
            },
        )
        user.preferred_tags.set([tags["親子"], tags["免費"], tags["中壢"]])
        Subscription.objects.update_or_create(
            user=user,
            activity=normal,
            defaults={"status": "active", "remind_before_days": 1, "is_notified": False},
        )

        self.stdout.write(self.style.SUCCESS(
            f"Seeded demo data: activities={Activity.objects.filter(source_key='demo').count()}, "
            f"users={UserProfile.objects.filter(line_user_id__startswith='demo-').count()}"
        ))


def ensure_demo_tags():
    specs = {
        "中壢": "region",
        "親子": "audience",
        "免費": "cost",
        "手作": "activity_type",
        "市集": "activity_type",
        "藝文": "activity_type",
    }
    tags = {}
    for name, tag_type in specs.items():
        tag, _ = Tag.objects.get_or_create(name=name, tag_type=tag_type, defaults={"is_active": True})
        tags[name] = tag
    return tags


def upsert_activity(source_item_id, source, **values):
    defaults = {
        "source_agency": source.name,
        "source_website": source,
        "source_key": "demo",
        "source_url": f"https://demo.local/taoyuan-events/{source_item_id}",
        "official_detail_url": f"https://demo.local/taoyuan-events/{source_item_id}",
        "raw_content": f"<main><h1>{values['title']}</h1><p>{values['description']}</p></main>",
        "status": "active",
        "item_type": "activity",
        "is_activity": True,
        "is_public_item": True,
        "line_ready": True,
        "ai_ready": True,
        "recommendation_ready": True,
        "quality_score": 90,
        "quality_level": "high",
        "quality_warnings": "",
        "exclude_from_recommendation_reason": "",
        "ocr_status": "success",
        "ocr_summary": "Demo OCR summary",
        "is_free": values.pop("is_free", True),
        "fee_type": values.pop("fee_type", "free"),
        "fee_description": values.pop("fee_description", "免費"),
        "image_url": values.pop("image_url", "https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=800&h=520&fit=crop&auto=format"),
        "official_link_error": "",
        **values,
    }
    activity, _ = Activity.objects.update_or_create(
        source_key="demo",
        source_item_id=source_item_id,
        defaults=defaults,
    )
    return activity
