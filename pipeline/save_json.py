import json
import os
import random
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pipeline.dedupe import apply_stable_ids


def _today():
    return datetime.now(ZoneInfo("Asia/Taipei")).date()


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _freshness_sort_key(event):
    today = _today()
    start = _parse_date(event.get("date_start"))
    end = _parse_date(event.get("date_end")) or start
    if end and end < today:
        return (3, (today - end).days, event.get("title") or "")
    if start and start <= today <= (end or start):
        return (0, 0, event.get("title") or "")
    if start and start > today:
        return (1, (start - today).days, event.get("title") or "")
    return (2, 999999, event.get("title") or "")


def _sort_events(events):
    return sorted(events, key=_freshness_sort_key)


def _normalize_output_contract(event):
    apply_stable_ids(event)
    for key in ("manual_review_required", "line_card_ready", "line_ready", "search_ready", "ai_ready", "recommendation_ready", "is_public_item", "is_searchable", "published", "front_ready", "ocr_ready"):
        event[key] = bool(event.get(key))
    event.setdefault("quality_warnings", [])
    event.setdefault("parse_warnings", [])
    event.setdefault("ocr_warnings", [])
    event.setdefault("missing_fields", [])
    event.setdefault("status_reason", "")
    return event


def _front_exclusion_reason(event):
    if event.get("quality_level") != "usable":
        return "not_usable"
    if not (event.get("is_activity") or event.get("content_type") == "activity"):
        return "not_activity"
    if event.get("manual_review_required"):
        return "manual_review"
    if not event.get("line_card_ready"):
        return event.get("line_not_ready_reason") or "line_not_ready"
    if not event.get("search_ready"):
        return "search_not_ready"
    if not event.get("ai_ready"):
        return event.get("ai_not_ready_reason") or "ai_not_ready"
    if not event.get("recommendation_ready"):
        return event.get("exclude_from_recommendation_reason") or "recommendation_not_ready"
    if not event.get("is_public_item"):
        return "not_public_item"
    return None


def _sync_front_facing_flags(event):
    """檢查 front_ready 狀態，但不再覆寫 readiness 欄位（由 compute_readiness 負責）。"""
    reason = _front_exclusion_reason(event)
    front_ready = reason is None
    event["front_ready"] = front_ready
    if not front_ready:
        event["front_exclusion_reason"] = reason
    return front_ready

def save_to_json(events, output_dir="scraping/data/output"):
    os.makedirs(output_dir, exist_ok=True)
    
    usable = []
    public_items = []
    recommendation_ready = []
    line_ready = []
    ai_ready = []
    needs_review = []
    rejected = []
    assets = []
    line_not_ready = []
    
    source_buckets = {} # For manual audit sample
    
    for event in events:
        _normalize_output_contract(event)
        source_key = event.get("source_key", "unknown")
        if source_key not in source_buckets:
            source_buckets[source_key] = []
            
        # Collect assets
        if event.get("extracted_assets"):
            for asset in event["extracted_assets"]:
                asset_copy = asset.copy()
                asset_copy["activity_hash"] = event.get("content_hash")
                asset_copy["source_key"] = source_key
                assets.append(asset_copy)
                
        is_activity = bool(event.get("is_activity") or event.get("content_type") == "activity")
        event["official_detail_url"] = event.get("official_detail_url") or event.get("source_url")
        event.setdefault("item_type", event.get("content_type", "unknown"))
        event.setdefault("status", "active")
        event.setdefault("quality_warnings", [])

        front_ready = _sync_front_facing_flags(event)
        has_ocr_candidate = any(
            asset.get("ocr_candidate") and asset.get("image_role") in {"poster", "main_visual"}
            for asset in event.get("extracted_assets") or []
        )
        if not front_ready:
            event["ocr_ready"] = False
            event["ocr_status"] = "skipped_not_front_pool"
        elif not event.get("ocr_status"):
            if not has_ocr_candidate:
                event["ocr_status"] = "skipped_no_image"

        # Classification
        if event.get("quality_level") == "usable" and is_activity:
            usable.append(event)
            if event.get("line_card_ready"):
                line_ready.append(event)
            if front_ready:
                ai_ready.append(event)
                recommendation_ready.append(event)
                public_items.append(event)
        elif event.get("quality_score", 0) < 40 or event.get("content_type") in ["unknown", "procurement", "recruitment"]:
            rejected.append(event)
        else:
            needs_review.append(event)
            
        # Add to bucket for sampling
        source_buckets[source_key].append(event)
        if not event.get("line_card_ready"):
            line_not_ready.append({
                "title": event.get("title"),
                "source_key": source_key,
                "source_url": event.get("source_url"),
                "official_detail_url": event.get("official_detail_url") or event.get("source_url"),
                "content_type": event.get("content_type"),
                "date_start": event.get("date_start"),
                "location": event.get("location"),
                "district": event.get("district"),
                "line_card_ready": event.get("line_card_ready"),
                "line_not_ready_reason": event.get("line_not_ready_reason"),
                "status_reason": event.get("status_reason"),
                "missing_fields": event.get("missing_fields", []),
            })
        
    # Write files
    files_to_write = {
        "activities_all.json": _sort_events(events),
        "activities_usable.json": _sort_events(usable),
        "activities_public.json": _sort_events(public_items),
        "activities_line_ready.json": _sort_events(line_ready),
        "activities_ai_ready.json": _sort_events(ai_ready),
        "ai_searchable_activities.json": _sort_events(ai_ready),
        "activities_recommendation_ready.json": _sort_events(recommendation_ready),
        "activities_needs_review.json": _sort_events(needs_review),
        "line_card_not_ready.json": line_not_ready,
        "rejected_items.json": rejected,
        "assets.json": assets
    }
    
    for filename, data in files_to_write.items():
        with open(os.path.join(output_dir, filename), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
    # Generate manual audit sample
    manual_sample = []
    
    categories_to_sample = [
        ("usable", lambda e: e.get("quality_level") == "usable"),
        ("line_card_ready", lambda e: e.get("line_card_ready")),
        ("ai_ready", lambda e: e.get("ai_ready")),
        ("needs_review", lambda e: e.get("quality_level") == "needs_review"),
        ("rejected", lambda e: e.get("quality_level") == "rejected")
    ]
    
    for source_key, items in source_buckets.items():
        source_sample = {
            "source_key": source_key,
            "samples": {},
            "missing_categories": []
        }
        
        for cat_name, condition in categories_to_sample:
            matching_items = [e for e in items if condition(e)]
            if matching_items:
                evt = random.choice(matching_items)
                source_sample["samples"][cat_name] = {
                    "title": evt.get("title"),
                    "source_url": evt.get("source_url"),
                    "content_type": evt.get("content_type"),
                    "date_start": evt.get("date_start"),
                    "location": evt.get("location"),
                    "line_card_ready": evt.get("line_card_ready"),
                    "search_ready": evt.get("search_ready"),
                    "ai_ready": evt.get("ai_ready"),
                    "quality_level": evt.get("quality_level"),
                    "clean_description_snippet": str(evt.get("clean_description", ""))[:300]
                }
            else:
                source_sample["missing_categories"].append(cat_name)
                
        manual_sample.append(source_sample)
            
    with open(os.path.join(output_dir, "manual_audit_sample.json"), "w", encoding="utf-8") as f:
        json.dump(manual_sample, f, ensure_ascii=False, indent=2)

def save_run_summary_json(summary, output_dir="scraping/data/output"):
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "crawler_run_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
