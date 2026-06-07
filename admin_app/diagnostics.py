import json
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from events.models import Activity, ActionLog
from events.services import activity_business_key, is_seed_activity


REASON_LABELS = {
    "inactive": "已下架",
    "expired": "已過期",
    "not_activity": "不是活動",
    "not_public": "未開放前台",
    "missing_official_detail": "缺官方詳細頁",
    "line_not_ready": "未標記 LINE ready",
    "recommendation_not_ready": "未標記推薦 ready",
    "ai_not_ready": "未標記 AI ready",
    "ai_summary_exists": "已有 AI 摘要",
    "seed_sample": "疑似假資料",
    "quality_rejected": "品質為 rejected",
    "image_fallback": "圖片需 fallback",
    "ocr_success": "OCR 已成功",
    "ocr_no_image": "沒有 OCR 候選圖",
    "ocr_not_front_pool": "不在前台池",
    "ocr_failed": "OCR 失敗",
    "ocr_not_run": "OCR 尚未執行",
}

ACTION_LABELS = {
    "view_card": "看過活動卡片",
    "view_detail": "點詳細資訊",
    "interested": "感興趣",
    "not_interested": "不感興趣",
    "subscribe": "訂閱活動",
    "unsubscribe": "取消訂閱",
    "how_to_go": "點導航",
    "add_calendar": "加入行事曆",
    "view_more": "查看更多活動",
    "citizen_card_click": "點市民卡資訊",
}

QUALITY_WARNING_LABELS = {
    "no_valid_poster_or_main_visual": "沒有可用主視覺圖",
    "cross_source_duplicate_merged": "跨來源重複已合併",
    "poster_not_validated": "海報尚未驗證",
    "small_sample_size": "樣本數偏小",
    "date_range_invalid": "日期區間異常",
}


def is_expired(activity, now=None):
    now = now or timezone.now()
    return bool(activity.end_date and activity.end_date < now)


def has_official_detail(activity):
    return bool((activity.official_detail_url or "").strip())


def has_fallback_image(activity):
    image_url = activity.image_url or ""
    return not image_url or "placehold.co" in image_url


def parse_listish(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [text]
    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item).strip()]
    return [str(parsed)]


def translated_quality_warnings(activity):
    return [
        QUALITY_WARNING_LABELS.get(item, item)
        for item in parse_listish(activity.quality_warnings)
        if item and item != "[]"
    ]


def line_visibility_reasons(activity, now=None):
    reasons = []
    if activity.status != "active":
        reasons.append("inactive")
    if is_expired(activity, now):
        reasons.append("expired")
    if not activity.is_activity:
        reasons.append("not_activity")
    if not activity.is_public_item:
        reasons.append("not_public")
    if not has_official_detail(activity):
        reasons.append("missing_official_detail")
    if not activity.line_ready:
        reasons.append("line_not_ready")
    if activity.quality_level == "rejected":
        reasons.append("quality_rejected")
    return reasons


def recommendation_reasons(activity, now=None):
    reasons = []
    if activity.status != "active":
        reasons.append("inactive")
    if is_expired(activity, now):
        reasons.append("expired")
    if not activity.is_activity:
        reasons.append("not_activity")
    if not has_official_detail(activity):
        reasons.append("missing_official_detail")
    if not activity.recommendation_ready:
        reasons.append("recommendation_not_ready")
    if activity.quality_level == "rejected":
        reasons.append("quality_rejected")
    if activity.exclude_from_recommendation_reason:
        reasons.extend(parse_listish(activity.exclude_from_recommendation_reason))
    return reasons


def ai_summary_reasons(activity, now=None, force=False):
    reasons = []
    if activity.status != "active":
        reasons.append("inactive")
    if is_expired(activity, now):
        reasons.append("expired")
    if not activity.is_activity:
        reasons.append("not_activity")
    if not has_official_detail(activity):
        reasons.append("missing_official_detail")
    if not (activity.line_ready or activity.recommendation_ready):
        reasons.append("line_not_ready")
    if is_seed_activity(activity):
        reasons.append("seed_sample")
    if activity.ai_summary and not force:
        reasons.append("ai_summary_exists")
    return reasons


