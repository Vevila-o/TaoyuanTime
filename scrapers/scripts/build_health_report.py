import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


OUTPUT_DIR = os.path.join("scraping", "data", "output")
EVENTS_PATH = os.path.join(OUTPUT_DIR, "activities_all.json")
RUN_SUMMARY_PATH = os.path.join(OUTPUT_DIR, "crawler_run_summary.json")
SOURCE_SUMMARY_PATH = os.path.join(OUTPUT_DIR, "source_quality_summary.json")
DB_PATH = os.path.join(OUTPUT_DIR, "activities.db")
HEALTH_REPORT_PATH = os.path.join(OUTPUT_DIR, "health_report.json")

PRIMARY_SOURCES = {"travel_openapi", "culture", "tycg_events"}
SUPPLEMENTARY_SOURCES = {"agriculture"}
FILTERED_SOURCES = {"dst", "economic", "youth", "hakka", "travel_news"}
EXCLUDED_SOURCES = {"tycg_news", "travel"}
MVP_EVALUATED_SOURCES = PRIMARY_SOURCES | SUPPLEMENTARY_SOURCES


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def pct(numerator, denominator):
    if denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, 1)


def status_for(rate, pass_threshold, warn_threshold=None):
    if warn_threshold is None:
        warn_threshold = pass_threshold * 0.9
    if rate >= pass_threshold:
        return "PASS"
    if rate >= warn_threshold:
        return "WARN"
    return "FAIL"


def non_empty(value):
    return value is not None and str(value).strip() != ""


def valid_official_url(value):
    if not non_empty(value):
        return False
    parsed = urlparse(str(value))
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    host = parsed.netloc.lower()
    official_hosts = {
        "tycg.gov.tw",
        "www.tycg.gov.tw",
        "travel.tycg.gov.tw",
        "culture.tycg.gov.tw",
        "agriculture.tycg.gov.tw",
        "youth.tycg.gov.tw",
        "edb.tycg.gov.tw",
        "www.hakka.tycg.gov.tw",
        "hakka.tycg.gov.tw",
        "taoyuan.94i.club",
        "www.dst.tycg.gov.tw",
        "animal.tycg.gov.tw",
        "www.typl.gov.tw",
        "wem.tycg.gov.tw",
        "tmofa.tycg.gov.tw",
        "event.culture.tw",
    }
    return host in official_hosts or host.endswith(".tycg.gov.tw")


def is_activity(event):
    return bool(event.get("is_activity")) or event.get("item_type") == "activity" or event.get("content_type") == "activity"


def official_url(event):
    return event.get("official_detail_url") or event.get("source_url")


def parse_date(value):
    if not non_empty(value):
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def today():
    return datetime.now(ZoneInfo("Asia/Taipei")).date()


def not_expired(event):
    if event.get("status") == "inactive" or event.get("freshness_status") == "expired":
        return False
    end = parse_date(event.get("date_end")) or parse_date(event.get("date_start"))
    if not end:
        return True
    return end >= today()


def has_date(event):
    return non_empty(event.get("date_start"))


def has_location(event):
    return non_empty(event.get("location")) or non_empty(event.get("district"))


def is_serviceable_active_activity(event):
    return bool(
        is_activity(event)
        and not_expired(event)
        and has_date(event)
        and has_location(event)
        and valid_official_url(official_url(event))
        and not event.get("manual_review_required")
        and "date_range_invalid" not in event.get("quality_warnings", [])
    )


def front_ready(event):
    return bool(
        is_serviceable_active_activity(event)
        and line_ready(event)
        and event.get("search_ready")
        and event.get("ai_ready")
        and recommendation_ready(event)
        and public_item(event)
    )


def line_ready(event):
    return bool((event.get("line_ready") or event.get("line_card_ready")) and not_expired(event))


def recommendation_ready(event):
    if "recommendation_ready" in event:
        return bool(event.get("recommendation_ready") and not_expired(event))
    return bool(
        is_activity(event)
        and line_ready(event)
        and event.get("search_ready")
        and non_empty(event.get("date_start"))
        and (non_empty(event.get("location")) or non_empty(event.get("district")))
        and valid_official_url(official_url(event))
        and not_expired(event)
        and not event.get("manual_review_required")
    )


def public_item(event):
    if "is_public_item" in event:
        return bool(event.get("is_public_item") and not_expired(event))
    return bool(
        line_ready(event)
        and valid_official_url(official_url(event))
        and event.get("quality_level") in {"usable", "needs_review"}
        and not event.get("manual_review_required")
    )


