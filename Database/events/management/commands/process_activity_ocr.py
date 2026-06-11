import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from events.ai_providers import create_no_proxy_session
from events.models import AIProcessingLog, Activity
from events.services import backfill_activity_assets_from_images, is_seed_activity, backfill_missing_fields
from admin_app.diagnostics import recompute_activity_readiness
from pipeline.ocr_client import call_ocr


class Command(BaseCommand):
    help = "Process OCR for active public activities with usable images."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--activity-id", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        limit = max(1, int(options["limit"]))
        dry_run = bool(options["dry_run"])
        backfill_result = backfill_activity_assets_from_images(dry_run=dry_run)
        if options.get("activity_id"):
            qs = Activity.objects.filter(id=options["activity_id"], excluded_from_public=False)
        else:
            qs = Activity.objects.filter(
                status="active",
                excluded_from_public=False,
                is_activity=True,
            )
        qs = (
            qs.exclude(ocr_status="success")
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=timezone.now()))
            .filter(
                Q(image_url__startswith="https://")
                | Q(ocr_image_url__startswith="https://")
                | Q(ocr_image_path__gt="")
                | Q(assets__ocr_eligible=True)
            )
        )
        activities = [activity for activity in qs.distinct().order_by("start_date", "id")[:limit] if not is_seed_activity(activity)]
        processed = 0
        success = 0
        failed = 0
        skipped = 0
        for activity in activities:
            try:
                image_path = prepare_ocr_image_path(activity, dry_run=dry_run)
            except Exception as exc:
                skipped += 1
                if not dry_run:
                    activity.ocr_ready = False
                    activity.ocr_status = "skipped_image_download_failed"
                    activity.ocr_warnings = merge_warning(activity.ocr_warnings, str(exc)[:300])
                    activity.save(update_fields=["ocr_ready", "ocr_status", "ocr_warnings", "updated_at"])
                continue
            if not image_path:
                skipped += 1
                if not dry_run:
                    activity.ocr_ready = False
                    activity.ocr_status = "skipped_no_local_image"
                    activity.ocr_warnings = merge_warning(activity.ocr_warnings, "有圖片 URL，但無法取得本機 OCR 圖檔。請確認圖片 URL 可連線。")
                    activity.save(update_fields=["ocr_ready", "ocr_status", "ocr_warnings", "updated_at"])
                continue
            processed += 1
            if dry_run:
                continue
            try:
                result = call_ocr(str(image_path))
                activity.ocr_text = result["ocr_text"]
                activity.ocr_summary = result["ocr_summary"]
                activity.ocr_confidence = result["ocr_confidence"]
                activity.ocr_warnings = json.dumps(result["ocr_warnings"], ensure_ascii=False)
                activity.ocr_ready = bool(activity.ocr_text or activity.ocr_summary)
                activity.ocr_status = "success" if activity.ocr_ready else "failed"
                activity.ocr_image_path = str(image_path)
                activity.save(update_fields=[
                    "ocr_text",
                    "ocr_summary",
                    "ocr_confidence",
                    "ocr_warnings",
                    "ocr_ready",
                    "ocr_status",
                    "ocr_image_path",
                    "updated_at",
                ])
                AIProcessingLog.objects.create(
                    activity=activity,
                    task_type="ocr",
                    model=str(result.get("provider", "") + ":" + result.get("model", "")).strip(":"),
                    prompt_version="ocr-v1",
                    input_summary=str(image_path)[:500],
                    output_json={"ocr_status": activity.ocr_status},
                    status="success",
                )
                
                # Try backfilling dates and locations from OCR text
                backfill_missing_fields(activity)
                # Recompute readiness (this saves the activity if there are updates to dates/locations/status)
                recompute_activity_readiness(activity, save=True)
                
                success += 1
            except Exception as exc:
                failed += 1
                activity.ocr_ready = False
                activity.ocr_status = "failed"
                activity.ocr_warnings = merge_warning(activity.ocr_warnings, str(exc)[:300])
                activity.save(update_fields=["ocr_ready", "ocr_status", "ocr_warnings", "updated_at"])
                AIProcessingLog.objects.create(
                    activity=activity,
                    task_type="ocr",
                    model=str(result.get("provider", "") + ":" + result.get("model", "")).strip(":"),
                    prompt_version="ocr-v1",
                    input_summary=str(image_path)[:500],
                    output_json={"ocr_status": "failed"},
                    status="failed",
                    error=str(exc)[:1000],
                )
        self.stdout.write(self.style.SUCCESS(
            f"OCR done: checked={len(activities)} processed={processed} success={success} "
            f"failed={failed} skipped={skipped} backfill_created={backfill_result['created']}"
        ))


def resolve_ocr_image_path(activity):
    candidates = [activity.ocr_image_path]
    for raw_path in candidates:
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.exists() and path.is_file():
            return path
    return None


def prepare_ocr_image_path(activity, *, dry_run=False):
    local_path = resolve_ocr_image_path(activity)
    if local_path:
        return local_path
    image_url = ocr_image_url(activity)
    if not image_url or dry_run:
        return None
    return download_ocr_image(activity, image_url)


def ocr_image_url(activity):
    if activity.ocr_image_url:
        return activity.ocr_image_url
    if activity.image_url:
        return activity.image_url
    asset = activity.assets.filter(ocr_eligible=True).order_by("-is_primary", "-created_at").first()
    return asset.url if asset else ""


def download_ocr_image(activity, image_url):
    output_dir = Path.cwd() / "scraping" / "data" / "ocr_assets"
    output_dir.mkdir(parents=True, exist_ok=True)
    session = create_no_proxy_session()
    response = session.get(image_url, timeout=20)
    if response.status_code >= 400:
        raise RuntimeError(f"image download HTTP {response.status_code}")
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type and not content_type.startswith("image/"):
        raise RuntimeError(f"image download returned non-image content: {content_type}")
    suffix = image_suffix(image_url, content_type, response.content)
    path = output_dir / f"activity_{activity.id}{suffix}"
    path.write_bytes(response.content)
    activity.ocr_image_url = image_url
    activity.ocr_image_path = str(path)
    activity.save(update_fields=["ocr_image_url", "ocr_image_path", "updated_at"])
    return path


def image_suffix(image_url, content_type, content):
    parsed_suffix = Path(urlparse(image_url).path).suffix.lower()
    if parsed_suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return parsed_suffix
    guessed = mimetypes.guess_extension(content_type or "")
    if guessed in {".jpe"}:
        return ".jpg"
    if guessed in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return guessed
    if content.startswith(b"\x89PNG"):
        return ".png"
    if content.startswith(b"\xff\xd8"):
        return ".jpg"
    if content.startswith(b"RIFF") and b"WEBP" in content[:20]:
        return ".webp"
    return ".jpg"


def merge_warning(existing, warning):
    warnings = []
    if existing:
        try:
            parsed = json.loads(existing)
            if isinstance(parsed, list):
                warnings.extend(str(item) for item in parsed)
            else:
                warnings.append(str(parsed))
        except json.JSONDecodeError:
            warnings.append(str(existing))
    if warning and warning not in warnings:
        warnings.append(warning)
    return json.dumps(warnings[-5:], ensure_ascii=False)



