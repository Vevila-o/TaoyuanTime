import base64
import json
import mimetypes
import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image


SUPPORTED_DIRECT_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


@dataclass(frozen=True)
class OcrConfig:
    base_url: str
    api_key: str
    model: str
    timeout_ms: int
    provider: str = "local"


def normalize_base_url(value):
    return str(value or "").strip().rstrip("/")


DISABLED_VALUES = {"", "0", "false", "no", "off", "not", "none", "null", "disable", "disabled"}


def is_disabled_value(value):
    return str(value if value is not None else "").strip().lower() in DISABLED_VALUES


def local_enabled():
    explicit = os.environ.get("LOCAL", os.environ.get("AI_LOCAL_ENABLED", None))
    if explicit is not None:
        return not is_disabled_value(explicit)
    raw_base_url = os.environ.get("AI_BASE_URL")
    if raw_base_url is not None and is_disabled_value(raw_base_url):
        return False
    return bool(normalize_base_url(os.environ.get("AI_BASE_URL", "")))


def provider_order():
    raw = os.environ.get("AI_PROVIDER_ORDER", "openai")
    providers = []
    use_local = local_enabled()
    for item in raw.split(","):
        provider = item.strip().lower()
        if provider == "local" and not use_local:
            continue
        if provider in {"local", "openai"} and provider not in providers:
            providers.append(provider)
    if providers:
        return providers
    return ["local"] if use_local else ["openai"]

def get_ocr_config(provider="local"):
    if provider == "openai":
        return OcrConfig(
            base_url=normalize_base_url(os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")),
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
            timeout_ms=int(os.environ.get("AI_TIMEOUT_MS", "60000")),
            provider="openai",
        )
    return OcrConfig(
        base_url=normalize_base_url(os.environ.get("AI_BASE_URL", "")),
        api_key=os.environ.get("AI_API_KEY", "sk-no-key-required"),
        model=os.environ.get("AI_MODEL", "qwen"),
        timeout_ms=int(os.environ.get("AI_TIMEOUT_MS", "60000")),
        provider="local",
    )


def create_no_proxy_session():
    session = requests.Session()
    session.trust_env = False
    return session


def encode_image_data_url(image_path):
    path = Path(image_path)
    ext = path.suffix.lower()
    if ext == ".gif":
        with Image.open(path) as image:
            image.seek(0)
            frame = image.convert("RGB")
            buffer = BytesIO()
            frame.save(buffer, format="PNG")
        mime_type = "image/png"
        payload = buffer.getvalue()
    elif ext in SUPPORTED_DIRECT_MIME:
        mime_type = SUPPORTED_DIRECT_MIME[ext]
        payload = path.read_bytes()
    else:
        with Image.open(path) as image:
            converted = image.convert("RGB")
            buffer = BytesIO()
            converted.save(buffer, format="JPEG", quality=92)
        mime_type = mimetypes.guess_type(str(path))[0] or "image/jpeg"
        if not mime_type.startswith("image/"):
            mime_type = "image/jpeg"
        payload = buffer.getvalue()
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_ocr_messages(data_url):
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "請辨識這張活動海報或主視覺中的文字。只回傳 JSON object，不要 markdown。"
                        "schema: {\"ocr_text\": string, \"ocr_summary\": string, "
                        "\"confidence\": number, \"warnings\": [string]}。"
                        "ocr_text 保留重要文字、日期、地點、費用與報名資訊；"
                        "ocr_summary 用 80 字內摘要海報內容。"
                    ),
                },
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]


def completion_url(config):
    return config.base_url if config.base_url.endswith("/chat/completions") else f"{config.base_url}/chat/completions"


