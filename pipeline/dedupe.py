import hashlib
import re
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse


SOURCE_PRIORITY = {
    "tycg_events": 1,
    "culture": 2,
    "travel_openapi": 3,
    "tmofa_exhibitions": 4,
    "tmofa_events": 5,
    "library_activity_rss": 6,
    "wem_news_photo": 7,
    "sports_rss": 8,
    "agriculture": 9,
    "economic": 10,
    "youth": 11,
    "hakka": 12,
    "travel_news": 13,
    # RSS mirrors are fallback sources; keep them lower than canonical sources.
    "tycg_events_rss": 30,
    "culture_rss": 31,
    "economic_rss": 32,
    "agriculture_rss": 33,
    "hakka_rss": 34,
    "hakka_json": 35,
    "youth_hot_rss": 36,
    "youth_news_rss": 37,
    "animal_rss": 38,
}

def calculate_content_hash(event):
    """
    Calculates a unique hash for the event content.
    Uses title + date_text + location + clean_description.
    """
    title = event.get("title") or ""
    date_text = event.get("date_text") or ""
    location = event.get("location") or ""
    desc = event.get("clean_description") or ""
    
    hash_str = f"{title}|{date_text}|{location}|{desc}"
    return hashlib.md5(hash_str.encode("utf-8")).hexdigest()


def extract_source_item_id(event):
    for key in ("source_item_id", "travel_openapi_id"):
        if event.get(key):
            return str(event.get(key))
    url = event.get("official_detail_url") or event.get("source_url") or ""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("s", "id", "actId", "actid"):
        if query.get(key):
            return query[key][0]
    parts = [part for part in parsed.path.split("/") if part]
    if parts and parts[-1].isdigit():
        return parts[-1]
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:12] if url else None


def apply_stable_ids(event):
    source_key = event.get("source_key") or "unknown"
    source_item_id = extract_source_item_id(event)
    event["source_item_id"] = source_item_id
    event["activity_uid"] = f"{source_key}_{source_item_id}" if source_item_id else None
    return event


def normalize_title(title):
    text = str(title or "").lower()
    text = re.sub(r"[\s　]+", "", text)
    text = re.sub(r"[【】\[\]（）()《》「」『』:：\-－_｜|]", "", text)
    return text


def cross_source_key(event):
    title = normalize_title(event.get("title"))
    date_start = event.get("date_start") or ""
    place = event.get("location") or event.get("district") or ""
    place = re.sub(r"[\s　]+", "", str(place))
    if not title or not date_start or not place:
        return None
    return f"{title}|{date_start}|{place}"


def event_priority(event):
    base = SOURCE_PRIORITY.get(event.get("source_key"), 99)
    score = event.get("quality_score") or 0
    return (base, -score)


def normalized_detail_url(event):
    raw_url = event.get("official_detail_url") or event.get("source_url") or ""
    parsed = urlparse(str(raw_url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    path = re.sub(r"/+$", "", parsed.path or "").lower()
    host = parsed.netloc.lower()
    query_pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        if key.lower() in {"id", "s", "sn", "n", "actid"}:
            query_pairs.append((key.lower(), value))
    query = urlencode(sorted(query_pairs)) if query_pairs else ""

    normalized = f"{parsed.scheme.lower()}://{host}{path}"
    if query:
        normalized += f"?{query}"
    return normalized


def canonical_event_keys(event):
    keys = []
    detail_url = normalized_detail_url(event)
    if detail_url:
        keys.append(f"detail:{detail_url}")

    source_item_id = event.get("source_item_id") or extract_source_item_id(event)
    if source_item_id:
        keys.append(f"item:{event.get('source_key') or 'unknown'}:{source_item_id}")
    return keys


def register_event_keys(event, index, seen_canonical, seen_cross_source):
    for key in canonical_event_keys(event):
        seen_canonical[key] = index
    cross_key = cross_source_key(event)
    if cross_key:
        seen_cross_source[cross_key] = index


def merge_duplicate(primary, secondary):
    merged = dict(primary)
    for key, value in secondary.items():
        if key in {"source_key", "source_name", "source_url", "official_detail_url"}:
            continue
        if merged.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
            merged[key] = value
    urls = []
    for event in (primary, secondary):
        for key in ("official_detail_url", "source_url"):
            url = event.get(key)
            if url and url not in urls:
                urls.append(url)
    if len(urls) > 1:
        merged["duplicate_source_urls"] = urls
    keys = []
    for event in (primary, secondary):
        for key in canonical_event_keys(event):
            if key not in keys:
                keys.append(key)
        for old_key in event.get("duplicate_source_keys", []):
            if old_key not in keys:
                keys.append(old_key)
    if len(keys) > 1:
        merged["duplicate_source_keys"] = keys
    warnings = set(primary.get("quality_warnings") or []) | set(secondary.get("quality_warnings") or [])
    if secondary.get("source_key") != primary.get("source_key"):
        warnings.add("cross_source_duplicate_merged")
    merged["quality_warnings"] = sorted(warnings)
    return merged


def deduplicate(events):
    """
    Deduplicates by canonical detail keys first, then by normalized title + start date + place.
    """
    seen_urls = {}
    seen_canonical = {}
    seen_cross_source = {}
    deduped = []
    
    for event in events:
        if not event: continue
        
        event["content_hash"] = calculate_content_hash(event)
        apply_stable_ids(event)
        url = event.get("source_url")
        
        if url:
            if url in seen_urls:
                continue
            seen_urls[url] = event

        existing_index = None
        for key in canonical_event_keys(event):
            if key in seen_canonical:
                existing_index = seen_canonical[key]
                break
        if existing_index is None:
            key = cross_source_key(event)
            if key and key in seen_cross_source:
                existing_index = seen_cross_source[key]

        if existing_index is not None:
            index = existing_index
            existing = deduped[index]
            if event_priority(event) < event_priority(existing):
                deduped[index] = merge_duplicate(event, existing)
            else:
                deduped[index] = merge_duplicate(existing, event)
            register_event_keys(deduped[index], index, seen_canonical, seen_cross_source)
            continue
        
        deduped.append(event)
        register_event_keys(event, len(deduped) - 1, seen_canonical, seen_cross_source)
        
    return deduped
