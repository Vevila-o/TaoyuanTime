def calculate_quality_score(event):
    """
    Calculates a quality score from 0 to 100 based on field completeness.
    """
    if not event: return event
    
    score = 0
    warnings = event.setdefault("quality_warnings", [])
    
    if event.get("title"): score += 15
    if event.get("official_detail_url") or event.get("source_url"): score += 15
    if event.get("clean_description"): score += 15
    if event.get("is_activity") or event.get("is_event_candidate"): score += 15
    if event.get("date_start"): score += 15
    else: warnings.append("missing_activity_date")
    if event.get("location"): score += 10
    else: warnings.append("missing_location")
    if event.get("district"): score += 5
    if event.get("fee_parse_status") != "failed": score += 5
    if event.get("has_assets"): score += 5
    
    event["quality_score"] = score
    
    if not (event.get("is_activity") or event.get("content_type") == "activity"):
        if score >= 60:
            event["quality_level"] = "needs_review"
        elif score >= 40:
            event["quality_level"] = "low_quality"
        else:
            event["quality_level"] = "rejected"
    elif score >= 80:
        event["quality_level"] = "usable"
    elif score >= 60:
        event["quality_level"] = "needs_review"
    elif score >= 40:
        event["quality_level"] = "low_quality"
    else:
        event["quality_level"] = "rejected"

    event["quality_warnings"] = sorted(set(warnings))
    event["is_public_item"] = bool(
        event.get("line_card_ready")
        and event.get("status", "active") == "active"
        and event["quality_level"] == "usable"
        and not event.get("manual_review_required")
    )
        
    return event