def ai_tag_reasons(activity, now=None):
    reasons = recommendation_reasons(activity, now)
    if not activity.ai_ready:
        reasons.append("ai_not_ready")
    return reasons


def ocr_reasons(activity, now=None):
    reasons = []
    front_reasons = recommendation_reasons(activity, now)
    if front_reasons:
        reasons.append("ocr_not_front_pool")
    if activity.ocr_status == "success":
        reasons.append("ocr_success")
    elif activity.ocr_status == "failed":
        reasons.append("ocr_failed")
    elif activity.ocr_status in {"skipped_no_image", ""} and not (activity.ocr_image_url or activity.ocr_image_path or activity.assets.filter(ocr_eligible=True).exists()):
        reasons.append("ocr_no_image")
    elif not activity.ocr_status:
        reasons.append("ocr_not_run")
    else:
        reasons.append(activity.ocr_status)
    return reasons


def labels(reason_codes):
    return [REASON_LABELS.get(code, code) for code in reason_codes]


def activity_exposure_diagnostic(activity, now=None):
    now = now or timezone.now()
    line = line_visibility_reasons(activity, now)
    rec = recommendation_reasons(activity, now)
    summary = ai_summary_reasons(activity, now)
    tag = ai_tag_reasons(activity, now)
    ocr = ocr_reasons(activity, now)
    quality = translated_quality_warnings(activity)
    if has_fallback_image(activity):
        quality.append(REASON_LABELS["image_fallback"])
    return {
        "line": {"ok": not line, "reasons": labels(line)},
        "recommendation": {"ok": not rec, "reasons": labels(rec)},
        "ai_summary": {"ok": not summary, "reasons": labels(summary)},
        "ai_tag": {"ok": not tag, "reasons": labels(tag)},
        "ocr": {"ok": ocr == ["ocr_success"], "reasons": labels(ocr)},
        "quality_warnings": quality,
        "business_key": activity_business_key(activity),
    }


def exposure_summary():
    now = timezone.now()
    qs = Activity.objects.all()
    summary = {
        "line_blocked": 0,
        "recommendation_blocked": 0,
        "ai_summary_blocked": 0,
        "ocr_blocked": 0,
        "fallback_image": qs.filter(Q(image_url="") | Q(image_url__icontains="placehold.co")).count(),
        "quality_warning": qs.exclude(quality_warnings="").exclude(quality_warnings="[]").count(),
        "duplicate_keys": 0,
    }
    reason_counter = Counter()
    business_keys = Counter()
    for activity in qs:
        line = line_visibility_reasons(activity, now)
        rec = recommendation_reasons(activity, now)
        summary_reasons = ai_summary_reasons(activity, now)
        ocr = ocr_reasons(activity, now)
        if line:
            summary["line_blocked"] += 1
        if rec:
            summary["recommendation_blocked"] += 1
        if summary_reasons:
            summary["ai_summary_blocked"] += 1
        if ocr != ["ocr_success"]:
            summary["ocr_blocked"] += 1
        for reason in line + rec + summary_reasons + ocr + parse_listish(activity.quality_warnings):
            if reason and reason != "[]":
                reason_counter[REASON_LABELS.get(reason, QUALITY_WARNING_LABELS.get(reason, reason))] += 1
        business_keys[activity_business_key(activity)] += 1
    summary["duplicate_keys"] = sum(1 for count in business_keys.values() if count > 1)
    top_reasons = reason_counter.most_common(8)
    return summary, top_reasons


