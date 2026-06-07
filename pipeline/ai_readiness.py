def check_ai_readiness(event):
    if not event: return event
    
    ai_ready = True
    ai_reject_reason = None
    ai_input_text = None
    
    raw_desc = event.get("description", "")
    clean_desc = event.get("clean_description", "")
    content_type = event.get("content_type", "")
    
    # Calculate noise ratio
    noise_ratio = 0
    if len(raw_desc) > 0:
        noise_ratio = 1 - (len(clean_desc) / len(raw_desc))
        
    if content_type != "activity" and not event.get("is_activity"):
        ai_ready = False
        ai_reject_reason = f"content_type is {content_type}, not activity"
    elif event.get("status") == "inactive" or event.get("freshness_status") == "expired":
        ai_ready = False
        ai_reject_reason = "Expired event"
    elif event.get("manual_review_required"):
        ai_ready = False
        ai_reject_reason = "Manual review required"
    elif not event.get("date_start"):
        ai_ready = False
        ai_reject_reason = "Missing event date"
    elif not (event.get("location") or event.get("district")):
        ai_ready = False
        ai_reject_reason = "Missing event location"
    elif not event.get("is_event_candidate", False):
        ai_ready = False
        ai_reject_reason = "Not an event candidate"
    elif len(clean_desc) < 80:
        ai_ready = False
        ai_reject_reason = f"Description too short ({len(clean_desc)} chars)"
    elif noise_ratio > 0.4:
        ai_ready = False
        ai_reject_reason = f"Description contains too much navigation noise (ratio: {noise_ratio:.2f})"
    elif not (event.get("official_detail_url") or event.get("source_url")):
        ai_ready = False
        ai_reject_reason = "Missing official source URL"
        
    if ai_ready:
        ai_input_text = f"Title: {event.get('title', '')}\\nDate: {event.get('date_start') or event.get('date_text', '')}\\nLocation: {event.get('location', '')}\\nSource: {event.get('official_detail_url') or event.get('source_url', '')}\\nDescription: {clean_desc}"
        
    event["ai_ready"] = ai_ready
    event["ai_reject_reason"] = ai_reject_reason
    event["ai_input_text"] = ai_input_text
    event["noise_ratio"] = round(noise_ratio, 2)
    
    return event
