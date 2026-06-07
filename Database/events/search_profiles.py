import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from django.conf import settings
from django.utils import timezone

from events.ai_providers import call_json_with_fallback, payload_messages
from events.models import AIProcessingLog, Activity, ActivitySearchProfile


SEMANTIC_EXPANSIONS = {
    '腳踏車': ['自行車', '單車', '騎車', '運動', '戶外'],
    '自行車': ['腳踏車', '單車', '騎車', '運動', '戶外'],
    '單車': ['自行車', '腳踏車', '騎車', '運動', '戶外'],
    '騎車': ['自行車', '單車', '腳踏車', '運動', '戶外'],
    '運動': ['戶外', '健走', '路跑', '自行車', '單車', '體驗'],
    '戶外': ['運動', '健走', '旅行', '自然', '體驗'],
    '免費': ['免門票', '不用錢', '免費入場'],
    '親子': ['兒童', '家庭', '小朋友', '孩子'],
    '藝文': ['展覽', '表演', '音樂', '藝術', '文化'],
}

RAW_HTML_MAIN_SELECTORS = [
    '.page-content',
    'main',
    'article',
    '[role=main]',
    '#content',
    '.content',
]

RAW_HTML_REMOVE_SELECTORS = [
    'script',
    'style',
    'noscript',
    'svg',
    'header',
    'nav',
    'footer',
    'aside',
    'form',
    'button',
]

RAW_HTML_NOISE_PHRASES = [
    ':::',
    '首頁',
    '網站導覽',
    '跳過此子選單列',
    '網頁功能',
    '列印內容',
    '回上一頁',
    '回最上面',
]


