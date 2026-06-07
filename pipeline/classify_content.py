import yaml
import os

# Load keywords
with open(os.path.join("config", "keywords.yaml"), "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)
    ACTIVITY_KEYWORDS = config.get("activity_keywords", [])
    NON_ACTIVITY_KEYWORDS = config.get("non_activity_keywords", [])

def classify_content(event):
    """
    Classifies the content based on keyword scoring.
    Updates content_type, is_event_candidate, and event_confidence.
    """
    if not event: return event
    
    title = event.get("title", "") or ""
    desc = event.get("clean_description", "") or ""
    text_to_search = title + " " + desc
    warnings = event.setdefault("quality_warnings", [])
    
    activity_score = 0
    non_event_score = 0
    
    for kw in ACTIVITY_KEYWORDS:
        if kw in text_to_search:
            activity_score += 1
            # Weight title matches higher
            if kw in title:
                activity_score += 1
                
    for kw in NON_ACTIVITY_KEYWORDS:
        if kw in text_to_search:
            non_event_score += 1
            if kw in title:
                non_event_score += 1
                
    # Calculate confidence based on scores
    total_score = activity_score + non_event_score
    if total_score > 0:
        event["event_confidence"] = round(activity_score / total_score, 2)
    else:
        event["event_confidence"] = 0.0
        
    strong_non_activity_terms = [
        "徵才", "採購", "決算", "裁罰", "罰鍰", "公示送達", "失物招領",
        "休館公告", "開館事宜", "工廠校正", "營運調查", "面試甄選結果",
        "錄取名單", "書審結果", "違反", "名單至", "補助計畫",
        "光電指引", "太陽光電", "財報承認", "商業決算", "違規最重罰",
        "管理缺口", "修法", "設施設置指引", "甄選結果",
        "實習生申請", "實習生", "志工招募", "服務生招募", "招募",
        "志願服務整合資訊平台", "桃園志工網", "志工業務承辦人", "志工業務",
    ]
    announcement_prefixes = ("公告", "【公告】", "📢 公告")
    strong_activity_terms = [
        "活動日期", "活動地址", "活動地點", "開放報名", "活動時間",
        "講座", "課程", "展覽", "音樂會", "市集", "工作坊", "嘉年華",
        "比賽", "體驗", "演出", "表演", "節", "季", "夏令營", "營隊"
    ]

    forced_non_activity = any(term in text_to_search for term in strong_non_activity_terms)
    title_is_announcement = title.startswith(announcement_prefixes)
    has_structured_activity = any(term in text_to_search for term in strong_activity_terms)
    recap_terms = ["圓滿落幕", "活動回顧", "成果", "吸引超過", "順利完成"]
    resource_terms = ["名單", "清冊", "旅宿", "地圖", "懶人包", "資訊", "資源"]
    has_explicit_activity_fields = "活動日期" in text_to_search and (
        "活動地址" in text_to_search or "活動地點" in text_to_search
    )
    force_activity = bool(event.get("force_activity_classification"))

    # Rules
    if forced_non_activity:
        if "採購" in text_to_search or "決算" in text_to_search:
            event["content_type"] = "procurement"
        elif "徵才" in text_to_search or "面試甄選" in text_to_search or "招募" in text_to_search:
            event["content_type"] = "recruitment"
        elif "光電" in text_to_search or "指引" in text_to_search or "修法" in text_to_search:
            event["content_type"] = "policy"
        else:
            event["content_type"] = "announcement"
        event["is_event_candidate"] = False
        warnings.append("strong_non_activity_keyword")
    elif any(term in text_to_search for term in recap_terms) and not has_structured_activity:
        event["content_type"] = "recap"
        event["is_event_candidate"] = False
        warnings.append("recap_not_recommendable")
    elif any(term in text_to_search for term in resource_terms) and not has_structured_activity:
        event["content_type"] = "place_or_resource"
        event["is_event_candidate"] = False
        warnings.append("resource_not_recommendable")
    elif title_is_announcement and not has_structured_activity:
        event["content_type"] = "announcement"
        event["is_event_candidate"] = False
        warnings.append("title_contains_announcement_terms")
    elif has_explicit_activity_fields:
        event["content_type"] = "activity"
        event["is_event_candidate"] = True
        event["event_confidence"] = max(event.get("event_confidence", 0.0), 0.9)
    elif has_structured_activity and activity_score >= 1 and non_event_score <= activity_score:
        event["content_type"] = "activity"
        event["is_event_candidate"] = True
    elif force_activity:
        event["content_type"] = "activity"
        event["is_event_candidate"] = True
        event["event_confidence"] = max(event.get("event_confidence", 0.0), 0.9)
    elif activity_score >= 2 and non_event_score >= 1:
        if event["event_confidence"] >= 0.6:
            event["content_type"] = "activity"
            event["is_event_candidate"] = True
        else:
            event["content_type"] = "announcement"
            event["is_event_candidate"] = False
    elif non_event_score > activity_score:
        # Determine specific non-event type roughly
        if "採購" in text_to_search or "決算" in text_to_search:
            event["content_type"] = "procurement"
        elif "徵才" in text_to_search or "招募" in text_to_search:
            event["content_type"] = "recruitment"
        elif "政策" in text_to_search or "法規" in text_to_search:
            event["content_type"] = "policy"
        else:
            event["content_type"] = "announcement"
        event["is_event_candidate"] = False
    else:
        event["content_type"] = "unknown"
        event["is_event_candidate"] = False

    event["item_type"] = event["content_type"]
    event["is_activity"] = event["content_type"] == "activity"
    return event
