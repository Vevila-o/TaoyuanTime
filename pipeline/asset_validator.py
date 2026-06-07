IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods"}

BLOCKED_IMAGE_KEYWORDS = (
    "qrcode",
    "qr-code",
    "qr_code",
    "qr",
    "icon",
    "logo",
    "facebook",
    "line",
    "share",
    "print",
    "captcha",
    "banner-print",
)
POSITIVE_IMAGE_KEYWORDS = ("海報", "活動", "dm", "poster", "宣傳", "主視覺", "電子檔", "相關圖片")


def _combined_asset_text(asset):
    values = [
        asset.get("url"),
        asset.get("asset_url"),
        asset.get("alt_text"),
        asset.get("alt"),
        asset.get("link_text"),
        asset.get("title_text"),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _has_positive_keyword(asset):
    text = _combined_asset_text(asset)
    return any(keyword.lower() in text for keyword in POSITIVE_IMAGE_KEYWORDS)


def _has_blocked_keyword(asset):
    text = _combined_asset_text(asset)
    return any(keyword in text for keyword in BLOCKED_IMAGE_KEYWORDS)


def _compact_text(value):
    return "".join(str(value or "").lower().split())


def _matches_event_title(asset, event_title):
    title = _compact_text(event_title)
    text = _compact_text(_combined_asset_text(asset))
    if len(title) < 8 or len(text) < 8:
        return False
    return title[:12] in text or text[:12] in title


def classify_image_role(asset, event_title=""):
    warnings = []
    ext = (asset.get("ext") or asset.get("file_ext") or "").lower()
    status = asset.get("status") or asset.get("download_status")
    width = int(asset.get("width") or 0)
    height = int(asset.get("height") or 0)

    if status and status != "downloaded":
        return "failed", 0, ["asset_not_downloaded"]
    if ext in DOCUMENT_EXTENSIONS:
        return "document", 0, []
    if ext not in IMAGE_EXTENSIONS:
        return "decorative", 0, ["unsupported_asset_type"]
    if not width or not height:
        return "decorative", 0, ["missing_image_dimensions"]

    ratio = width / height if height else 0
    area_score = (width * height) / 10000
    positive = _has_positive_keyword(asset) or _matches_event_title(asset, event_title)
    blocked = _has_blocked_keyword(asset)
    is_small = width < 300 or height < 200
    is_small_square = 0.85 <= ratio <= 1.15 and max(width, height) <= 360

    if blocked or is_small_square:
        if blocked:
            warnings.append("blocked_image_keyword")
        if is_small_square:
            warnings.append("small_square_image")
        return "qr_or_icon", int(area_score), warnings

    if is_small:
        return "decorative", int(area_score), ["image_too_small"]

    score = area_score
    if positive:
        score += 80
    if ratio < 0.85 and height >= 350:
        score += 40
    if 1.2 <= ratio <= 2.6 and width >= 600 and height >= 300:
        score += 35

    if positive and ((ratio < 0.9 and height >= 350) or (width >= 600 and height >= 300)):
        return "poster", int(score), warnings
    if positive and width >= 600 and height >= 300:
        return "main_visual", int(score), warnings
    if width >= 300 and height >= 400 and positive:
        return "poster", int(score), warnings
    if width >= 500 and height >= 300:
        return "activity_photo", int(score), ["not_primary_visual"]
    return "decorative", int(score), ["weak_visual_candidate"]


def _candidate_sort_key(asset):
    role = asset.get("image_role")
    role_score = {"poster": 1000, "main_visual": 700}.get(role, 0)
    text = _combined_asset_text(asset)
    penalty = 0
    if "relpic/-1/1" in text:
        penalty -= 80
    if not (asset.get("alt_text") or asset.get("alt") or asset.get("link_text")):
        penalty -= 40
    return role_score + int(asset.get("poster_score") or 0) + penalty


def validate_assets(event):
    if not event:
        return event

    event["poster_url"] = None
    event["poster_local_path"] = None
    event["use_default_image"] = True

    assets = event.get("extracted_assets") or []
    if not assets:
        event["ocr_status"] = event.get("ocr_status") or "skipped_no_image"
        event["ocr_ready"] = bool(event.get("ocr_ready"))
        return event

    candidates = []
    for asset in assets:
        role, poster_score, warnings = classify_image_role(asset, event.get("title"))
        line_or_ocr_candidate = role in {"poster", "main_visual"} and bool(asset.get("local_path"))
        asset["image_role"] = role
        asset["asset_validation_status"] = "valid_poster" if role in {"poster", "main_visual"} else role
        asset["poster_score"] = poster_score
        asset["line_image_candidate"] = line_or_ocr_candidate
        asset["line_card_candidate"] = False
        asset["ocr_candidate"] = line_or_ocr_candidate
        asset["image_quality_warnings"] = warnings
        asset["is_primary_poster"] = False
        if line_or_ocr_candidate:
            candidates.append(asset)

    if candidates:
        primary = max(candidates, key=_candidate_sort_key)
        primary["line_card_candidate"] = True
        primary["is_primary_poster"] = True
        event["poster_url"] = primary.get("url") or primary.get("asset_url")
        event["poster_local_path"] = primary.get("local_path")
        event["use_default_image"] = False
        event["ocr_image_url"] = event.get("ocr_image_url") or event["poster_url"]
        event["ocr_image_path"] = event.get("ocr_image_path") or event["poster_local_path"]
        if event.get("ocr_status") == "skipped_no_image":
            event.pop("ocr_status", None)
    else:
        warnings = event.setdefault("quality_warnings", [])
        if "no_valid_poster_or_main_visual" not in warnings:
            warnings.append("no_valid_poster_or_main_visual")
        event["ocr_status"] = event.get("ocr_status") or "skipped_no_image"
        event["ocr_ready"] = bool(event.get("ocr_ready"))

    return event
