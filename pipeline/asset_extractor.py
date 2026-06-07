import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def is_valid_asset_url(url):
    if not url or url.startswith('data:'): return False
    lower_url = url.lower()
    invalid_keywords = [
        "logo", "icon", "facebook", "line", "twitter", "share", "print", "home",
        "search", "menu", "banner_tiny", "spacer", "loading", "captcha",
        "egov", "aplusaa", "a11y", "qrcode", "favicon", "apple-touch-icon",
        "android-chrome", "m_0.png", "m_1.png"
    ]
    for kw in invalid_keywords:
        if kw in lower_url:
            return False
    tiny_size_markers = ["72x72", "64x64", "48x48", "32x32", "24x24", "16x16"]
    if any(marker in lower_url for marker in tiny_size_markers):
        return False
    return True

def asset_priority(asset):
    text = f"{asset.get('url', '')} {asset.get('alt', '')}".lower()
    score = 0
    if "relpic" in text or "articles-image" in text:
        score += 100
    if any(size in text for size in ["710x470", "700x400", "1024x768", "1080x1920", "1200x630"]):
        score += 50
    if any(kw in text for kw in ["海報", "活動", "dm", "poster", "主視覺", "宣傳"]):
        score += 30
    if asset.get("type") == "og_image":
        score += 20
    if asset.get("type") == "attachment":
        score -= 20
    return -score

def extract_assets(event):
    """
    Extracts asset URLs from the saved raw HTML.
    """
    if not event: return event
    
    raw_html_path = event.get("raw_html_path")
    if not raw_html_path or not os.path.exists(raw_html_path):
        return event
        
    with open(raw_html_path, "r", encoding="utf-8") as f:
        html = f.read()
        
    soup = BeautifulSoup(html, "html.parser")
    base_url = event.get("source_url", "")
    
    assets = []
    
    # 1. Open Graph Image
    og_image = soup.find("meta", property="og:image")
    if og_image and is_valid_asset_url(og_image.get("content")):
        assets.append({
            "url": urljoin(base_url, og_image.get("content")),
            "type": "og_image",
            "alt": None
        })
        
    # 2. Inline Images
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        if is_valid_asset_url(src):
            assets.append({
                "url": urljoin(base_url, src),
                "type": "inline_image",
                "alt": img.get("alt") or img.get("title"),
                "width_hint": img.get("width"),
                "height_hint": img.get("height")
            })
            
    # 3. Attachments (PDFs, docs)
    valid_exts = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".zip"]
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href: continue
        
        lower_href = href.lower()
        if any(lower_href.endswith(ext) for ext in valid_exts):
            assets.append({
                "url": urljoin(base_url, href),
                "type": "attachment",
                "alt": a.text.strip() or a.get("title")
            })
            
    # Deduplicate assets by URL
    unique_assets = {}
    for a in assets:
        url = a["url"]
        if url not in unique_assets:
            unique_assets[url] = a
            
    event["extracted_assets"] = sorted(unique_assets.values(), key=asset_priority)
    if event["extracted_assets"]:
        event["has_assets"] = True
        event["asset_count"] = len(event["extracted_assets"])
        
    return event
