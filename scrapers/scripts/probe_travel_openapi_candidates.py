import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_DIR = os.path.join("scraping", "data", "output", "debug_cases")
CANDIDATES_PATH = os.path.join(BASE_DIR, "travel_activity_api_candidates.json")
SPEC_PATH = os.path.join(BASE_DIR, "travel_openapi_spec.json")
PROBE_RESULTS_PATH = os.path.join(BASE_DIR, "travel_openapi_probe_results.json")
SAMPLE_RECORDS_PATH = os.path.join(BASE_DIR, "travel_openapi_sample_records.json")
RANKED_CANDIDATES_PATH = os.path.join(BASE_DIR, "travel_openapi_ranked_candidates.json")

DEFAULT_BASE_URL = "https://travel.tycg.gov.tw/open-api"
TEXT_PREVIEW_CHARS = 2000

PATH_PARAM_VALUES = {
    "lang": "zh-tw",
    "language": "zh-tw",
}
QUERY_PARAM_VALUES = {
    "page": "1",
    "pageindex": "1",
    "size": "10",
    "pagesize": "10",
    "limit": "10",
    "lang": "zh-tw",
    "language": "zh-tw",
    "year": "2026",
    "month": "5",
}
SKIP_QUERY_PARAMS = {"keyword", "category", "id"}
LIST_CONTAINER_KEYS = ["data", "items", "list", "result", "results"]

TITLE_TOKENS = ["title", "name", "subject", "caption", "活動名稱", "名稱", "標題"]
DATE_TOKENS = ["date", "time", "start", "end", "begin", "finish", "期限", "日期", "時間"]
LOCATION_TOKENS = [
    "address",
    "location",
    "place",
    "venue",
    "region",
    "district",
    "latitude",
    "longitude",
    "lat",
    "lng",
    "lon",
    "座標",
    "地點",
    "地址",
    "行政區",
]
IMAGE_TOKENS = ["image", "img", "picture", "photo", "pic", "thumbnail", "cover", "照片", "圖片"]
DETAIL_URL_TOKENS = ["url", "link", "href", "website", "detail", "id", "網址", "連結", "編號"]
CATEGORY_TOKENS = ["category", "type", "tag", "class", "分類", "類別"]
NEWS_TOKENS = ["news", "announcement", "最新消息", "新聞", "公告"]


def load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build_base_url(spec: dict[str, Any]) -> str:
    if not spec:
        return DEFAULT_BASE_URL
    scheme = (spec.get("schemes") or ["https"])[0]
    host = spec.get("host") or "travel.tycg.gov.tw"
    base_path = spec.get("basePath") or "/open-api"
    return f"{scheme}://{host}{base_path}".rstrip("/")


def merge_spec_parameters(candidate: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    path = candidate.get("path")
    method = str(candidate.get("method", "get")).lower()
    spec_operation = ((spec.get("paths") or {}).get(path) or {}).get(method) or {}
    path_item = (spec.get("paths") or {}).get(path) or {}
    parameters: list[dict[str, Any]] = []
    for item in path_item.get("parameters") or []:
        if isinstance(item, dict):
            parameters.append(item)
    for item in spec_operation.get("parameters") or candidate.get("parameters") or []:
        if isinstance(item, dict):
            parameters.append(item)
    return parameters


def normalize_param_name(name: str) -> str:
    return name.replace("_", "").replace("-", "").lower()


def replace_path_params(path: str, parameters: list[dict[str, Any]]) -> tuple[str, list[str]]:
    replaced = path
    skipped_ids = []
    for param in parameters:
        if param.get("in") != "path":
            continue
        name = str(param.get("name") or "")
        normalized = normalize_param_name(name)
        if normalized in {"id"}:
            skipped_ids.append(name)
            continue
        value = PATH_PARAM_VALUES.get(normalized) or QUERY_PARAM_VALUES.get(normalized)
        if value is not None:
            replaced = replaced.replace("{" + name + "}", value)
    return replaced, skipped_ids


def build_query(parameters: list[dict[str, Any]]) -> dict[str, str]:
    query: dict[str, str] = {}
    for param in parameters:
        if param.get("in") != "query":
            continue
        name = str(param.get("name") or "")
        normalized = normalize_param_name(name)
        if normalized in SKIP_QUERY_PARAMS:
            continue
        if normalized in QUERY_PARAM_VALUES:
            query[name] = QUERY_PARAM_VALUES[normalized]
    return query


def build_request_url(base_url: str, candidate: dict[str, Any], parameters: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    path, skipped_ids = replace_path_params(str(candidate.get("path") or ""), parameters)
    if skipped_ids or "{" in path or "}" in path:
        return None, f"skipped unresolved path parameter: {', '.join(skipped_ids) or path}"
    query = build_query(parameters)
    url = f"{base_url}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    return url, None


def fetch_url(url: str, timeout: int = 30) -> dict[str, Any]:
    req = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 travel-openapi-probe/1.0",
        },
    )
    result: dict[str, Any] = {
        "request_url": url,
        "status_code": None,
        "content_type": "",
        "success": False,
        "error": "",
        "response_text_preview": "",
    }
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read()
            text = body.decode("utf-8-sig", errors="replace")
            result.update(
                {
                    "status_code": response.status,
                    "content_type": response.headers.get("content-type", ""),
                    "success": 200 <= response.status < 300,
                    "response_text_preview": text[:TEXT_PREVIEW_CHARS],
                }
            )
            parsed = parse_json_if_possible(text)
            if parsed is not None:
                result["parsed_json"] = parsed
                result.update(describe_json(parsed))
    except HTTPError as exc:
        body = exc.read()
        text = body.decode("utf-8-sig", errors="replace") if body else ""
        result.update(
            {
                "status_code": exc.code,
                "content_type": exc.headers.get("content-type", "") if exc.headers else "",
                "error": str(exc),
                "response_text_preview": text[:TEXT_PREVIEW_CHARS],
            }
        )
        parsed = parse_json_if_possible(text)
        if parsed is not None:
            result["parsed_json"] = parsed
            result.update(describe_json(parsed))
    except (URLError, TimeoutError, OSError) as exc:
        result["error"] = repr(exc)
    return result


