from datetime import date, datetime
from zoneinfo import ZoneInfo


def _today():
    return datetime.now(ZoneInfo("Asia/Taipei")).date()


def _invalid_date_range(event):
    start = event.get("date_start")
    end = event.get("date_end")
    if not start or not end:
        return False
    try:
        return datetime.strptime(str(end), "%Y-%m-%d") < datetime.strptime(str(start), "%Y-%m-%d")
    except ValueError:
        return True


def _parse_iso_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _apply_freshness(event):
    today = _today()
    start = _parse_iso_date(event.get("date_start"))
    end = _parse_iso_date(event.get("date_end")) or start
    warnings = event.setdefault("quality_warnings", [])

    if end and end < today:
        event["status"] = "inactive"
        event["freshness_status"] = "expired"
        event["days_since_end"] = (today - end).days
        event["exclude_from_recommendation_reason"] = "expired"
        warnings.append("expired_event")
    elif start and start <= today <= (end or start):
        event["status"] = "active"
        event["freshness_status"] = "ongoing"
        event["days_until_start"] = 0
    elif start and start > today:
        event["status"] = "active"
        event["freshness_status"] = "upcoming"
        event["days_until_start"] = (start - today).days
    else:
        event.setdefault("status", "active")
        event["freshness_status"] = "unknown"

    event["quality_warnings"] = sorted(set(warnings))
    return event


def check_line_card_readiness(event):
    if not event: return event
    event = _apply_freshness(event)
    
    is_activity = bool(event.get("is_activity") or event.get("content_type") == "activity")
    official_url = event.get("official_detail_url") or event.get("source_url")
    has_location = bool(event.get("location") or event.get("district"))
    has_date = bool(event.get("date_start"))
    is_expired = event.get("freshness_status") == "expired" or event.get("status") == "inactive"
    invalid_date_range = _invalid_date_range(event) or "date_range_invalid" in event.get("quality_warnings", [])

    # Check for line_card_ready
    line_card_ready = bool(
        is_activity and event.get("title") and official_url and
        event.get("clean_description") and has_date and has_location and not invalid_date_range and not is_expired
    )
        
    # Check for search_ready
    search_ready = bool(is_activity and event.get("title") and official_url and has_date and has_location and not invalid_date_range and not is_expired)
        
    use_default_image = False
    if not event.get("poster_local_path"):
        use_default_image = True
        
    event["line_card_ready"] = line_card_ready
    event["line_ready"] = line_card_ready
    event["search_ready"] = search_ready
    event["is_public_item"] = bool(line_card_ready)
    event["use_default_image"] = use_default_image
    missing = []
    if not is_activity:
        missing.append("not_activity")
    if not event.get("title"):
        missing.append("missing_title")
    if not official_url:
        missing.append("missing_official_detail_url")
    if not event.get("clean_description"):
        missing.append("missing_clean_description")
    if not has_date:
        missing.append("missing_date_start")
    if invalid_date_range:
        missing.append("date_range_invalid")
    if is_expired:
        missing.append("expired")
    if not has_location:
        missing.append("missing_location_or_district")
    event["line_not_ready_reason"] = None if line_card_ready else ",".join(missing or ["unknown"])
    event["recommendation_ready"] = bool(line_card_ready and search_ready and not event.get("manual_review_required"))
    if not event["recommendation_ready"]:
        if not is_activity:
            event["exclude_from_recommendation_reason"] = "not_activity"
        elif is_expired:
            event["exclude_from_recommendation_reason"] = "expired"
        elif not has_date:
            event["exclude_from_recommendation_reason"] = "missing_date"
        elif not has_location:
            event["exclude_from_recommendation_reason"] = "missing_location"
        elif invalid_date_range:
            event["exclude_from_recommendation_reason"] = "invalid_date_range"
        elif event.get("manual_review_required"):
            event["exclude_from_recommendation_reason"] = "manual_review_required"
        else:
            event["exclude_from_recommendation_reason"] = "not_line_or_search_ready"
    
    return event
