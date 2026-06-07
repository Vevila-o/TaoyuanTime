import asyncio
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SWAGGER_UI_URL = "https://travel.tycg.gov.tw/open-api/swagger/ui/index"
SPEC_CANDIDATE_URLS = [
    "https://travel.tycg.gov.tw/open-api/swagger/v1/swagger.json",
    "https://travel.tycg.gov.tw/open-api/swagger/docs/v1",
    "https://travel.tycg.gov.tw/open-api/swagger.json",
    "https://travel.tycg.gov.tw/open-api/swagger/ui/swagger.json",
    "https://travel.tycg.gov.tw/open-api/swagger",
]
OUTPUT_DIR = os.path.join("scraping", "data", "output", "debug_cases")
SPEC_OUTPUT = os.path.join(OUTPUT_DIR, "travel_openapi_spec.json")
PATHS_OUTPUT = os.path.join(OUTPUT_DIR, "travel_openapi_paths.json")
CANDIDATES_OUTPUT = os.path.join(OUTPUT_DIR, "travel_activity_api_candidates.json")
DISCOVERY_LOG_OUTPUT = os.path.join(OUTPUT_DIR, "travel_openapi_discovery_log.json")
ACTIVITY_KEYWORDS = [
    "activity",
    "activities",
    "event",
    "events",
    "calendar",
    "festival",
    "news",
    "tour",
    "scenic",
    "spot",
]


