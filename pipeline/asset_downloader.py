import os
import hashlib
from urllib.parse import urlparse
from PIL import Image
from io import BytesIO
import requests

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TaoyuanPublicEventCrawler/1.0)",
}


def create_asset_session():
    session = requests.Session()
    session.trust_env = False
    session.headers.update(REQUEST_HEADERS)
    return session


def read_image_dimensions(filepath):
    try:
        with Image.open(filepath) as img:
            return img.size
    except Exception:
        return None, None


def read_image_dimensions_from_content(content):
    try:
        with Image.open(BytesIO(content)) as img:
            return img.size
    except Exception:
        return None, None


def download_assets(event, max_assets=8, debug_log=None):
    """
    Downloads assets and records local metadata.
    """
    if not event or not event.get("extracted_assets"):
        return event
        
    assets = event["extracted_assets"][:max_assets]
    
    session = create_asset_session()

    for asset in assets:
        url = asset["url"]
        asset_type = asset["type"]
        ext = os.path.splitext(urlparse(url).path)[1].lower()
        if not ext:
            if asset_type in ["inline_image", "og_image"]:
                ext = ".jpg"
            else:
                ext = ".unknown"
                
        # Hash for filename
        activity_hash = (event.get("content_hash") or "nohash")[:8]
        asset_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:8]
        
        folder = "unknown"
        if asset_type in ["inline_image", "og_image"]:
            folder = "images"
        elif ext == ".pdf":
            folder = "pdf"
        elif ext in [".doc", ".docx", ".xls", ".xlsx"]:
            folder = "documents"
            
        filename = f"{event.get('source_key')}_{activity_hash}_{asset_hash}{ext}"
        filepath = os.path.join("scraping", "data", "assets", folder, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Download
        status = "failed"
        width = None
        height = None
        
        if not os.path.exists(filepath):
            try:
                resp = session.get(url, timeout=10, stream=True)
                if resp.status_code == 200:
                    content = resp.content
                    
                    # If image, check size
                    if folder == "images":
                        width, height = read_image_dimensions_from_content(content)
                        if width and height:
                            if width < 200 or height < 120:
                                status = "filtered"
                                if debug_log is not None:
                                    debug_log.append({
                                        "title": event.get("title"),
                                        "source_url": event.get("source_url"),
                                        "asset_url": url,
                                        "reason": f"too_small: {width}x{height}"
                                    })
                            else:
                                with open(filepath, "wb") as f:
                                    f.write(content)
                                status = "downloaded"
                        else:
                            status = "failed"
                    else:
                        with open(filepath, "wb") as f:
                            f.write(content)
                        status = "downloaded"
                else:
                    status = "failed"
            except Exception as e:
                status = "failed"
                if debug_log is not None:
                    debug_log.append({
                        "title": event.get("title"),
                        "source_url": event.get("source_url"),
                        "asset_url": url,
                        "reason": str(e)
                    })
        else:
            status = "downloaded" # Already downloaded
            if folder == "images":
                width, height = read_image_dimensions(filepath)
                if not width or not height:
                    status = "failed"
                    if debug_log is not None:
                        debug_log.append({
                            "title": event.get("title"),
                            "source_url": event.get("source_url"),
                            "asset_url": url,
                            "reason": "existing_image_unreadable"
                        })
            
        asset.update({
            "source_name": event.get("source_name"),
            "source_url": event.get("source_url"),
            "asset_url": url,
            "local_path": filepath if status == "downloaded" else None,
            "asset_type": asset_type,
            "type": asset_type,
            "file_ext": ext,
            "ext": ext,
            "width": width,
            "height": height,
            "is_primary_poster": False,
            "download_status": status,
            "status": status,
            "alt_text": asset.get("alt"),
            "link_text": asset.get("link_text") or asset.get("alt"),
            "image_quality_warnings": asset.get("image_quality_warnings") or [],
        })
        
    event["extracted_assets"] = assets
    return event