def build_ocr_payload(image_path, *, config=None):
    config = config or get_ocr_config()
    data_url = encode_image_data_url(image_path)
    payload = {
        "model": config.model,
        "messages": build_ocr_messages(data_url),
        "temperature": 0,
        "max_tokens": int(os.environ.get("AI_MAX_TOKENS", "1024")),
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    if config.provider == "local":
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    return payload


def extract_message_content(response_json):
    choices = response_json.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return message.get("content") or ""


def parse_json_object(raw_content):
    text = (raw_content or "").strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").strip()
        text = text.removesuffix("```").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("OCR response JSON must be an object.")
    return parsed


def normalize_ocr_result(parsed, *, provider="", model=""):
    warnings = parsed.get("warnings") or []
    if isinstance(warnings, str):
        warnings = [warnings]
    try:
        confidence = float(parsed.get("confidence"))
    except (TypeError, ValueError):
        confidence = None
    return {
        "ocr_text": str(parsed.get("ocr_text") or "").strip(),
        "ocr_summary": str(parsed.get("ocr_summary") or "").strip(),
        "ocr_confidence": confidence,
        "ocr_warnings": [str(item).strip() for item in warnings if str(item).strip()],
        "provider": provider,
        "model": model,
    }


def call_ocr_once(image_path, *, config, session=None):
    if config.provider == "openai" and not config.api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    client = session or create_no_proxy_session()
    payload = build_ocr_payload(image_path, config=config)
    headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
    response = client.post(
        completion_url(config),
        json=payload,
        headers=headers,
        timeout=config.timeout_ms / 1000,
    )
    if response.status_code >= 400 and "response_format" in payload:
        payload.pop("response_format")
        response = client.post(
            completion_url(config),
            json=payload,
            headers=headers,
            timeout=config.timeout_ms / 1000,
        )
    response.raise_for_status()
    raw_content = extract_message_content(response.json())
    try:
        return normalize_ocr_result(parse_json_object(raw_content), provider=config.provider, model=config.model)
    except Exception:
        text = (raw_content or "").strip()
        if not text:
            raise
        return {
            "ocr_text": text,
            "ocr_summary": text[:120],
            "ocr_confidence": None,
            "ocr_warnings": ["ocr_response_not_json"],
            "provider": config.provider,
            "model": config.model,
        }


def call_ocr(image_path, *, config=None, session=None):
    if config is not None:
        return call_ocr_once(image_path, config=config, session=session)
    errors = []
    for provider in provider_order():
        cfg = get_ocr_config(provider)
        try:
            return call_ocr_once(image_path, config=cfg, session=session)
        except Exception as exc:
            errors.append(f"{provider}: {exc}")
    raise RuntimeError("; ".join(errors))


def _find_ocr_asset(event):
    for asset in event.get("extracted_assets") or []:
        if asset.get("ocr_candidate") and asset.get("image_role") in {"poster", "main_visual"} and asset.get("local_path"):
            return asset
    return None


def apply_ocr_to_event(event: dict[str, Any], *, session=None, config=None) -> dict[str, Any]:
    if not event.get("front_ready"):
        event["ocr_ready"] = False
        event["ocr_status"] = "skipped_not_front_pool"
        event.setdefault("ocr_warnings", [])
        return event

    asset = _find_ocr_asset(event)
    if not asset:
        event["ocr_ready"] = False
        event["ocr_status"] = "skipped_no_image"
        event["ocr_image_url"] = None
        event["ocr_image_path"] = None
        event.setdefault("ocr_warnings", [])
        return event

    event["ocr_image_url"] = asset.get("url") or asset.get("asset_url") or event.get("poster_url")
    event["ocr_image_path"] = asset.get("local_path")
    try:
        result = call_ocr(asset["local_path"], session=session, config=config)
    except Exception as exc:
        warnings = event.setdefault("ocr_warnings", [])
        warnings.append(str(exc))
        event["ocr_ready"] = False
        event["ocr_status"] = "failed"
        return event

    event.update(result)
    event["ocr_ready"] = bool(event.get("ocr_text") or event.get("ocr_summary"))
    event["ocr_status"] = "success" if event["ocr_ready"] else "failed"
    return event

