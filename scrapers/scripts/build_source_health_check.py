import json
import os
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


OUTPUT_DIR = os.path.join("scraping", "data", "output")
EVENTS_PATH = os.path.join(OUTPUT_DIR, "activities_all.json")
HEALTH_REPORT_PATH = os.path.join(OUTPUT_DIR, "health_report.json")
SOURCE_SUMMARY_PATH = os.path.join(OUTPUT_DIR, "source_quality_summary.json")
SOURCE_HEALTH_PATH = os.path.join(OUTPUT_DIR, "source_health_check.json")


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def pct(numerator, denominator):
    if denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, 1)


def is_activity(event):
    return bool(event.get("is_activity") or event.get("item_type") == "activity" or event.get("content_type") == "activity")


def non_empty(value):
    return value is not None and str(value).strip() != ""


def line_ready(event):
    return bool((event.get("line_card_ready") or event.get("line_ready")) and not_expired(event))


def parse_date(value):
    if not value:
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


def official_url(event):
    return event.get("official_detail_url") or event.get("source_url") or ""


def has_official_url(event):
    url = official_url(event)
    parsed = urlparse(url)
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
    return parsed.scheme == "https" and (host in official_hosts or host.endswith(".tycg.gov.tw"))


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
        and has_official_url(event)
        and not event.get("manual_review_required")
    )


def public_item(event):
    if "is_public_item" in event:
        return bool(event.get("is_public_item") and not_expired(event))
    return bool(
        line_ready(event)
        and has_official_url(event)
        and event.get("quality_level") in {"usable", "needs_review"}
        and not_expired(event)
        and not event.get("manual_review_required")
    )


def health_level(source):
    if source["raw_total"] == 0:
        return "no_data"
    if source["total"] == 0 and source["raw_total"] > 0:
        return "deduped_only"
    if source["source_key"] == "travel_news":
        return "filtered_only"
    if source["serviceable_active"] == 0 and source["expired_items"] > 0 and source["expired_rate"] >= 50:
        return "historical_only"
    if (
        source["active_activity_purity"] >= 90
        and source["public_items"] >= 10
        and source["recommendation_ready"] >= 10
        and source["avg_score"] >= 80
    ):
        return "primary_ready"
    if source["active_activity_purity"] >= 80 and source["serviceable_active"] >= 1 and source["avg_score"] >= 75:
        return "supplementary_ready"
    if source["active_activity_purity"] >= 60 and (source["serviceable_active"] > 0 or source["usable"] > 0):
        return "filtered_only"
    return "needs_attention"


def recommended_actions(source):
    warnings = set(source.get("warnings", []))
    actions = []
    if source["source_key"] == "travel_openapi":
        actions.append("保留為桃園觀光主來源；缺日期的 Activity 只進 needs_review，不進 recommendation。")
    if source["source_key"] == "travel_news":
        actions.append("只作 filtered 補充，不當主來源。")
    if source["health_level"] == "deduped_only":
        actions.append("來源有抓到資料但全部被跨來源去重合併，屬正常鏡像來源行為。")
    if source["expired_rate"] >= 50 and source["expired_items"] > 0:
        actions.append("來源多為歷史活動，保留全量但不納入 AI/推薦覆蓋率分母。")
    if source["activity_purity"] < 75:
        actions.append("來源混入非活動內容，優先補分類規則或來源層過濾。")
    if source["active_line_ready_rate"] < 70 and source["active_activity_purity"] >= 80 and source["active_total"] > 0:
        actions.append("主要缺口是日期/地點不足，優先補 structured location/date parser。")
    if source["public_items"] == 0 and source["usable"] > 0:
        actions.append("可用項目未進 public，檢查 manual_review_required、地點、日期與官方 URL 條件。")
    if "small_sample_size" in warnings:
        actions.append("樣本數偏小，先維持 supplementary/filtered。")
    if "poster_not_validated" in warnings:
        actions.append("此來源未找到合格 poster/main_visual 或海報驗證不足；前台仍可使用 default image，不阻擋 MVP。")
    return actions or ["目前狀態可接受，維持現有策略。"]


