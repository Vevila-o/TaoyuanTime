"""
統一計算活動的所有 readiness 狀態。
這是 pipeline 中的最後一步（在 quality_score 之後）。
所有 readiness / published / searchable 判斷都集中在此。
"""
from datetime import date
from zoneinfo import ZoneInfo

def compute_readiness(event):
    """
    根據 event 現有欄位，統一計算並設定以下欄位：
    - has_required_date
    - has_title
    - has_location
    - has_source_url
    - line_ready / line_card_ready
    - ai_ready
    - search_ready
    - is_searchable
    - is_public_item
    - recommendation_ready
    - published (= status == 'active' 且可被查詢)
    - status_reason (人類可讀的狀態說明)
    - missing_fields (缺失欄位清單)
    """
    if not event:
        return event

    is_activity = bool(event.get("is_activity") or event.get("content_type") == "activity")
    has_title = bool(event.get("title"))
    has_date = bool(event.get("date_start"))
    has_location = bool(event.get("location") or event.get("district"))
    has_url = bool(event.get("official_detail_url") or event.get("source_url"))
    has_desc = bool(event.get("clean_description"))
    is_expired = event.get("freshness_status") == "expired" or event.get("status") == "inactive"
    invalid_date = "date_range_invalid" in event.get("quality_warnings", [])
    quality_ok = event.get("quality_level") in ("usable", "needs_review")
    manual_review = bool(event.get("manual_review_required"))

    # 寫入基礎欄位
    event["has_required_date"] = has_date
    event["has_title"] = has_title
    event["has_location"] = has_location
    event["has_source_url"] = has_url

    # 計算各 readiness
    line_ready = bool(
        is_activity and has_title and has_url and has_desc
        and has_date and has_location
        and not invalid_date and not is_expired
    )
    search_ready = bool(
        is_activity and has_title and has_url
        and has_date and has_location
        and not invalid_date and not is_expired
    )
    ai_ready = bool(event.get("ai_ready"))  # 保留 ai_readiness.py 的計算結果
    is_searchable = bool(search_ready and quality_ok and not manual_review)
    is_public_item = bool(line_ready and quality_ok and not manual_review)
    recommendation_ready = bool(line_ready and search_ready and not manual_review and quality_ok)
    published = bool(is_public_item and is_searchable and event.get("status", "active") == "active")

    event["line_card_ready"] = line_ready
    event["line_ready"] = line_ready
    event["search_ready"] = search_ready
    event["is_searchable"] = is_searchable
    event["is_public_item"] = is_public_item
    event["recommendation_ready"] = recommendation_ready
    event["published"] = published

    # 計算 missing_fields
    missing = []
    if not is_activity:
        missing.append("not_activity")
    if not has_title:
        missing.append("missing_title")
    if not has_date:
        missing.append("missing_date")
    if not has_location:
        missing.append("missing_location")
    if not has_url:
        missing.append("missing_source_url")
    if not has_desc:
        missing.append("missing_description")
    if invalid_date:
        missing.append("invalid_date_range")
    if is_expired:
        missing.append("expired")
    if manual_review:
        missing.append("manual_review_required")
    if not quality_ok:
        missing.append(f"quality_{event.get('quality_level', 'unknown')}")

    event["missing_fields"] = missing

    # 計算 status_reason（人類可讀）
    REASON_MAP = {
        "not_activity": "不是活動",
        "missing_title": "缺少標題",
        "missing_date": "缺少活動日期",
        "missing_location": "缺少地點",
        "missing_source_url": "缺少來源網址",
        "missing_description": "缺少說明內容",
        "invalid_date_range": "日期區間異常",
        "expired": "活動已過期",
        "manual_review_required": "需人工審核",
    }
    if not missing:
        if is_expired:
            event["status_reason"] = "已過期"
        elif event.get("status") == "inactive":
            event["status_reason"] = "已下架"
        elif published:
            event["status_reason"] = "已上架：可被 LINE 查詢與推薦"
        elif recommendation_ready:
            event["status_reason"] = "可推薦但尚未上架"
        elif line_ready:
            event["status_reason"] = "可顯示但不推薦"
        else:
            event["status_reason"] = "草稿"
    else:
        reasons = [REASON_MAP.get(m, m) for m in missing[:3]]
        event["status_reason"] = "；".join(reasons)

    # line_not_ready_reason（保持相容）
    event["line_not_ready_reason"] = None if line_ready else ",".join(missing or ["unknown"])

    # exclude_from_recommendation_reason（保持相容）
    if recommendation_ready:
        event["exclude_from_recommendation_reason"] = None
    elif not is_activity:
        event["exclude_from_recommendation_reason"] = "not_activity"
    elif is_expired:
        event["exclude_from_recommendation_reason"] = "expired"
    elif not has_date:
        event["exclude_from_recommendation_reason"] = "missing_date"
    elif not has_location:
        event["exclude_from_recommendation_reason"] = "missing_location"
    elif manual_review:
        event["exclude_from_recommendation_reason"] = "manual_review_required"
    else:
        event["exclude_from_recommendation_reason"] = "not_ready"

    return event
