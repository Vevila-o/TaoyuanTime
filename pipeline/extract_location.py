import re
import yaml
import os

with open(os.path.join("config", "districts.yaml"), "r", encoding="utf-8") as f:
    DISTRICTS = yaml.safe_load(f).get("districts", [])

VENUE_DISTRICTS = {
    "桃園展演中心": "桃園區",
    "桃園市政府文化局": "桃園區",
    "文化局": "桃園區",
    "中壢藝術館": "中壢區",
    "觀音國小": "觀音區",
    "中原文創園區": "中壢區",
    "桃園市立美術館": "中壢區",
    "桃園市兒童美術館": "中壢區",
    "橫山書法藝術館": "大園區",
}

def extract_location(event, debug_log=None):
    """
    Extracts location and district.
    """
    if not event: return event
    
    desc = f"{event.get('clean_description', '')} {event.get('enriched_metadata_text', '')}"
    
    # Common prefixes. Avoid single-character prefixes such as "於" / "在";
    # they produce false locations like "今年3月圓滿結束".
    prefixes = ["活動地址：", "活動地點：", "比賽地點：", "展覽地點：", "辦理地點：", "上課地點：", "施工範圍｜", "施工範圍：", "主場設於"]
    
    location = None
    
    # If the scraper found an explicit location_text, use that
    if event.get("location_text"):
        candidate = event.get("location_text")
        if is_plausible_location(candidate):
            location = candidate

    if not location:
        # Try to find in description
        for prefix in prefixes:
            pattern = re.compile(rf"{prefix}\s*([^。；;\n]+)")
            match = pattern.search(desc)
            if match:
                loc_candidate = re.split(r"\s*(?:發布單位|主辦單位|活動日期|報名|聯絡人|資料提供)", match.group(1).strip())[0]
                if is_plausible_location(loc_candidate):
                    location = loc_candidate
                    break
        if not location:
            prose_match = re.search(r"(桃園市[^。；;\n]{2,40}(?:館|中心|公園|學校|廣場|園區|市場|農場|教室|廳|區|路|街|號))", desc)
            if prose_match and is_plausible_location(prose_match.group(1)):
                location = prose_match.group(1)
                    
    event["location"] = location
    
    if location:
        # Find district
        matched_districts = [d for d in DISTRICTS if d in location]
        if len(matched_districts) == 1:
            event["district"] = matched_districts[0]
            event["location_parse_status"] = "success"
        elif len(matched_districts) > 1:
            event["district"] = matched_districts[0] # Pick first or leave null based on preference, here we just pick first to keep it simple, but mark multi
            event["location_parse_status"] = "multi_location"
        else:
            event["district"] = district_from_known_venue(location)
            event["location_parse_status"] = "success" # Extracted location but no specific Taoyuan district
        if location.strip() in {"桃園市", "桃園"}:
            warnings = event.setdefault("quality_warnings", [])
            warnings.append("generic_location")
            event["quality_warnings"] = sorted(set(warnings))
    else:
        event["location_parse_status"] = "failed"
        if debug_log is not None:
            debug_log.append({
                "title": event.get("title"),
                "source_url": event.get("source_url"),
                "description_sample": str(desc)[:100],
                "reason": "no location keyword found"
            })
            
    return event

def district_from_known_venue(location):
    for venue, district in VENUE_DISTRICTS.items():
        if venue in location:
            return district
    return None

def is_plausible_location(value):
    if not value:
        return False
    value = value.strip()
    if len(value) < 3 or len(value) > 80:
        return False
    bad_terms = [
        "公告", "名單", "結果", "報名", "計畫", "補助", "資格", "期間", "日期", "今年", "進行公告",
        "表示", "推薦民眾", "近年", "產業", "趨勢", "協助", "回應", "公布", "正式推出",
    ]
    if any(term in value for term in bad_terms):
        return False
    if district_from_known_venue(value):
        return True
    venue_terms = ["桃園市", "區", "路", "街", "號", "館", "中心", "公園", "學校", "廣場", "園區", "市場", "農場", "教室", "廳"]
    return any(term in value for term in venue_terms)