def metric(name, passed, total, threshold, description):
    rate = pct(passed, total)
    return {
        "name": name,
        "status": status_for(rate, threshold),
        "passed": passed,
        "total": total,
        "rate": rate,
        "threshold": threshold,
        "description": description,
    }


def db_schema_ok():
    if not os.path.exists(DB_PATH):
        return False, ["activities.db not found"]
    required = {
        "source_key", "source_url", "title", "date_start", "date_end",
        "location", "district", "quality_score", "quality_level",
        "line_card_ready", "search_ready", "ai_ready",
    }
    preferred = {
        "item_type", "is_activity", "line_ready", "recommendation_ready",
        "official_detail_url", "fee_type", "quality_warnings",
        "exclude_from_recommendation_reason",
    }
    conn = sqlite3.connect(DB_PATH)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(activities)").fetchall()}
        total = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    finally:
        conn.close()
    issues = []
    missing_required = sorted(required - columns)
    missing_preferred = sorted(preferred - columns)
    if total == 0:
        issues.append("activities table is empty")
    if missing_required:
        issues.append("missing required columns: " + ", ".join(missing_required))
    if missing_preferred:
        issues.append("missing quality-layer columns: " + ", ".join(missing_preferred))
    return not missing_required and total > 0, issues


def normalize_source_summary(source_summary, events):
    events_by_source = defaultdict(list)
    for event in events:
        events_by_source[event.get("source_key") or "unknown"].append(event)

    known_keys = set(events_by_source)
    known_keys.update(item.get("source_key") for item in source_summary if item.get("source_key"))

    summary_by_key = {item.get("source_key"): dict(item) for item in source_summary if item.get("source_key")}
    normalized = []
    for key in sorted(known_keys):
        source_events = events_by_source.get(key, [])
        item = summary_by_key.get(key, {"source_key": key, "status": "success" if source_events else "unknown"})
        items_created = item.get("items_created") or len(source_events)
        metric_total = len(source_events) or items_created
        activity_count = sum(1 for event in source_events if is_activity(event))
        public_count = sum(1 for event in source_events if public_item(event))
        rec_count = sum(1 for event in source_events if recommendation_ready(event))
        line_count = sum(1 for event in source_events if line_ready(event))
        ai_count = sum(1 for event in source_events if event.get("ai_ready") and is_activity(event))
        official_count = sum(1 for event in source_events if valid_official_url(official_url(event)))
        date_count = sum(1 for event in source_events if non_empty(event.get("date_start")))
        location_count = sum(1 for event in source_events if non_empty(event.get("location")) or non_empty(event.get("district")))

        warnings = set(item.get("quality_warnings", []))
        major_issues = set(item.get("major_issues", []))
        if items_created == 0 and item.get("status") != "failed":
            item["status"] = "no_data"
            major_issues.add("no_items_created")
        if items_created and item.get("poster_valid_count", 0) == 0:
            warnings.add("poster_not_validated")
        if 0 < items_created < 10:
            warnings.add("small_sample_size")
        if key in FILTERED_SOURCES and pct(activity_count, metric_total) < 60:
            warnings.add("low_activity_purity")
        if key in EXCLUDED_SOURCES and activity_count == 0:
            major_issues.add("no_activity_items")

        active_count = sum(1 for event in source_events if is_activity(event) and not_expired(event))
        expired_count = sum(1 for event in source_events if is_activity(event) and not not_expired(event))
        serviceable_count = sum(1 for event in source_events if is_serviceable_active_activity(event))
        active_line_count = sum(1 for event in source_events if line_ready(event) and is_activity(event))
        active_ai_count = sum(1 for event in source_events if event.get("ai_ready") and is_serviceable_active_activity(event))
        active_date_count = sum(1 for event in source_events if is_activity(event) and not_expired(event) and has_date(event))
        active_location_count = sum(1 for event in source_events if is_activity(event) and not_expired(event) and has_location(event))
        active_official_count = sum(1 for event in source_events if is_activity(event) and not_expired(event) and valid_official_url(official_url(event)))

        line_ready_rate = line_count / metric_total if metric_total else 0
        date_success_rate = date_count / metric_total if metric_total else 0
        location_ready_rate = location_count / metric_total if metric_total else 0
        official_rate = official_count / metric_total if metric_total else 0
        serviceable_rate = serviceable_count / active_count if active_count else 0
        active_line_ready_rate = active_line_count / active_count if active_count else 0
        active_ai_ready_rate = active_ai_count / serviceable_count if serviceable_count else 0
        active_date_ready_rate = active_date_count / active_count if active_count else 0
        active_location_ready_rate = active_location_count / active_count if active_count else 0
        active_official_rate = active_official_count / active_count if active_count else 0
        recommended = bool(
            serviceable_count > 0
            and active_line_ready_rate >= 0.9
            and active_date_ready_rate >= 0.9
            and active_location_ready_rate >= 0.8
            and active_official_rate == 1.0
        )
        level = item.get("mvp_recommendation_level")
        if key == "travel_openapi":
            recommended = serviceable_count > 0 and official_rate == 1.0
            level = "primary" if public_count >= 10 and rec_count >= 10 and official_rate == 1.0 else "supplementary" if recommended else "not_recommended"
        elif key in PRIMARY_SOURCES and recommended and items_created >= 10:
            level = "primary"
        elif key in (PRIMARY_SOURCES | SUPPLEMENTARY_SOURCES) and recommended:
            level = "supplementary"
        elif key in FILTERED_SOURCES and (recommended or activity_count > 0):
            recommended = activity_count > 0
            level = "filtered"
        elif key in EXCLUDED_SOURCES:
            recommended = False
            level = "not_recommended"
        elif not level:
            level = "not_recommended"

        item.update({
            "items_created": items_created,
            "activity_count": activity_count,
            "active_activity_count": active_count,
            "expired_activity_count": expired_count,
            "serviceable_active_count": serviceable_count,
            "public_item_count": public_count,
            "recommendation_ready_count": rec_count,
            "line_ready_count": line_count,
            "ai_ready_count": ai_count,
            "official_detail_url_count": official_count,
            "date_parse_success_rate": round(date_count / metric_total, 2) if metric_total else 0,
            "raw_location_parse_success_rate": item.get("location_parse_success_rate", round(location_count / metric_total, 2) if metric_total else 0),
            "final_location_ready_rate": round(location_count / metric_total, 2) if metric_total else 0,
            "official_detail_url_rate": round(official_count / metric_total, 2) if metric_total else 0,
            "line_ready_rate": round(line_ready_rate, 2) if metric_total else 0,
            "serviceable_active_rate": round(serviceable_rate, 2) if active_count else 0,
            "active_line_ready_rate": round(active_line_ready_rate, 2) if active_count else 0,
            "active_ai_ready_rate": round(active_ai_ready_rate, 2) if serviceable_count else 0,
            "active_date_ready_rate": round(active_date_ready_rate, 2) if active_count else 0,
            "active_location_ready_rate": round(active_location_ready_rate, 2) if active_count else 0,
            "active_official_detail_url_rate": round(active_official_rate, 2) if active_count else 0,
            "activity_purity": round(activity_count / metric_total, 2) if metric_total else 0,
            "quality_warnings": sorted(warnings),
            "major_issues": sorted(major_issues),
            "recommended_for_mvp_by_metrics": recommended,
            "mvp_recommendation_level": level,
        })
        normalized.append(item)
    return normalized