def build_source_health():
    events = load_json(EVENTS_PATH, [])
    report = load_json(HEALTH_REPORT_PATH, {})
    source_summary = load_json(SOURCE_SUMMARY_PATH, [])
    summary_by_key = {item.get("source_key"): item for item in source_summary if item.get("source_key")}
    report_by_key = {item.get("source_key"): item for item in report.get("source_quality_summary", []) if item.get("source_key")}

    events_by_source = defaultdict(list)
    for event in events:
        events_by_source[event.get("source_key") or "unknown"].append(event)

    sources = []
    for key in sorted(set(events_by_source) | set(summary_by_key) | set(report_by_key)):
        rows = events_by_source.get(key, [])
        total = len(rows)
        activities = sum(1 for event in rows if is_activity(event))
        active_all = [event for event in rows if not_expired(event)]
        active_rows = [event for event in rows if is_activity(event) and not_expired(event)]
        active_total = len(active_rows)
        expired = sum(1 for event in rows if is_activity(event) and not not_expired(event))
        serviceable = sum(1 for event in rows if is_serviceable_active_activity(event))
        usable = sum(1 for event in rows if event.get("quality_level") == "usable")
        line = sum(1 for event in rows if line_ready(event))
        active_line = sum(1 for event in rows if line_ready(event) and is_activity(event))
        ai = sum(1 for event in rows if event.get("ai_ready") and is_serviceable_active_activity(event))
        public = sum(1 for event in rows if public_item(event))
        recommendation = sum(1 for event in rows if event.get("recommendation_ready") and not_expired(event))
        date_ready = sum(1 for event in rows if event.get("date_start"))
        location_ready = sum(1 for event in rows if event.get("location") or event.get("district"))
        official = sum(1 for event in rows if has_official_url(event))
        active_date_ready = sum(1 for event in active_rows if has_date(event))
        active_location_ready = sum(1 for event in active_rows if has_location(event))
        active_official = sum(1 for event in active_rows if has_official_url(event))
        score = round(sum(event.get("quality_score", 0) for event in rows) / total, 2) if total else 0
        source_info = summary_by_key.get(key, {})
        report_info = report_by_key.get(key, {})
        raw_total = int(source_info.get("items_created") or 0)
        list_items_found = int(source_info.get("list_items_found") or 0)
        status = source_info.get("status") or report_info.get("status")
        major_issues = source_info.get("major_issues") or []

        parse_status = "ok"
        if status == "failed":
            parse_status = "fetch_failed"
        elif any(str(issue).startswith("rss_list_fetch_failed") for issue in major_issues):
            parse_status = "fetch_failed"
        elif "Max runtime reached" in major_issues:
            parse_status = "runtime_cutoff"
        elif raw_total == 0 and list_items_found > 0:
            parse_status = "no_items_created"
        elif raw_total == 0 and list_items_found == 0:
            parse_status = "no_list_items"
        elif raw_total > 0 and total == 0:
            parse_status = "deduped_out"

        source = {
            "source_key": key,
            "source_name": source_info.get("source_name") or report_info.get("source_name"),
            "source_priority": source_info.get("source_priority") or report_info.get("source_priority"),
            "fetcher_type": source_info.get("fetcher_type") or report_info.get("fetcher_type"),
            "raw_total": raw_total,
            "list_items_found": list_items_found,
            "total": total,
            "activities": activities,
            "activity_purity": pct(activities, total),
            "active_total": active_total,
            "active_activity_purity": pct(active_total, len(active_all)),
            "expired_items": expired,
            "expired_rate": pct(expired, activities),
            "serviceable_active": serviceable,
            "serviceable_active_rate": pct(serviceable, active_total),
            "usable": usable,
            "usable_rate": pct(usable, total),
            "line_ready": line,
            "line_ready_rate": pct(line, total),
            "active_line_ready_rate": pct(active_line, active_total),
            "ai_ready": ai,
            "ai_ready_rate": pct(ai, serviceable),
            "public_items": public,
            "recommendation_ready": recommendation,
            "date_ready_rate": pct(date_ready, total),
            "location_ready_rate": pct(location_ready, total),
            "official_url_rate": pct(official, total),
            "active_date_ready_rate": pct(active_date_ready, active_total),
            "active_location_ready_rate": pct(active_location_ready, active_total),
            "active_official_url_rate": pct(active_official, active_total),
            "avg_score": score,
            "health_report_level": report_info.get("mvp_recommendation_level"),
            "warnings": report_info.get("quality_warnings", []),
            "source_status": status,
            "parse_status": parse_status,
            "major_issues": major_issues,
        }
        source["health_level"] = health_level(source)
        source["recommended_action"] = recommended_actions(source)
        sources.append(source)

    return {
        "generated_from": {
            "activities_all": EVENTS_PATH,
            "health_report": HEALTH_REPORT_PATH,
            "source_quality_summary": SOURCE_SUMMARY_PATH,
        },
        "overall": {
            "health_report_status": report.get("overall_status"),
            "events": report.get("totals", {}).get("events"),
            "raw_activity_rate": report.get("totals", {}).get("raw_activity_rate"),
            "recommendation_pool_purity": report.get("totals", {}).get("recommendation_pool_purity"),
        },
        "sources": sources,
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(SOURCE_HEALTH_PATH, "w", encoding="utf-8") as f:
        json.dump(build_source_health(), f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(SOURCE_HEALTH_PATH)


if __name__ == "__main__":
    main()
