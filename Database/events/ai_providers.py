import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings


@dataclass(frozen=True)
class AIProviderResponse:
    provider: str
    model: str
    raw_text: str
    parsed: dict[str, Any] | None = None


def create_no_proxy_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


DISABLED_VALUES = {"", "0", "false", "no", "off", "not", "none", "null", "disable", "disabled"}


def is_disabled_value(value: Any) -> bool:
    return str(value if value is not None else "").strip().lower() in DISABLED_VALUES


def local_enabled() -> bool:
    explicit = os.environ.get("LOCAL", os.environ.get("AI_LOCAL_ENABLED", None))
    if explicit is not None:
        return not is_disabled_value(explicit)
    raw_base_url = os.environ.get("AI_BASE_URL")
    if raw_base_url is not None and is_disabled_value(raw_base_url):
        return False
    return bool(local_base_url())


def local_base_url() -> str:
    return (os.environ.get("AI_BASE_URL") or getattr(settings, "AI_BASE_URL", "")).strip().rstrip("/")

def local_api_key() -> str:
    return os.environ.get("AI_API_KEY") or getattr(settings, "AI_API_KEY", "sk-no-key-required")


def local_model() -> str:
    return os.environ.get("AI_MODEL") or getattr(settings, "AI_MODEL", "qwen")


def openai_base_url() -> str:
    return (os.environ.get("OPENAI_BASE_URL") or getattr(settings, "OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")


def openai_api_key() -> str:
    return os.environ.get("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", "")


def openai_model() -> str:
    return os.environ.get("OPENAI_MODEL") or getattr(settings, "OPENAI_MODEL", "gpt-4.1-mini")


def provider_order() -> list[str]:
    raw = os.environ.get("AI_PROVIDER_ORDER") or getattr(settings, "AI_PROVIDER_ORDER", "openai")
    providers = [item.strip().lower() for item in raw.split(",") if item.strip()]
    valid = []
    use_local = local_enabled()
    for provider in providers:
        if provider == "local" and not use_local:
            continue
        if provider in {"local", "openai"} and provider not in valid:
            valid.append(provider)
    if valid:
        return valid
    return ["local"] if use_local else ["openai"]

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


def payload_messages(system_prompt: str, payload: Any) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
    ]


def completion_url(base_url: str) -> str:
    return base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"


def call_openai_compatible_text(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    response_format: dict[str, str] | None = None,
    session: requests.Session | None = None,
) -> AIProviderResponse:
    if not base_url:
        raise RuntimeError(f"{provider} base URL is not configured")
    if provider == "openai" and not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": int(getattr(settings, "AI_MAX_TOKENS", os.environ.get("AI_MAX_TOKENS", 800))),
        "stream": False,
    }
    if provider == "local":
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    if response_format:
        payload["response_format"] = response_format
    client = session or create_no_proxy_session()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response = client.post(
        completion_url(base_url),
        json=payload,
        headers=headers,
        timeout=max(1, int(getattr(settings, "AI_TIMEOUT_MS", os.environ.get("AI_TIMEOUT_MS", 8000))) / 1000),
    )
    if response.status_code >= 400 and "response_format" in payload:
        payload.pop("response_format")
        response = client.post(
            completion_url(base_url),
            json=payload,
            headers=headers,
            timeout=max(1, int(getattr(settings, "AI_TIMEOUT_MS", os.environ.get("AI_TIMEOUT_MS", 8000))) / 1000),
        )
    raise_for_status_without_secrets(response, provider=provider, model=model)
    data = response.json()
    raw_text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not raw_text:
        raise RuntimeError(f"{provider} returned empty text")
    return AIProviderResponse(provider=provider, model=model, raw_text=raw_text)


def call_local_text(
    messages: list[dict[str, Any]],
    *,
    response_format: dict[str, str] | None = None,
    session: requests.Session | None = None,
) -> AIProviderResponse:
    return call_openai_compatible_text(
        provider="local",
        base_url=local_base_url(),
        api_key=local_api_key(),
        model=local_model(),
        messages=messages,
        response_format=response_format,
        session=session,
    )


def call_openai_text(
    messages: list[dict[str, Any]],
    *,
    response_format: dict[str, str] | None = None,
    session: requests.Session | None = None,
) -> AIProviderResponse:
    return call_openai_compatible_text(
        provider="openai",
        base_url=openai_base_url(),
        api_key=openai_api_key(),
        model=openai_model(),
        messages=messages,
        response_format=response_format,
        session=session,
    )


def raise_for_status_without_secrets(response: requests.Response, *, provider: str, model: str) -> None:
    if response.status_code < 400:
        return
    detail = ""
    try:
        payload = response.json()
        detail = str(payload.get("error") or payload)[:500]
    except Exception:
        detail = response.text[:500]
    raise RuntimeError(f"{provider} {model} HTTP {response.status_code}: {detail}")


def call_json_with_fallback(messages: list[dict[str, Any]]) -> AIProviderResponse:
    errors = []
    callers = {
        "local": lambda: call_local_text(messages, response_format={"type": "json_object"}),
        "openai": lambda: call_openai_text(messages, response_format={"type": "json_object"}),
    }
    for provider_name in provider_order():
        try:
            response = callers[provider_name]()
            return AIProviderResponse(
                provider=response.provider,
                model=response.model,
                raw_text=response.raw_text,
                parsed=parse_json_object(response.raw_text),
            )
        except Exception as exc:
            errors.append(f"{provider_name}: {exc}")
    raise RuntimeError("; ".join(errors))


def call_text_with_fallback(messages: list[dict[str, Any]]) -> AIProviderResponse:
    errors = []
    callers = {
        "local": lambda: call_local_text(messages),
        "openai": lambda: call_openai_text(messages),
    }
    for provider_name in provider_order():
        try:
            return callers[provider_name]()
        except Exception as exc:
            errors.append(f"{provider_name}: {exc}")
    raise RuntimeError("; ".join(errors))

