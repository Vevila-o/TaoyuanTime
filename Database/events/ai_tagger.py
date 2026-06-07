import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests

from .ai_providers import call_json_with_fallback
from .models import Activity, Tag


TAG_TYPES = ("region", "activity_type", "audience", "cost", "discount", "time")
COST_VALUE_TAGS = {"免費", "付費", "金額未提供"}
REGISTRATION_COST_TAGS = {"需報名", "免預約"}
STRICT_DISCOUNT_TAGS = {"無優惠"}
FREE_EVIDENCE = ("免費", "免票", "免門票", "自由入場", "自由進場", "免費入場", "不收費")
PAID_EVIDENCE = ("票價", "售票", "門票", "報名費", "費用", "OPENTIX", "元")
NO_DISCOUNT_EVIDENCE = ("無優惠", "不適用優惠", "未提供優惠", "沒有優惠")
AUDIENCE_EVIDENCE = {
    "親子": ("親子", "兒童", "小朋友", "家庭", "親子共遊", "孩童"),
    "學生": ("學生", "學校", "高中", "大學", "國小", "國中", "校園"),
    "青年": ("青年", "青少年", "青創", "青年局", "青年事務"),
    "長輩": ("長輩", "樂齡", "銀髮", "老人", "高齡"),
    "情侶": ("情侶", "伴侶", "約會"),
    "毛孩": ("毛孩", "寵物", "犬", "貓"),
}
TAG_TYPE_ALIASES = {
    "地區": "region",
    "行政區": "region",
    "區域": "region",
    "活動類型": "activity_type",
    "活動型態": "activity_type",
    "活動": "activity_type",
    "類型": "activity_type",
    "對象": "audience",
    "受眾": "audience",
    "適合對象": "audience",
    "費用": "cost",
    "成本": "cost",
    "優惠": "discount",
    "折扣": "discount",
    "時間": "time",
}
LOW_VALUE_WARNING_PATTERNS = (
    "目前 tags 數量",
    "未達上限",
    "可視情況增加",
    "需確認是否為過去或未來",
    "如果當前時間",
    "若當前時間",
    "依輸入資料判斷 tag",
    "無矛盾標籤",
    "無矛盾",
    "不矛盾",
    "無衝突",
    "無其他類型矛盾",
    "無明顯矛盾",
    "無直接衝突",
    "資料一致",
    "通常不需報名",
    "tag 僅選地區與類型",
    "屬於學校場地",
    "未明確標示具體時區",
    "故未選 time 標籤",
    "需確認有效性",
    "未重複標註",
)
INFO_WARNING_PATTERNS = (
    "符合",
    "索票資訊",
    "索票進場",
    "數量有限",
    "可能影響參與性",
    "非絕對矛盾",
    "非矛盾",
    "不視為矛盾",
    "不視為衝突",
    "不構成矛盾",
    "不互斥",
    "互斥規則僅適用",
    "獨立欄位",
    "皆符合",
    "推測",
    "較低",
    "更精確",
    "重複",
    "白名單",
    "無「",
    "fee_description 為未標示",
    "費用資訊矛盾：is_free 為 false",
    "無法確認實際收費狀況",
    "無法確定是否付費",
    "金額未提供",
    "current_tags",
    "現行標籤",
    "目前標籤",
    "活動日期",
    "通常付費活動需報名",
    "同時具備售票與報名",
    "免費與免預約",
    "需報名與免費",
    "付費與需報名",
    "依票價欄位判斷",
    "registration_info 有網址",
    "registration_info 含 URL",
    "registration_info 欄位顯示",
    "registration_info 連結",
    "registration_info 顯示",
    "registration_info 提供線上連結",
    "requires_registration 為 false 但 registration_info",
    "依 requires_registration 為 false",
    "需確認是否為錯誤資訊",
    "僅供查詢",
    "無明確矛盾",
    "文化幣",
    "特約優惠標籤",
    "非主要活動類型",
    "合併或分開標籤",
    "未選",
    "故選",
    "故不選",
    "故未",
    "判斷為需報名",
    "部分活動需網路報名",
    "部分活動為自由參加",
    "需依具體活動項目判斷",
    "兩者無",
    "無明確",
    "無法判斷是否",
    "無法確定是否",
    "依規則",
    "推斷",
    "推測",
    "僅依",
    "未提及",
    "未標示",
    "優惠未提供",
    "discount 欄位",
    "audience 標籤",
    "fee_type 為 unknown",
)
BLOCKING_WARNING_PATTERNS = (
    "矛盾",
    "衝突",
    "不一致",
    "不符",
    "互斥",
    "誤標",
    "誤植",
    "錯誤",
    "存疑",
)
OCR_CONFLICT_WARNING_PATTERNS = BLOCKING_WARNING_PATTERNS