def activity_profile_hash(activity: Activity) -> str:
    payload = {
        'title': activity.title,
        'description': activity.description,
        'raw_content': activity.raw_content[:3000],
        'raw_html_path': activity.raw_html_path,
        'raw_html_text': raw_html_text_for_activity(activity, limit=3000),
        'district': activity.district,
        'location': activity.location,
        'ai_summary': activity.ai_summary,
        'ocr_text': activity.ocr_text[:2000],
        'ocr_summary': activity.ocr_summary,
        'tags': list(activity.tags.filter(is_active=True).values_list('name', flat=True)),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def normalize_terms(values: Any, limit: int = 24) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = re.split(r'[,，、\s]+', values)
    terms = []
    for value in values:
        term = re.sub(r'\s+', '', str(value or '').strip().lstrip('#'))
        if not term or len(term) > 20:
            continue
        if term not in terms:
            terms.append(term)
        if len(terms) >= limit:
            break
    return terms


def fallback_profile_terms(activity: Activity, ai_result: dict[str, Any] | None = None) -> tuple[list[str], list[str], list[str]]:
    base_terms = []
    for tag in activity.tags.filter(is_active=True):
        base_terms.append(tag.name)
    for item in (ai_result or {}).get('accepted_tags') or []:
        base_terms.append(item.get('name'))
    text = ' '.join([
        activity.title or '',
        activity.description or '',
        activity.raw_content[:1500] or '',
        raw_html_text_for_activity(activity, limit=1500),
        activity.ai_summary or '',
        activity.ocr_summary or '',
        activity.ocr_text[:1000] or '',
    ])
    for key, expansions in SEMANTIC_EXPANSIONS.items():
        if key in text or key in base_terms:
            base_terms.append(key)
            base_terms.extend(expansions)
    keywords = normalize_terms(base_terms, limit=30)
    topics = normalize_terms([term for term in keywords if term in {'運動', '戶外', '親子', '藝文', '展覽', '音樂', '市集', '美食', '自行車', '單車'}], limit=12)
    synonyms = []
    for term in keywords:
        synonyms.extend(SEMANTIC_EXPANSIONS.get(term, []))
    return keywords, topics, normalize_terms(synonyms, limit=30)


def build_search_text(activity: Activity, keywords=None, topics=None, synonyms=None) -> str:
    tag_names = list(activity.tags.filter(is_active=True).values_list('name', flat=True))
    parts = [
        activity.title,
        activity.description,
        activity.raw_content,
        raw_html_text_for_activity(activity, limit=3000),
        activity.district,
        activity.location,
        activity.source_agency,
        activity.ai_summary,
        activity.ocr_summary,
        activity.ocr_text,
        ' '.join(tag_names),
        ' '.join(normalize_terms(keywords, limit=80)),
        ' '.join(normalize_terms(topics, limit=40)),
        ' '.join(normalize_terms(synonyms, limit=80)),
    ]
    return re.sub(r'\s+', ' ', ' '.join(str(part or '') for part in parts)).strip()


def update_activity_search_profile(activity: Activity, *, ai_result: dict[str, Any] | None = None, force: bool = False) -> ActivitySearchProfile:
    source_hash = activity_profile_hash(activity)
    existing = getattr(activity, 'search_profile', None)
    if existing and existing.source_hash == source_hash and existing.status == 'success' and not force:
        return existing

    started_at = time.monotonic()
    keywords, topics, synonyms = fallback_profile_terms(activity, ai_result=ai_result)
    raw_source_text = build_raw_source_text(activity)
    provider_model = 'rule'
    status = 'success'
    error = ''
    try:
        response = call_json_with_fallback(
            payload_messages(
                '你是桃園活動搜尋語意整理器。只輸出 JSON。'
                '請根據活動內容產生搜尋用 keywords/topics/synonyms，可包含自然語言同義詞。'
                '不可創造活動事實、日期、地點或費用。keywords 最多 18 個，topics 最多 8 個，synonyms 最多 18 個。',
                {
                    'activity': {
                        'title': activity.title,
                        'description': activity.description[:1500],
                        'raw_source_text': raw_source_text[:2500],
                        'district': activity.district,
                        'location': activity.location,
                        'ai_summary': activity.ai_summary[:500],
                        'ocr_summary': activity.ocr_summary[:500],
                        'ocr_text': activity.ocr_text[:1500],
                        'current_tags': list(activity.tags.filter(is_active=True).values_list('name', flat=True)),
                        'ai_accepted_tags': (ai_result or {}).get('accepted_tags') or [],
                    },
                    'examples': {
                        '自行車活動': ['自行車', '單車', '腳踏車', '運動', '戶外'],
                        '免費活動': ['免費', '免門票', '不用錢'],
                    },
                    'output_schema': {
                        'keywords': 'array of search words',
                        'topics': 'array of broad activity topics',
                        'synonyms': 'array of related natural language words',
                    },
                },
            )
        )
        parsed = response.parsed or {}
        keywords = merge_terms(keywords, parsed.get('keywords'), limit=30)
        topics = merge_terms(topics, parsed.get('topics'), limit=16)
        synonyms = merge_terms(synonyms, parsed.get('synonyms'), limit=30)
        provider_model = f'{response.provider}:{response.model}'[:100]
    except Exception as exc:
        status = 'success' if keywords or topics or synonyms else 'failed'
        error = str(exc)[:1000]

    profile, _ = ActivitySearchProfile.objects.update_or_create(
        activity=activity,
        defaults={
            'search_text': build_search_text(activity, keywords, topics, synonyms),
            'keywords': keywords,
            'topics': topics,
            'synonyms': synonyms,
            'source_hash': source_hash,
            'status': status,
            'error': error,
            'provider_model': provider_model,
        },
    )
    AIProcessingLog.objects.create(
        activity=activity,
        task_type='search_profile',
        model=provider_model,
        prompt_version='search-profile-v1',
        input_summary=activity.title[:500],
        output_json={
            'keywords': keywords,
            'topics': topics,
            'synonyms': synonyms,
            'provider_model': provider_model,
        },
        latency_ms=int((time.monotonic() - started_at) * 1000),
        status='success' if status == 'success' else 'failed',
        error=error,
    )
    return profile


def merge_terms(*groups, limit: int = 30) -> list[str]:
    merged = []
    for group in groups:
        for term in normalize_terms(group, limit=limit):
            if term not in merged:
                merged.append(term)
            if len(merged) >= limit:
                return merged
    return merged


def build_raw_source_text(activity: Activity) -> str:
    parts = [
        activity.raw_content or '',
        raw_html_text_for_activity(activity, limit=4000),
    ]
    return re.sub(r'\s+', ' ', ' '.join(part for part in parts if part)).strip()


def raw_html_text_for_activity(activity: Activity, limit: int = 3000) -> str:
    cached = getattr(activity, '_raw_html_text_cache', None)
    if cached is not None:
        return cached[:limit]
    raw_path = (activity.raw_html_path or '').strip()
    if not raw_path:
        return ''
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(settings.BASE_DIR) / path
    try:
        if not path.exists() or not path.is_file():
            return ''
        html = path.read_text(encoding='utf-8', errors='ignore')[:200000]
    except OSError:
        return ''
    soup = BeautifulSoup(html, 'html.parser')
    text_root = cleaned_html_text_root(soup)
    text = text_root.get_text(' ')
    text = strip_raw_html_noise(text)
    text = re.sub(r'\s+', ' ', text).strip()
    activity._raw_html_text_cache = text[:5000]
    return activity._raw_html_text_cache[:limit]


def cleaned_html_text_root(soup: BeautifulSoup):
    for node in soup.select(','.join(RAW_HTML_REMOVE_SELECTORS)):
        node.decompose()
    for selector in RAW_HTML_MAIN_SELECTORS:
        node = soup.select_one(selector)
        if node:
            return node
    return soup.body or soup


def strip_raw_html_noise(text: str) -> str:
    cleaned = text or ''
    for phrase in RAW_HTML_NOISE_PHRASES:
        cleaned = cleaned.replace(phrase, ' ')
    cleaned = re.sub(r'跳過此[^，。]*?(?:Enter|Tab)[^，。]*', ' ', cleaned, flags=re.IGNORECASE)
    return cleaned


def mark_search_profile_stale(activity: Activity) -> None:
    profile = getattr(activity, 'search_profile', None)
    if profile:
        profile.status = 'stale'
        profile.save(update_fields=['status', 'updated_at'])


def set_link_health(activity: Activity, status: str, error: str = '') -> None:
    activity.official_link_status = status
    activity.official_link_checked_at = timezone.now()
    activity.official_link_error = error[:1000]
    activity.save(update_fields=['official_link_status', 'official_link_checked_at', 'official_link_error', 'updated_at'])
