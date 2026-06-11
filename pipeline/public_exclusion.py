import re


CONTENT_TYPE_LABELS = {
    "activity": "活動",
    "news": "新聞稿",
    "announcement": "公告",
    "admin_notice": "行政通知",
    "penalty_list": "裁罰名單",
    "venue_notice": "場地公告",
    "policy": "政策宣導",
    "procurement": "採購招標",
    "recruitment": "徵才招募",
    "recap": "成果回顧",
    "place_or_resource": "地點或資源",
    "unknown": "不確定",
}


NON_ACTIVITY_RULES = (
    ("penalty_list", "penalty_list", ("裁罰", "罰鍰", "違反", "非法旅宿", "名單至")),
    ("venue_notice", "venue_notice", ("暫停開放", "休館公告", "開館事宜", "閉館", "場地公告")),
    ("admin_notice", "admin_notice", ("公差假", "核予", "請貴校", "函", "轉知", "公告周知", "公文")),
    ("procurement", "procurement", ("招標", "採購", "決算", "財報")),
    ("recruitment", "recruitment", ("徵才", "招募", "甄選結果", "錄取名單", "面試甄選")),
    ("policy", "policy", ("法規", "辦法", "作業要點", "政策宣導", "補助公告", "補助", "光電指引", "修法")),
    ("news", "news", ("新聞稿", "新聞", "參訪", "市長", "宣傳", "廣告", "海外再掀話題", "新典範", "供應鏈", "接軌", "商機", "征戰", "出訪")),
    ("recap", "recap", ("成果", "圓滿落幕", "活動回顧", "順利完成", "吸引超過")),
    ("place_or_resource", "place_or_resource", ("清冊", "懶人包", "得獎名單", "說明會紀錄")),
)

STRUCTURED_ACTIVITY_TERMS = (
    "活動日期",
    "活動地址",
    "活動地點",
    "活動時間",
    "展覽期間",
    "開放報名",
    "開放參加",
    "自由入場",
    "歡迎參加",
)

ACTIVITY_INVITATION_TERMS = (
    "講座",
    "課程",
    "展覽",
    "音樂會",
    "市集",
    "工作坊",
    "導覽",
    "體驗",
    "演出",
    "表演",
    "夏令營",
    "營隊",
)


def public_exclusion_for_text(title="", description="", metadata=""):
    text = " ".join(str(part or "") for part in (title, description, metadata))
    title = str(title or "")
    if any(term in text for term in ("商機", "征戰", "出訪")):
        return "news", "news_unconditional"

    has_structured_activity = any(term in text for term in STRUCTURED_ACTIVITY_TERMS)
    has_invitation = any(term in text for term in ACTIVITY_INVITATION_TERMS)

    for content_type, reason, terms in NON_ACTIVITY_RULES:
        if not any(term in text for term in terms):
            continue
        if content_type in {"penalty_list", "admin_notice", "procurement", "recruitment", "venue_notice"}:
            return content_type, reason
        if has_structured_activity and has_invitation:
            continue
        return content_type, reason

    if "公告" in title and not (has_structured_activity and has_invitation):
        return "announcement", "announcement"

    if re.search(r"名單\s*(至|截至|公告)", text) and not has_structured_activity:
        return "place_or_resource", "resource_list"

    return None, ""


def apply_public_exclusion(event):
    if not event:
        return event

    content_type, reason = public_exclusion_for_text(
        event.get("title", ""),
        " ".join([
            str(event.get("clean_description") or ""),
            str(event.get("description") or ""),
            str(event.get("raw_content") or ""),
        ]),
        event.get("enriched_metadata_text", ""),
    )
    if content_type:
        event["content_type"] = content_type
        event["item_type"] = content_type
        event["is_activity"] = False
        event["is_event_candidate"] = False
        event["excluded_from_public"] = True
        event["exclude_reason"] = reason
        event["is_public_item"] = False
        event["line_ready"] = False
        event["line_card_ready"] = False
        event["search_ready"] = False
        event["ai_ready"] = False
        event["recommendation_ready"] = False
        event["published"] = False
        event["final_state"] = "non_activity"
        warnings = event.get("quality_warnings") or []
        if not isinstance(warnings, list):
            warnings = [str(warnings)]
            event["quality_warnings"] = warnings
        if "excluded_from_public" not in warnings:
            warnings.append("excluded_from_public")
    else:
        event.setdefault("excluded_from_public", False)
        event.setdefault("exclude_reason", "")
    return event


def final_state_for_event(event):
    if event.get("excluded_from_public"):
        return "non_activity" if not event.get("is_activity") else "system_excluded"
    if event.get("freshness_status") == "expired" or event.get("status") == "inactive":
        return "expired" if event.get("freshness_status") == "expired" else "inactive"
    if event.get("published") or (event.get("status") == "active" and event.get("line_ready") and event.get("recommendation_ready")):
        return "published"
    if event.get("manual_review_required"):
        return "needs_review"
    missing = set(event.get("missing_fields") or [])
    if missing & {"missing_date", "missing_date_start", "missing_location", "missing_location_or_district", "missing_description"}:
        return "needs_data"
    return "needs_review"