def parse_json_if_possible(text: str) -> Any:
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def describe_json(data: Any) -> dict[str, Any]:
    description: dict[str, Any] = {}
    records, container = extract_records(data)
    if isinstance(data, list):
        description["json_type"] = "list"
        description["list_length"] = len(data)
        description["first_record_keys"] = sorted(data[0].keys()) if data and isinstance(data[0], dict) else []
    elif isinstance(data, dict):
        description["json_type"] = "dict"
        description["top_level_keys"] = sorted(data.keys())
        if records:
            description["record_container"] = container
            description["record_list_length"] = len(records)
            description["first_record_keys"] = sorted(records[0].keys()) if isinstance(records[0], dict) else []
    else:
        description["json_type"] = type(data).__name__
    return description


def extract_records(data: Any) -> tuple[list[Any], str]:
    if isinstance(data, list):
        return data, "$"
    if not isinstance(data, dict):
        return [], ""
    for key in LIST_CONTAINER_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            return value, key
        if isinstance(value, dict):
            nested, nested_key = extract_records(value)
            if nested:
                return nested, f"{key}.{nested_key}"
    return find_first_list(data)


def find_first_list(data: Any, prefix: str = "$") -> tuple[list[Any], str]:
    if isinstance(data, list):
        return data, prefix
    if not isinstance(data, dict):
        return [], ""
    for key, value in data.items():
        nested_prefix = f"{prefix}.{key}"
        if isinstance(value, list):
            return value, nested_prefix
        if isinstance(value, dict):
            found, found_prefix = find_first_list(value, nested_prefix)
            if found:
                return found, found_prefix
    return [], ""