def build_report():
    events = load_json(EVENTS_PATH, [])
    run_summary = load_json(RUN_SUMMARY_PATH, {})
    source_summary = normalize_source_summary(load_json(SOURCE_SUMMARY_PATH, []), events)
    failed_source_keys = [
        item.get("source_key")
        for item in source_summary
        if item.get("source_key") and item.get("status") == "failed"
    ]
    critical_failed_sources = [
        key for key in failed_source_keys
        if key in (PRIMARY_SOURCES | SUPPLEMENTARY_SOURCES)
    ]
    filtered_failed_sources = [
        key for key in failed_source_keys
        if key in FILTERED_SOURCES
    ]

    activities = [event for event in events if is_activity(event)]
    active_activities = [event for event in activities if not_expired(event)]
    serviceable_active_activities = [event for event in active_activities if is_serviceable_active_activity(event)]
    mvp_evaluated_activities = [
        event for event in serviceable_active_activities
        if (event.get("source_key") or "unknown") in MVP_EVALUATED_SOURCES
    ]
    public_items = [event for event in events if public_item(event)]
    recommendation_items = [event for event in events if recommendation_ready(event)]
    ai_output_items = [event for event in events if event.get("ai_ready") and is_activity(event) and not_expired(event)]
    recommendation_activity_items = [event for event in recommendation_items if is_activity(event)]
    ai_ready_activity_items = [event for event in serviceable_active_activities if event.get("ai_ready")]
    expired_items = [event for event in activities if not not_expired(event)]
    needs_review_or_incomplete_items = [
        event for event in active_activities
        if not is_serviceable_active_activity(event)
    ]

    raw_activity_rate = pct(len(activities), len(events))
    recommendation_pool_purity = pct(len(recommendation_activity_items), len(recommendation_items))
    public_ids = {event.get("activity_uid") for event in public_items}
    recommendation_ids = {event.get("activity_uid") for event in recommendation_items}
    ai_ids = {event.get("activity_uid") for event in ai_output_items}
    front_pool_aligned = public_ids == recommendation_ids == ai_ids
    db_ok, db_issues = db_schema_ok()

    health_metrics = [
        {
            "name": "crawler_run_completed",
            "status": "PASS" if len(events) > 0 and not critical_failed_sources else "FAIL",
            "description": "爬蟲需產生資料，且 primary/supplementary 來源不得失敗；filtered-only 來源失敗列為警告。",
            "details": {
                "run_id": run_summary.get("run_id"),
                "success_sources": run_summary.get("success_sources"),
                "failed_sources": run_summary.get("failed_sources"),
                "failed_source_keys": failed_source_keys,
                "critical_failed_sources": critical_failed_sources,
                "filtered_failed_sources": filtered_failed_sources,
                "total_items": len(events),
            },
        },
        {
            "name": "database_output_ready",
            "status": "PASS" if db_ok else "FAIL",
            "description": "SQLite activities 表需可供查詢與匯入使用。",
            "details": {"issues": db_issues},
        },
        {
            "name": "raw_activity_purity",
            "status": status_for(raw_activity_rate, 75),
            "passed": len(activities),
            "total": len(events),
            "rate": raw_activity_rate,
            "threshold": 75,
            "description": "原始抓取資料以活動為主；若低於門檻，需確認推薦池是否已完成過濾。",
        },
        {
            "name": "recommendation_pool_purity",
            "status": status_for(recommendation_pool_purity, 95),
            "passed": len(recommendation_activity_items),
            "total": len(recommendation_items),
            "rate": recommendation_pool_purity,
            "threshold": 95,
            "description": "推薦池不得含公告、回顧或資源頁。",
        },
        {
            "name": "front_pool_alignment",
            "status": "PASS" if front_pool_aligned else "FAIL",
            "passed": len(public_ids & recommendation_ids & ai_ids),
            "total": len(public_ids | recommendation_ids | ai_ids),
            "rate": pct(len(public_ids & recommendation_ids & ai_ids), len(public_ids | recommendation_ids | ai_ids)),
            "threshold": 100,
            "description": "LINE 公開池、推薦池與 AI 搜尋池必須使用同一組活動 ID，避免使用者認知斷層。",
        },
    ]

    basic_function_metrics = [
        metric("line_card_ready", sum(1 for e in public_items if line_ready(e)), len(public_items), 95, "公開資料需能渲染 LINE 卡片。"),
        metric("official_detail_url", sum(1 for e in public_items if valid_official_url(official_url(e))), len(public_items), 100, "公開資料必須回到官方或授權來源。"),
        metric("date_calendar_ready", sum(1 for e in public_items if non_empty(e.get("date_start"))), len(public_items), 95, "行事曆與日期排序需可解析日期。"),
        metric("location_ready", sum(1 for e in public_items if non_empty(e.get("location")) or non_empty(e.get("district"))), len(public_items), 90, "地點或行政區需可供查詢與篩選。"),
        metric("search_ready", sum(1 for e in public_items if e.get("search_ready")), len(public_items), 95, "公開查詢與 API 搜尋需要 search_ready。"),
        metric("fee_tag_ready", sum(1 for e in public_items if non_empty(e.get("fee_type")) or non_empty(e.get("fee_text")) or e.get("fee_parse_status") != "failed"), len(public_items), 85, "活動卡片需要費用標示，至少能標為免費、付費或未標示。"),
    ]

    ai_function_metrics = [
        metric("ai_input_ready", sum(1 for e in serviceable_active_activities if e.get("ai_ready") and non_empty(e.get("ai_input_text") or e.get("clean_description"))), len(serviceable_active_activities), 75, "AI 摘要只評估可服務、未過期且欄位完整的活動。"),
        metric("anti_hallucination_grounding", sum(1 for e in activities if valid_official_url(official_url(e)) and non_empty(e.get("clean_description"))), len(activities), 95, "AI 回覆需可追溯官方 URL 與資料庫內容。"),
        metric("recommendation_ready", sum(1 for e in mvp_evaluated_activities if recommendation_ready(e)), len(mvp_evaluated_activities), 80, "個人化推薦只評估 MVP 來源中可服務、未過期且欄位完整的活動。"),
        metric("recommendation_pool_purity", len(recommendation_activity_items), len(recommendation_items), 95, "推薦池不得含公告、回顧或資源頁。"),
    ]

    by_source = defaultdict(lambda: {"total": 0, "activities": 0, "active_activities": 0, "expired_items": 0, "serviceable_active_items": 0, "public_items": 0, "recommendation_items": 0, "line_ready": 0, "ai_ready": 0})
    for event in events:
        key = event.get("source_key") or "unknown"
        by_source[key]["total"] += 1
        by_source[key]["activities"] += int(is_activity(event))
        by_source[key]["active_activities"] += int(is_activity(event) and not_expired(event))
        by_source[key]["expired_items"] += int(is_activity(event) and not not_expired(event))
        by_source[key]["serviceable_active_items"] += int(is_serviceable_active_activity(event))
        by_source[key]["public_items"] += int(public_item(event))
        by_source[key]["recommendation_items"] += int(recommendation_ready(event))
        by_source[key]["line_ready"] += int(line_ready(event))
        by_source[key]["ai_ready"] += int(bool(event.get("ai_ready")) and is_serviceable_active_activity(event))

    mvp_sources = {"primary": [], "supplementary": [], "filtered": [], "excluded": []}
    remaining_warnings = []
    for source in source_summary:
        key = source.get("source_key")
        level = source.get("mvp_recommendation_level")
        if level == "primary":
            mvp_sources["primary"].append(key)
        elif level == "supplementary":
            mvp_sources["supplementary"].append(key)
        elif level == "filtered":
            mvp_sources["filtered"].append(key)
        else:
            mvp_sources["excluded"].append(key)
        for warning in source.get("quality_warnings", []):
            remaining_warnings.append({"name": warning, "source_key": key, "status": "WARN"})

    if raw_activity_rate < 75 and recommendation_pool_purity >= 95:
        remaining_warnings.append({
            "name": "raw_activity_purity",
            "status": "WARN",
            "description": "原始抓取資料仍包含公告或非活動項目，但推薦池已完成過濾。",
        })
    for key in filtered_failed_sources:
        remaining_warnings.append({
            "name": "filtered_source_failed",
            "source_key": key,
            "status": "WARN",
            "description": "filtered-only 來源本次抓取失敗，不影響公開池、AI 池或推薦池驗收。",
        })

    failed_sections = []
    if any(m["status"] == "FAIL" for m in health_metrics if m["name"] != "raw_activity_purity"):
        failed_sections.append("health")
    if any(m["status"] == "FAIL" for m in basic_function_metrics):
        failed_sections.append("basic_function_metrics")
    if any(m["status"] == "FAIL" for m in ai_function_metrics):
        failed_sections.append("ai_function_metrics")

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "overall_status": "PASS" if not failed_sections else "FAIL",
        "failed_sections": failed_sections,
        "input_files": {
            "events": EVENTS_PATH,
            "run_summary": RUN_SUMMARY_PATH,
            "source_summary": SOURCE_SUMMARY_PATH,
            "database": DB_PATH,
        },
        "totals": {
            "events": len(events),
            "activities": len(activities),
            "public_items": len(public_items),
            "recommendation_items": len(recommendation_items),
            "ai_ready_activity_items": len(ai_ready_activity_items),
            "active_activity_items": len(active_activities),
            "serviceable_active_items": len(serviceable_active_activities),
            "expired_items": len(expired_items),
            "needs_review_or_incomplete_items": len(needs_review_or_incomplete_items),
            "activity_rate": raw_activity_rate,
            "raw_activity_rate": raw_activity_rate,
            "recommendation_pool_purity": recommendation_pool_purity,
        },
        "health_metrics": health_metrics,
        "basic_function_metrics": basic_function_metrics,
        "ai_function_metrics": ai_function_metrics,
        "by_source": dict(sorted(by_source.items())),
        "source_quality_summary": source_summary,
        "mvp_sources": mvp_sources,
        "remaining_warnings": remaining_warnings,
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report = build_report()
    with open(HEALTH_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(HEALTH_REPORT_PATH)
    print(f"overall_status={report['overall_status']}")


if __name__ == "__main__":
    main()