def fetch_json(url: str, timeout: int = 20) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    info: dict[str, Any] = {"url": url, "ok": False}
    req = Request(
        url,
        headers={
            "Accept": "application/json, text/json, */*",
            "User-Agent": "Mozilla/5.0 travel-openapi-discovery/1.0",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read()
            text = body.decode("utf-8-sig")
            content_type = response.headers.get("content-type", "")
            info.update(
                {
                    "status": response.status,
                    "content_type": content_type,
                    "bytes": len(body),
                }
            )
            data = json.loads(text)
            if is_openapi_spec(data):
                info["ok"] = True
                return data, info
            info["error"] = "JSON response is not a Swagger/OpenAPI spec"
            info["top_level_keys"] = list(data.keys())[:20] if isinstance(data, dict) else None
            return None, info
    except HTTPError as exc:
        info.update({"status": exc.code, "error": str(exc)})
    except (URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        info["error"] = repr(exc)
    return None, info


def is_openapi_spec(data: Any) -> bool:
    return isinstance(data, dict) and (
        "openapi" in data
        or "swagger" in data
        or ("paths" in data and ("info" in data or "definitions" in data or "components" in data))
    )


async def discover_with_playwright() -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    from playwright.async_api import async_playwright

    json_responses: list[dict[str, Any]] = []
    spec: dict[str, Any] | None = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        async def on_response(response):
            nonlocal spec
            url = response.url
            content_type = response.headers.get("content-type", "")
            haystack = f"{url} {content_type}".lower()
            looks_relevant = any(
                token in haystack for token in ["swagger", "openapi", "api-docs", "v1", "json"]
            )
            if "json" not in content_type.lower() and not looks_relevant:
                return

            entry = {
                "url": url,
                "status": response.status,
                "content_type": content_type,
                "relevant": looks_relevant,
            }
            try:
                data = await response.json()
                entry["json_type"] = type(data).__name__
                if isinstance(data, dict):
                    entry["top_level_keys"] = list(data.keys())[:20]
                if spec is None and is_openapi_spec(data):
                    spec = data
                    entry["selected"] = True
            except Exception as exc:
                entry["error"] = repr(exc)
            json_responses.append(entry)

        page.on("response", on_response)
        await page.goto(SWAGGER_UI_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        await browser.close()

    json_responses.sort(key=lambda item: (not item.get("selected", False), not item.get("relevant", False), item["url"]))
    return spec, json_responses


def schema_preview(value: Any, max_depth: int = 3) -> Any:
    if max_depth <= 0:
        if isinstance(value, dict):
            return {"...": "..."}
        if isinstance(value, list):
            return ["..."]
        return value
    if isinstance(value, dict):
        preview: dict[str, Any] = {}
        for key in [
            "name",
            "in",
            "required",
            "type",
            "format",
            "$ref",
            "title",
            "description",
            "nullable",
        ]:
            if key in value:
                preview[key] = value[key]
        for key in ["items", "properties", "schema", "content"]:
            if key in value:
                preview[key] = schema_preview(value[key], max_depth - 1)
        if not preview:
            for key, nested in list(value.items())[:8]:
                preview[key] = schema_preview(nested, max_depth - 1)
        return preview
    if isinstance(value, list):
        return [schema_preview(item, max_depth - 1) for item in value[:3]]
    return value


def response_schema_preview(operation: dict[str, Any]) -> Any:
    responses = operation.get("responses") or {}
    for status in ["200", "201", "default"]:
        if status in responses:
            return {status: schema_preview(responses[status])}
    if responses:
        first_status = next(iter(responses))
        return {first_status: schema_preview(responses[first_status])}
    return None


def extract_paths(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    paths = spec.get("paths") or {}
    for path, path_item in sorted(paths.items()):
        if not isinstance(path_item, dict):
            continue
        path_parameters = path_item.get("parameters") or []
        for method, operation in sorted(path_item.items()):
            if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            if not isinstance(operation, dict):
                continue
            parameters = []
            parameters.extend(path_parameters if isinstance(path_parameters, list) else [])
            parameters.extend(operation.get("parameters") or [])
            rows.append(
                {
                    "path": path,
                    "method": method.upper(),
                    "summary": operation.get("summary") or operation.get("operationId") or "",
                    "tags": operation.get("tags") or [],
                    "parameters": schema_preview(parameters),
                    "response_schema_preview": response_schema_preview(operation),
                }
            )
    return rows


def filter_activity_candidates(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for row in paths:
        text = json.dumps(row, ensure_ascii=False).lower()
        matches = sorted({keyword for keyword in ACTIVITY_KEYWORDS if keyword in text})
        if matches:
            candidate = dict(row)
            candidate["matched_keywords"] = matches
            candidates.append(candidate)
    return candidates


def write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


async def main() -> None:
    discovery_log: dict[str, Any] = {"direct_candidates": [], "playwright_json_responses": []}
    spec = None
    for url in SPEC_CANDIDATE_URLS:
        spec, info = fetch_json(url)
        discovery_log["direct_candidates"].append(info)
        if spec is not None:
            discovery_log["selected_url"] = url
            discovery_log["selected_method"] = "direct"
            break

    if spec is None:
        spec, responses = await discover_with_playwright()
        discovery_log["playwright_json_responses"] = responses
        selected = next((item for item in responses if item.get("selected")), None)
        if selected:
            discovery_log["selected_url"] = selected["url"]
            discovery_log["selected_method"] = "playwright"

    if spec is None:
        write_json(DISCOVERY_LOG_OUTPUT, discovery_log)
        raise SystemExit(f"No Swagger/OpenAPI spec found. See {DISCOVERY_LOG_OUTPUT}")

    paths = extract_paths(spec)
    candidates = filter_activity_candidates(paths)
    write_json(SPEC_OUTPUT, spec)
    write_json(PATHS_OUTPUT, paths)
    write_json(CANDIDATES_OUTPUT, candidates)
    write_json(DISCOVERY_LOG_OUTPUT, discovery_log)

    print(f"Spec: {SPEC_OUTPUT}")
    print(f"Paths: {PATHS_OUTPUT} ({len(paths)} endpoints)")
    print(f"Activity candidates: {CANDIDATES_OUTPUT} ({len(candidates)} endpoints)")
    print(f"Discovery log: {DISCOVERY_LOG_OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