@dataclass(frozen=True)
class AiTaggerConfig:
    base_url: str
    api_key: str
    model: str
    timeout_ms: int
    max_tokens: int
    min_confidence: float


def normalize_base_url(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def get_ai_tagger_config() -> AiTaggerConfig:
    return AiTaggerConfig(
        base_url=normalize_base_url(os.environ.get("AI_BASE_URL", "http://100.107.195.9:8080/v1")),
        api_key=os.environ.get("AI_API_KEY", "sk-no-key-required"),
        model=os.environ.get("AI_MODEL", "local-model"),
        timeout_ms=int(os.environ.get("AI_TIMEOUT_MS", "60000")),
        max_tokens=int(os.environ.get("AI_MAX_TOKENS", "1024")),
        min_confidence=float(os.environ.get("AI_TAG_MIN_CONFIDENCE", "0.6")),
    )


def get_active_tag_map() -> dict[tuple[str, str], Tag]:
    tags = Tag.objects.filter(is_active=True).order_by("tag_type", "name")
    return {(tag.tag_type, tag.name): tag for tag in tags}


def build_tag_whitelist(tag_map: dict[tuple[str, str], Tag]) -> dict[str, list[str]]:
    whitelist: dict[str, list[str]] = {tag_type: [] for tag_type in TAG_TYPES}
    for tag_type, name in sorted(tag_map):
        whitelist.setdefault(tag_type, []).append(name)
    return {tag_type: names for tag_type, names in whitelist.items() if names}


def serialize_activity(activity: Any) -> dict[str, Any]:
    return {
        "id": getattr(activity, "id", None),
        "title": getattr(activity, "title", "") or "",
        "description": getattr(activity, "description", "") or "",
        "district": getattr(activity, "district", "") or "",
        "location": getattr(activity, "location", "") or "",
        "is_free": getattr(activity, "is_free", False),
        "requires_registration": getattr(activity, "requires_registration", False),
        "fee_type": getattr(activity, "fee_type", "") or "",
        "fee_description": getattr(activity, "fee_description", "") or "",
        "registration_info": getattr(activity, "registration_info", "") or "",
        "ocr_text": getattr(activity, "ocr_text", "") or "",
        "ocr_summary": getattr(activity, "ocr_summary", "") or "",
        "activity_uid": getattr(activity, "activity_uid", "") or "",
        "source_key": getattr(activity, "source_key", "") or "",
        "current_tags": get_current_tag_dicts(activity, get_active_tag_map()),
    }


def build_ai_tag_messages(activity: Any, tag_map: dict[tuple[str, str], Tag]) -> list[dict[str, str]]:
    whitelist = build_tag_whitelist(tag_map)
    system_prompt = (
        "你是活動分類助手。只能從白名單選 tag，不可創造新 tag。"
        "不可使用外部常識，只能依輸入欄位判斷。"
        "回傳 JSON object，不要 markdown。"
        'schema: {"tags":[{"name":string,"tag_type":string,"confidence":number,"reason":string}],'
        '"search_keywords":[string],"search_topics":[string],"search_synonyms":[string],"warnings":[string]}。'
        "若資料互相矛盾，請在 warnings 說明，不要自行修正活動資料。"
    )
    user_payload = {
        "tag_whitelist": whitelist,
        "activity": serialize_activity(activity),
        "rules": [
            "tags 必須完全等於白名單中的 name 與 tag_type",
            "tag_type 必須使用白名單中出現的英文 key",
            "白名單沒有列出的 tag_type 不可輸出",
            "只選有明確證據的 tags",
            "最多回 8 個 tags",
            "search_keywords/search_topics/search_synonyms 是搜尋輔助詞，可以包含非白名單自然語言詞，例如自行車、單車、腳踏車、運動、戶外",
            "搜尋輔助詞不得創造活動不存在的日期、地點或費用",
            "reason 必須少於 40 個中文字",
            "warnings 最多 5 則，每則少於 60 個中文字",
            "費用、地區、報名資訊若互相矛盾，列入 warnings",
            "fee_type 為 unknown 且文字沒有明確免費、售票、票價或報名費證據時，只能選金額未提供，不可推論免費或付費",
            "免費、付費、金額未提供三者互斥，只能輸出一個",
            "需報名、免預約只依 registration_info、registration_url、registration_method 或明確報名/預約文字判斷",
            "無優惠只有在文字明確寫無優惠或不適用優惠時才可輸出；缺資訊時選優惠未提供或不選 discount",
            "audience tag 必須有明確對象證據；不要把公務人員或一般民眾弱推成青年",
            "ocr_text 與 ocr_summary 只能作為摘要與 tag 輔助證據，不可覆蓋日期、地點、費用或報名 URL",
            "若 OCR 與頁面欄位互相衝突，列入 warnings 並保守選 tag",
            "不要因 current_tags 已存在就照抄；請依活動內容重新判斷",
        ],
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def create_no_proxy_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


def call_chat_completion(
    messages: list[dict[str, str]],
    *,
    config: AiTaggerConfig | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    response = call_json_with_fallback(messages)
    return {"choices": [{"message": {"content": response.raw_text}}]}


def extract_message_content(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return message.get("content") or ""


def parse_json_object(raw_content: str) -> dict[str, Any]:
    text = (raw_content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("AI response JSON must be an object.")
    return parsed


def build_repair_messages(
    messages: list[dict[str, str]],
    raw_content: str,
    error: Exception,
) -> list[dict[str, str]]:
    return messages + [
        {
            "role": "user",
            "content": (
                "上一個回覆不是合法 JSON 或 schema 不正確。"
                "請只修正 JSON 格式與欄位型別，不要新增事實。"
                f"解析錯誤: {error}\n"
                f"上一個回覆:\n{raw_content}"
            ),
        }
    ]


def normalize_ai_result(
    parsed: dict[str, Any],
    tag_map: dict[tuple[str, str], Tag],
    *,
    min_confidence: float | None = None,
) -> dict[str, Any]:
    if min_confidence is None:
        min_confidence = get_ai_tagger_config().min_confidence
    raw_tags = parsed.get("tags") or []
    if isinstance(raw_tags, dict):
        raw_tags = [raw_tags]
    if isinstance(raw_tags, str):
        raw_tags = [{"name": raw_tags}]

    accepted = []
    missing = []
    rejected = []
    seen: set[tuple[str, str]] = set()
    for item in raw_tags:
        if isinstance(item, str):
            item = {"name": item}
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        tag_type = normalize_tag_type(item.get("tag_type"))
        if not name:
            continue

        tag = tag_map.get((tag_type, name))
        if not tag and not tag_type:
            matches = [candidate for (candidate_type, candidate_name), candidate in tag_map.items() if candidate_name == name]
            if len(matches) == 1:
                tag = matches[0]
                tag_type = tag.tag_type

        confidence = _as_float(item.get("confidence"))
        if tag and confidence is not None and confidence < min_confidence:
            rejected.append(
                {
                    "id": tag.id,
                    "name": tag.name,
                    "tag_type": tag.tag_type,
                    "confidence": confidence,
                    "reason": str(item.get("reason") or "").strip(),
                    "reject_reason": f"confidence below {min_confidence}",
                    "reject_level": "info",
                }
            )
        elif tag:
            key = (tag.tag_type, tag.name)
            if key in seen:
                continue
            seen.add(key)
            accepted.append(
                {
                    "id": tag.id,
                    "name": tag.name,
                    "tag_type": tag.tag_type,
                    "confidence": confidence,
                    "reason": str(item.get("reason") or "").strip(),
                }
            )
        else:
            missing.append(
                {
                    "name": name,
                    "tag_type": tag_type,
                    "confidence": confidence,
                    "reason": str(item.get("reason") or "").strip(),
                    "review_level": "taxonomy",
                }
            )

    warnings = parsed.get("warnings") or []
    if isinstance(warnings, str):
        warnings = [warnings]
    warnings = filter_low_value_warnings(
        [str(warning).strip() for warning in warnings if str(warning).strip()]
    )
    warning_groups = classify_warnings(warnings)
    confidence_values = [tag["confidence"] for tag in accepted if tag["confidence"] is not None]
    confidence = round(sum(confidence_values) / len(confidence_values), 3) if confidence_values else None
    result = {
        "accepted_tags": accepted,
        "missing_tags": missing,
        "rejected_tags": rejected,
        "warnings": warnings,
        "blocking_warnings": warning_groups["blocking_warnings"],
        "info_warnings": warning_groups["info_warnings"],
        "confidence": confidence,
    }
    return result


def tag_activity_with_ai(activity: Any) -> dict[str, Any]:
    tag_map = get_active_tag_map()
    messages = build_ai_tag_messages(activity, tag_map)
    provider_response = call_json_with_fallback(messages)
    raw_content = provider_response.raw_text
    try:
        parsed = provider_response.parsed or parse_json_object(raw_content)
    except Exception as exc:
        repair_response_json = call_chat_completion(build_repair_messages(messages, raw_content, exc))
        raw_content = extract_message_content(repair_response_json)
        parsed = parse_json_object(raw_content)
    normalized = normalize_ai_result(parsed, tag_map)
    normalized["search_keywords"] = normalize_search_terms(parsed.get("search_keywords"), limit=24)
    normalized["search_topics"] = normalize_search_terms(parsed.get("search_topics"), limit=12)
    normalized["search_synonyms"] = normalize_search_terms(parsed.get("search_synonyms"), limit=24)
    apply_deterministic_quality_filters(activity, normalized, tag_map)
    current_tag_dicts = get_current_tag_dicts(activity, tag_map)
    current_keys = {
        (tag["tag_type"], tag["name"])
        for tag in current_tag_dicts
        if tag.get("tag_type") and tag.get("name")
    }
    accepted_keys = {
        (tag["tag_type"], tag["name"])
        for tag in normalized["accepted_tags"]
    }
    normalized.update(
        {
            "activity_id": activity.id,
            "activity_title": activity.title,
            "current_tags": current_tag_dicts,
            "new_tags": [
                tag for tag in normalized["accepted_tags"]
                if (tag["tag_type"], tag["name"]) not in current_keys
            ],
            "existing_tags_not_in_ai_result": [
                {"name": name, "tag_type": tag_type}
                for tag_type, name in sorted(current_keys - accepted_keys)
            ],
            "manual_evaluation": (
                "needs_review"
                if normalized["blocking_warnings"] or has_blocking_rejections(normalized)
                else "review_recommended"
            ),
            "raw_response": raw_content,
            "provider": provider_response.provider,
            "model": provider_response.model,
        }
    )
    return normalized


def normalize_search_terms(values: Any, limit: int = 24) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = re.split(r"[,，、\s]+", values)
    terms = []
    for value in values:
        term = re.sub(r"\s+", "", str(value or "").strip().lstrip("#"))
        if not term or len(term) > 20:
            continue
        if term not in terms:
            terms.append(term)
        if len(terms) >= limit:
            break
    return terms


def get_current_tag_dicts(activity: Any, tag_map: dict[tuple[str, str], Tag]) -> list[dict[str, str]]:
    current_tags = getattr(activity, "current_tags", None)
    if current_tags is not None:
        normalized = []
        for item in current_tags:
            if isinstance(item, str):
                name = item.strip()
                tag_type = infer_unique_tag_type(name, tag_map)
            elif isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                tag_type = normalize_tag_type(item.get("tag_type"))
                if not tag_type:
                    tag_type = infer_unique_tag_type(name, tag_map)
            else:
                continue
            if name:
                normalized.append({"name": name, "tag_type": tag_type})
        return sorted(normalized, key=lambda tag: (tag.get("tag_type") or "", tag.get("name") or ""))

    tags_manager = getattr(activity, "tags", None)
    if tags_manager is None:
        return []
    return [
        {"name": tag.name, "tag_type": tag.tag_type}
        for tag in tags_manager.filter(is_active=True).order_by("tag_type", "name")
    ]


def infer_unique_tag_type(name: str, tag_map: dict[tuple[str, str], Tag]) -> str:
    matches = [tag_type for tag_type, tag_name in tag_map if tag_name == name]
    return matches[0] if len(matches) == 1 else ""


def normalize_tag_type(value: Any) -> str:
    tag_type = str(value or "").strip()
    return TAG_TYPE_ALIASES.get(tag_type, tag_type)


def apply_deterministic_quality_filters(
    activity: Activity,
    result: dict[str, Any],
    tag_map: dict[tuple[str, str], Tag],
) -> None:
    reject_conflicting_region_tags(activity, result, tag_map)
    reject_unsupported_cost_tags(activity, result)
    reject_mutually_exclusive_cost_tags(result)
    reject_unsupported_discount_tags(activity, result)
    reject_weak_audience_tags(activity, result)
    recalculate_confidence(result)


def reject_conflicting_region_tags(
    activity: Activity,
    result: dict[str, Any],
    tag_map: dict[tuple[str, str], Tag],
) -> None:
    region_names = sorted(
        name for tag_type, name in tag_map
        if tag_type == "region"
    )
    strong_regions = extract_strong_region_evidence(activity, region_names)
    if not strong_regions:
        return

    kept = []
    for tag in result.get("accepted_tags", []):
        if tag.get("tag_type") != "region" or tag.get("name") in strong_regions:
            kept.append(tag)
            continue
        rejected = dict(tag)
        rejected["reject_reason"] = (
            "region conflicts with title/location evidence: "
            + ", ".join(sorted(strong_regions))
        )
        rejected["reject_level"] = "blocking"
        result.setdefault("rejected_tags", []).append(rejected)
        result.setdefault("warnings", []).append(
            f"AI suggested region '{tag.get('name')}', but title/location indicates "
            f"{', '.join(sorted(strong_regions))}."
        )
    result["accepted_tags"] = kept
    warning_groups = classify_warnings(result.get("warnings", []))
    result["blocking_warnings"] = warning_groups["blocking_warnings"]
    result["info_warnings"] = warning_groups["info_warnings"]


def extract_strong_region_evidence(activity: Activity, region_names: list[str]) -> set[str]:
    region_set = set(region_names)
    district = str(getattr(activity, "district", "") or "").replace("區", "").strip()
    if district in region_set:
        return {district}

    strong_text = f"{getattr(activity, 'title', '') or ''} {getattr(activity, 'location', '') or ''}"
    regions = {
        name for name in region_names
        if name and f"{name}區" in strong_text
    }
    for name in region_names:
        if not name or name == "桃園":
            continue
        if name in strong_text:
            regions.add(name)
    if "桃園" in region_set and ("桃園區" in strong_text or "桃園市桃園區" in strong_text):
        regions.add("桃園")
    return regions


def reject_unsupported_cost_tags(activity: Activity, result: dict[str, Any]) -> None:
    fee_type = str(getattr(activity, "fee_type", "") or "").strip()
    is_free = getattr(activity, "is_free", None)
    text = _activity_evidence_text(activity)
    has_free_evidence = any(keyword in text for keyword in FREE_EVIDENCE)
    has_paid_evidence = any(keyword in text for keyword in PAID_EVIDENCE)
    kept = []
    for tag in result.get("accepted_tags", []):
        if tag.get("tag_type") != "cost":
            kept.append(tag)
            continue
        name = tag.get("name")
        reject_reason = ""
        if name == "免費" and not (fee_type in {"free", "ticket_free"} or is_free is True or has_free_evidence):
            reject_reason = "free cost tag lacks explicit evidence"
        elif name == "付費" and not (fee_type == "paid" or is_free is False and has_paid_evidence or has_paid_evidence):
            reject_reason = "paid cost tag lacks explicit evidence"
        elif name == "金額未提供" and fee_type in {"free", "ticket_free", "paid"}:
            reject_reason = f"fee_type is {fee_type}"
        elif name == "需報名" and not _has_registration_evidence(activity):
            reject_reason = "registration tag lacks explicit evidence"
        elif name == "免預約" and not _has_no_reservation_evidence(activity):
            reject_reason = "no-reservation tag lacks explicit evidence"

        if reject_reason:
            _reject_tag(result, tag, reject_reason, "info")
        else:
            kept.append(tag)
    result["accepted_tags"] = kept


def reject_mutually_exclusive_cost_tags(result: dict[str, Any]) -> None:
    cost_value_tags = [
        tag for tag in result.get("accepted_tags", [])
        if tag.get("tag_type") == "cost" and tag.get("name") in COST_VALUE_TAGS
    ]
    if len(cost_value_tags) <= 1:
        return
    priority = {"免費": 3, "付費": 3, "金額未提供": 1}
    keep = max(
        cost_value_tags,
        key=lambda tag: (priority.get(tag.get("name"), 0), tag.get("confidence") or 0),
    )
    kept = []
    for tag in result.get("accepted_tags", []):
        if tag.get("tag_type") == "cost" and tag.get("name") in COST_VALUE_TAGS and tag is not keep:
            _reject_tag(result, tag, f"mutually exclusive with {keep.get('name')}", "blocking")
        else:
            kept.append(tag)
    result["accepted_tags"] = kept


def reject_unsupported_discount_tags(activity: Activity, result: dict[str, Any]) -> None:
    text = _activity_evidence_text(activity)
    kept = []
    for tag in result.get("accepted_tags", []):
        if tag.get("tag_type") == "discount" and tag.get("name") in STRICT_DISCOUNT_TAGS:
            if not any(keyword in text for keyword in NO_DISCOUNT_EVIDENCE):
                _reject_tag(result, tag, "no-discount tag lacks explicit evidence", "info")
                continue
        kept.append(tag)
    result["accepted_tags"] = kept


def reject_weak_audience_tags(activity: Activity, result: dict[str, Any]) -> None:
    text = _activity_evidence_text(activity)
    kept = []
    for tag in result.get("accepted_tags", []):
        if tag.get("tag_type") != "audience":
            kept.append(tag)
            continue
        name = tag.get("name")
        if name == "一般":
            kept.append(tag)
            continue
        evidence = AUDIENCE_EVIDENCE.get(name, ())
        if evidence and any(keyword in text for keyword in evidence):
            kept.append(tag)
        else:
            _reject_tag(result, tag, "audience tag lacks explicit evidence", "info")
    result["accepted_tags"] = kept


def _reject_tag(result: dict[str, Any], tag: dict[str, Any], reason: str, level: str) -> None:
    rejected = dict(tag)
    rejected["reject_reason"] = reason
    rejected["reject_level"] = level
    result.setdefault("rejected_tags", []).append(rejected)


def _activity_evidence_text(activity: Activity) -> str:
    fields = (
        "title",
        "description",
        "raw_content",
        "district",
        "location",
        "fee_description",
        "registration_info",
        "ocr_text",
        "ocr_summary",
    )
    return " ".join(str(getattr(activity, field, "") or "") for field in fields)


def _has_registration_evidence(activity: Activity) -> bool:
    if getattr(activity, "requires_registration", None) is True:
        return True
    text = _activity_evidence_text(activity)
    return any(keyword in text for keyword in ("報名", "線上報名", "預約", "登記", "registration", "Accupass", "BeClass"))


def _has_no_reservation_evidence(activity: Activity) -> bool:
    text = _activity_evidence_text(activity)
    return any(keyword in text for keyword in ("免預約", "無須預約", "不用預約", "自由入場", "自由進場"))


def filter_low_value_warnings(warnings: list[str]) -> list[str]:
    filtered = []
    seen = set()
    for warning in warnings:
        if any(pattern in warning for pattern in LOW_VALUE_WARNING_PATTERNS):
            continue
        if warning in seen:
            continue
        seen.add(warning)
        filtered.append(warning)
    return filtered


def classify_warnings(warnings: list[str]) -> dict[str, list[str]]:
    blocking = []
    info = []
    for warning in warnings:
        if is_ocr_conflict_warning(warning):
            info.append(warning)
        elif any(pattern in warning for pattern in INFO_WARNING_PATTERNS):
            info.append(warning)
        elif any(pattern in warning for pattern in BLOCKING_WARNING_PATTERNS):
            blocking.append(warning)
        else:
            info.append(warning)
    return {
        "blocking_warnings": blocking,
        "info_warnings": info,
    }


def is_ocr_conflict_warning(warning: str) -> bool:
    return "OCR" in warning.upper() and any(
        pattern in warning for pattern in OCR_CONFLICT_WARNING_PATTERNS
    )


def has_blocking_rejections(result: dict[str, Any]) -> bool:
    return any(
        tag.get("reject_level") == "blocking"
        for tag in result.get("rejected_tags", [])
    )


def recalculate_confidence(result: dict[str, Any]) -> None:
    confidence_values = [
        tag.get("confidence")
        for tag in result.get("accepted_tags", [])
        if tag.get("confidence") is not None
    ]
    result["confidence"] = (
        round(sum(confidence_values) / len(confidence_values), 3)
        if confidence_values
        else None
    )


def apply_accepted_tags(activity: Activity, result: dict[str, Any]) -> list[Tag]:
    tag_ids = [tag["id"] for tag in result.get("accepted_tags", []) if tag.get("id")]
    tags = list(Tag.objects.filter(id__in=tag_ids, is_active=True))
    if tags:
        activity.tags.add(*tags)
    return tags


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