def flatten_record(record: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    flattened: dict[str, Any] = {}
    for key, value in record.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(flatten_record(value, name))
        else:
            flattened[name] = value
    return flattened


def field_matches(flattened: dict[str, Any], tokens: list[str]) -> list[str]:
    matches = []
    for key in flattened:
        if any(key_has_token(key, token) for token in tokens):
            matches.append(key)
    return sorted(matches)


def key_has_token(key: str, token: str) -> bool:
    key_lower = key.lower()
    token_lower = token.lower()
    if any(ord(char) > 127 for char in token_lower):
        return token_lower in key_lower

    normalized = "".join(char if char.isalnum() else " " for char in key_lower)
    segments = normalized.split()
    compact = "".join(segments)
    if token_lower in {"id", "url", "lat", "lng", "lon", "img", "pic", "start", "end", "time"}:
        return token_lower in segments or key_lower.endswith("." + token_lower)
    return token_lower in compact


def infer_fields(record: Any) -> dict[str, dict[str, Any]]:
    flattened = flatten_record(record)
    inferred = {}
    for key, value in flattened.items():
        inferred[key] = {
            "type": type(value).__name__,
            "sample": value if not isinstance(value, str) or len(value) <= 200 else value[:200],
        }
    return inferred


def score_candidate(candidate: dict[str, Any], probe: dict[str, Any], sample_record: Any) -> tuple[int, str, str]:
    score = 0
    reasons = []
    record_count = int(probe.get("list_length") or probe.get("record_list_length") or 0)
    flattened = flatten_record(sample_record)
    title_fields = field_matches(flattened, TITLE_TOKENS)
    date_fields = field_matches(flattened, DATE_TOKENS)
    location_fields = field_matches(flattened, LOCATION_TOKENS)
    image_fields = field_matches(flattened, IMAGE_TOKENS)
    detail_fields = field_matches(flattened, DETAIL_URL_TOKENS)
    text = json.dumps(candidate, ensure_ascii=False).lower()

    if record_count > 1:
        score += 30
        reasons.append(f"has multiple records ({record_count})")
    elif record_count == 1:
        score += 15
        reasons.append("has one record")
    else:
        reasons.append("no usable list records")
    if title_fields:
        score += 15
        reasons.append(f"title/name fields: {', '.join(title_fields[:4])}")
    if date_fields:
        score += 20
        reasons.append(f"date/time fields: {', '.join(date_fields[:4])}")
    if location_fields:
        score += 15
        reasons.append(f"location fields: {', '.join(location_fields[:4])}")
    if image_fields:
        score += 10
        reasons.append(f"image fields: {', '.join(image_fields[:4])}")
    if detail_fields:
        score += 10
        reasons.append(f"detail/id fields: {', '.join(detail_fields[:4])}")
    if any(token.lower() in text for token in NEWS_TOKENS):
        score -= 20
        reasons.append("news/announcement-like endpoint penalty")

    score = max(0, min(100, score))
    usage = recommended_usage(score, candidate, date_fields, record_count)
    return score, "; ".join(reasons), usage


def recommended_usage(score: int, candidate: dict[str, Any], date_fields: list[str], record_count: int) -> str:
    text = json.dumps(candidate, ensure_ascii=False).lower()
    is_event_source = any(token in text for token in ["/event/activity", "/event/calendar"])
    is_news_source = "news" in text or "最新消息" in text
    is_travel_static_source = any(token in text for token in ["/travel/attraction", "/travel/touristinformation"])
    if score >= 70 and date_fields and record_count > 0 and is_event_source and not is_news_source:
        return "primary"
    if is_travel_static_source and record_count > 0:
        return "detail_only"
    if score >= 45 and record_count > 0:
        return "filtered"
    if score >= 25:
        return "detail_only"
    return "not_recommended"


def sample_record_for_endpoint(candidate: dict[str, Any], request_url: str, record: Any) -> dict[str, Any]:
    flattened = flatten_record(record)
    return {
        "endpoint": candidate.get("path"),
        "request_url": request_url,
        "raw_record": record,
        "inferred_fields": infer_fields(record),
        "possible_title_fields": field_matches(flattened, TITLE_TOKENS),
        "possible_date_fields": field_matches(flattened, DATE_TOKENS),
        "possible_location_fields": field_matches(flattened, LOCATION_TOKENS),
        "possible_image_fields": field_matches(flattened, IMAGE_TOKENS),
        "possible_detail_url_fields": field_matches(flattened, DETAIL_URL_TOKENS),
        "possible_category_fields": field_matches(flattened, CATEGORY_TOKENS),
    }


def main() -> None:
    candidates = load_json(CANDIDATES_PATH, [])
    spec = load_json(SPEC_PATH, {})
    base_url = build_base_url(spec)
    probe_results = []
    sample_records = []
    ranked_candidates = []

    for candidate in candidates:
        method = str(candidate.get("method", "GET")).upper()
        parameters = merge_spec_parameters(candidate, spec)
        result = {
            "path": candidate.get("path"),
            "method": method,
            "request_url": None,
            "status_code": None,
            "content_type": "",
            "success": False,
            "error": "",
            "response_text_preview": "",
        }

        if method != "GET":
            result["error"] = f"skipped non-GET method: {method}"
            probe_results.append(result)
            continue

        request_url, build_error = build_request_url(base_url, candidate, parameters)
        if build_error:
            result["error"] = build_error
            probe_results.append(result)
            ranked_candidates.append(
                {
                    "endpoint": candidate.get("path"),
                    "request_url": request_url,
                    "candidate_score": 0,
                    "candidate_reason": build_error,
                    "recommended_usage": "not_recommended",
                }
            )
            continue

        probe = fetch_url(str(request_url))
        result.update(probe)
        result["path"] = candidate.get("path")
        result["method"] = method

        records, _container = extract_records(probe.get("parsed_json"))
        first_record = records[0] if records else None
        if first_record is not None:
            sample = sample_record_for_endpoint(candidate, str(request_url), first_record)
            sample_records.append(sample)
        score, reason, usage = score_candidate(candidate, probe, first_record)
        result["candidate_score"] = score
        result["candidate_reason"] = reason
        result["recommended_usage"] = usage
        ranked_candidates.append(
            {
                "endpoint": candidate.get("path"),
                "request_url": request_url,
                "candidate_score": score,
                "candidate_reason": reason,
                "recommended_usage": usage,
            }
        )
        probe_results.append(result)

    ranked_candidates.sort(key=lambda row: row["candidate_score"], reverse=True)
    write_json(PROBE_RESULTS_PATH, probe_results)
    write_json(SAMPLE_RECORDS_PATH, sample_records)
    write_json(RANKED_CANDIDATES_PATH, ranked_candidates)

    print(f"Probe results: {PROBE_RESULTS_PATH} ({len(probe_results)} endpoints)")
    print(f"Sample records: {SAMPLE_RECORDS_PATH} ({len(sample_records)} records)")
    print(f"Ranked candidates: {RANKED_CANDIDATES_PATH} ({len(ranked_candidates)} endpoints)")


if __name__ == "__main__":
    main()