def apply_readiness_filter(qs, readiness):
    now = timezone.now()
    if readiness == "line_blocked":
        return qs.filter(
            ~Q(status="active") |
            Q(end_date__lt=now) |
            Q(is_activity=False) |
            Q(is_public_item=False) |
            Q(line_ready=False) |
            Q(official_detail_url__isnull=True) |
            Q(official_detail_url="") |
            Q(quality_level="rejected")
        )
    if readiness == "recommendation_blocked":
        return qs.filter(
            ~Q(status="active") |
            Q(end_date__lt=now) |
            Q(is_activity=False) |
            Q(recommendation_ready=False) |
            Q(official_detail_url__isnull=True) |
            Q(official_detail_url="") |
            Q(quality_level="rejected") |
            ~Q(exclude_from_recommendation_reason="")
        )
    if readiness == "ai_summary_blocked":
        return qs.filter(
            ~Q(status="active") |
            Q(end_date__lt=now) |
            Q(is_activity=False) |
            Q(official_detail_url__isnull=True) |
            Q(official_detail_url="") |
            ~(Q(line_ready=True) | Q(recommendation_ready=True)) |
            ~Q(ai_summary="")
        )
    if readiness == "ocr_blocked":
        return qs.exclude(ocr_status="success")
    if readiness == "quality_warning":
        return qs.exclude(quality_warnings="").exclude(quality_warnings="[]")
    return qs


def read_health_report():
    output_root = Path(settings.BASE_DIR) / "scraping" / "data" / "output"
    health_path = output_root / "health_report.json"
    source_path = output_root / "source_quality_summary.json"
    result = {
        "health_exists": health_path.exists(),
        "overall_status": "missing",
        "generated_at": "",
        "failed_sections": [],
        "warnings": [],
        "sources": [],
        "totals": {},
        "failed_metrics": [],
        "operator_note": "尚未產生爬蟲健康報告。",
    }
    if health_path.exists():
        try:
            health = json.loads(health_path.read_text(encoding="utf-8"))
            result["overall_status"] = health.get("overall_status") or "unknown"
            result["generated_at"] = health.get("generated_at") or ""
            result["failed_sections"] = health.get("failed_sections") or []
            result["warnings"] = health.get("remaining_warnings") or []
            result["totals"] = health.get("totals") or {}
            result["failed_metrics"] = failed_health_metrics(health)
            result["operator_note"] = health_operator_note(result)
        except Exception as exc:
            result["overall_status"] = "read_error"
            result["failed_sections"] = [str(exc)]
            result["operator_note"] = "健康報告讀取失敗，請重新跑爬蟲或檢查 JSON。"
    if source_path.exists():
        try:
            sources = json.loads(source_path.read_text(encoding="utf-8"))
            result["sources"] = sources[:5] if isinstance(sources, list) else []
        except Exception:
            result["sources"] = []
    return result


def failed_health_metrics(health):
    metrics = []
    for section in ("health_metrics", "basic_function_metrics", "ai_function_metrics"):
        for item in health.get(section) or []:
            if item.get("status") == "FAIL":
                metrics.append({
                    "section": section,
                    "name": item.get("name") or "",
                    "description": item.get("description") or "",
                    "passed": item.get("passed"),
                    "total": item.get("total"),
                    "rate": item.get("rate"),
                    "threshold": item.get("threshold"),
                })
    return metrics[:8]


def health_operator_note(report):
    totals = report.get("totals") or {}
    warnings = report.get("warnings") or []
    warning_names = {item.get("name") for item in warnings if isinstance(item, dict)}
    events = int(totals.get("events") or 0)
    recommendation_items = int(totals.get("recommendation_items") or 0)
    ai_ready_items = int(totals.get("ai_ready_activity_items") or 0)
    if events <= 1 or "small_sample_size" in warning_names:
        return "這份報告看起來是小批測試輸出；FAIL 多半代表樣本太少，不代表正式資料庫壞掉。請用正式匯入或正式匯入 + OCR 後再看。"
    if recommendation_items == 0:
        return "本次爬蟲輸出沒有推薦池活動，請檢查 recommendation_ready、官方詳情頁、日期與地點欄位。"
    if ai_ready_items == 0:
        return "本次爬蟲輸出沒有 AI ready 活動，請檢查內容長度、日期、地點與官方來源。"
    if report.get("overall_status") == "PASS":
        return "健康報告通過。"
    return "健康報告未通過，請看下方失敗指標與來源警告。"


def human_action_label(action_type):
    return ACTION_LABELS.get(action_type, action_type)


def recent_recommended_activity_ids(user, limit=20):
    return (
        ActionLog.objects.filter(user=user, action_type="view_card", activity_id__isnull=False)
        .order_by("-created_at")
        .values_list("activity_id", flat=True)[:limit]
    )
