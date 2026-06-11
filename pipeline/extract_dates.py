import re
from datetime import datetime

FULL_DATE_RE = r'\d{3,4}[-/年\.]\s*\d{1,2}[-/月\.]\s*\d{1,2}日?'
MONTH_DAY_RE = r'\d{1,2}[-/月\.]\s*\d{1,2}日?'
DATE_RANGE_SEP_RE = r'(?:至|到|－|-|~|～)'

ROC_DATE_PATTERN = re.compile(r"(?P<year>1\d{2})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})")

def _parse_roc_date_to_string(value):
    if not value:
        return None
    match = ROC_DATE_PATTERN.search(str(value))
    if not match:
        return None
    year = int(match.group("year")) + 1911
    month = int(match.group("month"))
    day = int(match.group("day"))
    return f"{year:04d}-{month:02d}-{day:02d}"

def infer_roc_datetimes_from_text(*texts):
    text = " ".join(str(item or "") for item in texts if item)
    start = None
    end = None
    start_match = re.search(r"(?:展覽期間起|活動期間起|期間起|起)[:：\s]*((?:1\d{2})[/-]\d{1,2}[/-]\d{1,2})", text)
    end_match = re.search(r"(?:展覽期間訖|活動期間訖|期間訖|訖|至)[:：\s]*((?:1\d{2})[/-]\d{1,2}[/-]\d{1,2})", text)
    range_match = re.search(r"((?:1\d{2})[/-]\d{1,2}[/-]\d{1,2})\s*[~～至]\s*((?:1\d{2})[/-]\d{1,2}[/-]\d{1,2})", text)
    
    if start_match:
        start = _parse_roc_date_to_string(start_match.group(1))
    if end_match:
        end = _parse_roc_date_to_string(end_match.group(1))
    if range_match:
        start = start or _parse_roc_date_to_string(range_match.group(1))
        end = end or _parse_roc_date_to_string(range_match.group(2))
    return start, end

def parse_date_string(date_str, default_year=None):
    """
    Parses a single date string and returns YYYY-MM-DD.
    Handles Minguo (e.g., 115) to Gregorian (2026) conversion.
    """
    # Pattern for YYYY-MM-DD, YYYY/MM/DD, YYY年M月D日, or M月D日 with a known year.
    match = re.search(r'(\d{3,4})[-/年\.]\s*(\d{1,2})[-/月\.]\s*(\d{1,2})', date_str)
    if not match and default_year:
        match = re.search(r'(\d{1,2})[-/月\.]\s*(\d{1,2})', date_str)
        if match:
            month, day = match.groups()
            year = default_year
            try:
                datetime(int(year), int(month), int(day))
                return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
            except ValueError:
                return None
    if not match:
        return None
        
    year, month, day = match.groups()
    year = int(year)
    month = int(month)
    day = int(day)
    
    # Minguo conversion
    if year < 1911:
        year += 1911
        
    try:
        datetime(year, month, day)
    except ValueError:
        return None
        
    return f"{year:04d}-{month:02d}-{day:02d}"

def infer_default_year(event, text):
    for value in (event.get("title"), text):
        match = re.search(r'(20\d{2})', str(value or ""))
        if match:
            return int(match.group(1))
    published = parse_date_string(event.get("published_date_text") or "")
    if published:
        return int(published[:4])
    return None

def parse_date_range(text, default_year=None):
    timed_full_range = re.search(
        rf'({FULL_DATE_RE})\s*(?:\d{{1,2}}:\d{{2}})?\s*{DATE_RANGE_SEP_RE}\s*({FULL_DATE_RE})\s*(?:\d{{1,2}}:\d{{2}})?',
        text,
    )
    if timed_full_range:
        return parse_date_string(timed_full_range.group(1)), parse_date_string(timed_full_range.group(2))

    full_then_partial = re.search(
        rf'({FULL_DATE_RE})\s*[^\d]{{0,8}}{DATE_RANGE_SEP_RE}\s*({FULL_DATE_RE}|{MONTH_DAY_RE})',
        text,
    )
    if full_then_partial:
        start = parse_date_string(full_then_partial.group(1))
        start_year = int(start[:4]) if start else default_year
        end = parse_date_string(full_then_partial.group(2), default_year=start_year)
        return start, end

    if default_year:
        partial_range = re.search(
            rf'({MONTH_DAY_RE})\s*{DATE_RANGE_SEP_RE}\s*({MONTH_DAY_RE})',
            text,
        )
        if partial_range:
            start = parse_date_string(partial_range.group(1), default_year=default_year)
            end = parse_date_string(partial_range.group(2), default_year=default_year)
            return start, end

    return None, None

def _date_value(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None

def validate_date_range(event):
    warnings = event.setdefault("quality_warnings", [])
    start = _date_value(event.get("date_start"))
    end = _date_value(event.get("date_end"))
    if start and end and end < start:
        event["date_end"] = None
        warnings.append("date_range_invalid")
        event["date_parse_status"] = "partial_invalid_range"
        event["recommendation_ready"] = False
        event["exclude_from_recommendation_reason"] = "invalid_date_range"
    event["quality_warnings"] = sorted(set(warnings))
    return event

def extract_dates(event, debug_log=None):
    """
    Extracts start and end dates from event fields.
    Updates date_start, date_end, and date_parse_status.
    """
    if not event: return event
    
    dt = event.get("date_text") or ""
    desc = event.get("clean_description") or ""
    enriched = event.get("enriched_metadata_text") or ""
    text = f"{dt} {enriched} {desc}"

    start_match = re.search(r'活動日期[\(（]起[\)）]\s*[:：]\s*([0-9./\-年月日]+)', text)
    end_match = re.search(r'活動日期[\(（]迄[\)）]\s*[:：]\s*([0-9./\-年月日]+)', text)
    if start_match:
        event["date_start"] = parse_date_string(start_match.group(1))
    if end_match:
        default_year = int(event["date_start"][:4]) if event.get("date_start") else None
        event["date_end"] = parse_date_string(end_match.group(1), default_year=default_year)

    if not event.get("date_start"):
        default_year = infer_default_year(event, text)
        start, end = parse_date_range(text, default_year=default_year)
        if start:
            event["date_start"] = start
        if end:
            event["date_end"] = end

    if not event.get("date_start"):
        # Activity-like sources may describe a single activity date in prose.
        prose_match = re.search(r'(?:活動|比賽|展覽|說明會|工作坊|市集|講座|課程|將於|於)\D{0,12}(\d{3,4}年\d{1,2}月\d{1,2}日)', text)
        if prose_match:
            event["date_start"] = parse_date_string(prose_match.group(1))

    if not event.get("date_start"):
        # New advanced ROC date inference from text
        start, end = infer_roc_datetimes_from_text(text)
        if start:
            event["date_start"] = start
        if end:
            event["date_end"] = end
            
    if not event.get("date_start") and event.get("content_type") != "activity":
        published = event.get("published_date_text")
        if published:
            event["date_start"] = parse_date_string(published)
                
    # Set status
    if event.get("date_start"):
        if not event.get("date_end"):
            event["date_end"] = event["date_start"] # Single day event
        event["date_parse_status"] = "success"
    else:
        event["date_parse_status"] = "failed"
        if debug_log is not None:
            debug_log.append({
                "title": event.get("title"),
                "source_url": event.get("source_url"),
                "date_text": event.get("date_text"),
                "description_sample": str(event.get("clean_description", ""))[:100],
                "reason": "unsupported date format or missing"
            })

    return validate_date_range(event)
