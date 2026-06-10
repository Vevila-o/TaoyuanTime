import re
from urllib.parse import urlparse


REGISTRATION_URL_RE = re.compile(r'https?://[^\s<>"）)]+', re.I)
REGISTRATION_HOST_HINTS = ("accupass.com", "forms.gle", "docs.google.com/forms")
REGISTRATION_TEXT_HINTS = ("網路報名", "報名連結", "Accupass", "Google 表單", "報名網址", "需事先報名")
COMMON_REGISTRATION_PAGE_HINTS = ("ActiveList.aspx", "sms=20299")
FREE_EVIDENCE_KEYWORDS = ("免費入場", "自由參加", "免費")
PAID_EVIDENCE_KEYWORDS = ("票價", "售票", "購票", "報名費", "門票", "收費", "材料費", "入場費", "付費")
PAID_AMOUNT_RE = re.compile(r'費用\s*[:：]?\s*(?:NT\$|新臺幣|新台幣|\$)?\s*\d[\d,]*(?:\s*元)?', re.I)
PAID_PER_PERSON_RE = re.compile(r'每人\s*(?:NT\$|新臺幣|新台幣|\$)?\s*\d[\d,]*(?:\s*元)?', re.I)


def extract_fee(event, debug_log=None):
    """
    Extracts fee information.
    """
    if not event: return event
    
    desc = " ".join([
        str(event.get("fee_raw_text") or ""),
        str(event.get("enriched_metadata_text") or ""),
        str(event.get("clean_description") or ""),
        str(event.get("raw_content") or ""),
    ])
    registration_url, registration_evidence = extract_registration_url(desc, event.get("registration_url"))
    if registration_evidence:
        event["registration_method"] = "online"
        event["registration_url"] = registration_url or event.get("registration_url")
        event["registration_parse_status"] = "success"
        event["registration_evidence_text"] = registration_evidence
    else:
        event["registration_method"] = "unknown"
        event["registration_url"] = None
        event["registration_parse_status"] = "not_found"
        event["registration_evidence_text"] = ""

    free_ticket_keywords = ["索票進場", "免費索票", "索票入場"]
    free_evidence = first_keyword(desc, FREE_EVIDENCE_KEYWORDS)
    paid_evidence = first_keyword(desc, PAID_EVIDENCE_KEYWORDS) or fee_amount_evidence(desc) or per_person_evidence(desc)
    is_free_ticket = any(kw in desc for kw in free_ticket_keywords)
    if (free_evidence or is_free_ticket) and paid_evidence:
        event["is_free"] = None
        event["fee_type"] = "mixed"
        event["fee_text"] = "部分免費、部分收費"
        event["fee_evidence_text"] = "；".join(filter(None, [free_evidence or "索票進場", paid_evidence]))
        event["fee_parse_status"] = "success"
    elif free_evidence or is_free_ticket:
        event["is_free"] = True
        event["fee_type"] = "ticket_free" if is_free_ticket else "free"
        event["fee_text"] = "索票進場" if is_free_ticket else free_evidence
        event["fee_evidence_text"] = "索票進場" if is_free_ticket else free_evidence
        event["fee_parse_status"] = "success"
    elif paid_evidence:
        event["is_free"] = False
        event["fee_type"] = "paid"
        event["fee_text"] = paid_evidence
        event["fee_evidence_text"] = paid_evidence
        event["fee_parse_status"] = "success"
    else:
        # 沒有明確提到收費 → 推定為免費
        event["is_free"] = True
        event["fee_type"] = "assumed_free"
        event["fee_text"] = "未明確收費（推定免費）"
        event["fee_evidence_text"] = ""
        event["fee_parse_status"] = "assumed"
        if debug_log is not None:
            debug_log.append({
                "title": event.get("title"),
                "source_url": event.get("source_url"),
                "description_sample": str(desc)[:100],
                "reason": "no fee keyword found"
            })
            
    # 判斷是否需要報名
    exhibition_terms = ("展覽", "展期", "開放參觀", "常設展", "特展", "展出", "展示")
    registration_positive_terms = (
        "立即報名", "線上報名", "報名網址", "報名期間", "報名表單",
        "名額限制", "額滿", "報名連結",
    )
    is_exhibition = any(term in desc for term in exhibition_terms)
    has_registration_action = any(term in desc for term in registration_positive_terms)
    has_registration_url = bool(event.get("registration_url"))

    if has_registration_action or (has_registration_url and not is_exhibition):
        event["registration_required"] = True
    elif is_exhibition and not has_registration_action:
        event["registration_required"] = False
    else:
        event["registration_required"] = None  # unknown

    return event


def extract_registration_url(text, existing_url=None):
    if existing_url:
        evidence = registration_evidence(text or "", existing_url)
        if evidence:
            return existing_url, evidence
    for match in REGISTRATION_URL_RE.finditer(text or ""):
        url = match.group(0).rstrip("，。；;、")
        evidence = registration_evidence(text[max(0, match.start() - 40): match.end() + 40], url)
        if evidence:
            return url, evidence
    return None, ""


def registration_evidence(text, url):
    if is_common_registration_page(url):
        return ""
    host = urlparse(url or "").netloc.lower()
    if any(hint in host for hint in REGISTRATION_HOST_HINTS):
        if "accupass.com" in host:
            return "Accupass"
        return "Google 表單"
    return first_keyword(text, REGISTRATION_TEXT_HINTS)


def is_common_registration_page(url):
    return any(hint.lower() in (url or "").lower() for hint in COMMON_REGISTRATION_PAGE_HINTS)


def first_keyword(text, keywords):
    for keyword in keywords:
        if keyword in (text or ""):
            return keyword
    return ""


def fee_amount_evidence(text):
    match = PAID_AMOUNT_RE.search(text or "")
    return match.group(0).strip() if match else ""

def per_person_evidence(text):
    match = PAID_PER_PERSON_RE.search(text or "")
    return match.group(0).strip() if match else ""


def has_fee_amount_near_paid_context(text):
    amount_re = re.compile(r'(?:NT\$|新臺幣|新台幣|\$)?\s*\d[\d,]*(?:\s*元)?', re.I)
    paid_context = ("票價", "費用", "報名費", "售票", "門票", "購票", "OPENTIX", "opentix", "收費")
    blocked_context = ("罰", "罰鍰", "裁罰", "補助", "預算", "決算", "財報", "違規")
    for match in amount_re.finditer(text or ""):
        context = text[max(0, match.start() - 20): match.end() + 20]
        if any(term in context for term in blocked_context):
            continue
        if any(term in context for term in paid_context):
            return True
    return False
