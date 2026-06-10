import re

TAIL_NOISE_MARKERS = (
    "回上一頁",
    "回最上面",
    "相關圖片",
    "相關連結",
    "上版日期",
    "下版日期",
)
MIN_TAIL_PREFIX_LENGTH = 80


def truncate_tail_noise(text):
    cut_points = []
    for marker in TAIL_NOISE_MARKERS:
        index = text.find(marker)
        if index >= MIN_TAIL_PREFIX_LENGTH:
            cut_points.append(index)
    if not cut_points:
        return text
    return text[:min(cut_points)].strip()


def build_enriched_text(event):
    """
    將 HTML metadata 合併到 event 中，供後續 pipeline 使用。
    產生 enriched_text 欄位：包含 title + metadata + clean_description。
    """
    metadata = event.get("html_metadata") or {}
    parts = []

    # Page title
    if metadata.get("page_title"):
        parts.append(f"頁面標題：{metadata['page_title']}")

    # Meta description
    if metadata.get("meta_description"):
        parts.append(f"頁面描述：{metadata['meta_description']}")

    # OG description（如果和 meta_description 不同）
    og_desc = metadata.get("og_description") or ""
    meta_desc = metadata.get("meta_description") or ""
    if og_desc and og_desc != meta_desc:
        parts.append(f"社群描述：{og_desc}")

    # Structured data 中的關鍵欄位
    for sd in metadata.get("structured_data") or []:
        sd_type = sd.get("@type", "")
        if sd_type in ("Event", "ExhibitionEvent", "Festival", "MusicEvent"):
            if sd.get("name"):
                parts.append(f"結構化資料名稱：{sd['name']}")
            if sd.get("startDate"):
                parts.append(f"結構化資料開始日期：{sd['startDate']}")
            if sd.get("endDate"):
                parts.append(f"結構化資料結束日期：{sd['endDate']}")
            if sd.get("location"):
                loc = sd["location"]
                if isinstance(loc, dict):
                    loc_name = loc.get("name") or loc.get("address", "")
                    parts.append(f"結構化資料地點：{loc_name}")
                else:
                    parts.append(f"結構化資料地點：{loc}")
            if sd.get("offers"):
                offers = sd["offers"]
                if isinstance(offers, dict):
                    price = offers.get("price", "")
                    if price:
                        parts.append(f"結構化資料費用：{price}")

    # Meta keywords
    if metadata.get("meta_keywords"):
        parts.append(f"關鍵字：{metadata['meta_keywords']}")

    enriched = " ".join(parts)
    event["enriched_metadata_text"] = enriched

    return event


def normalize_text(event):
    """
    Cleans up description and title.
    """
    if not event: return event
    
    desc = event.get("description", "")
    if desc:
        # Basic cleanup
        clean_desc = re.sub(r'\s+', ' ', desc).strip()
        clean_desc = truncate_tail_noise(clean_desc)
        
        # Remove common website navigation noise
        noise_patterns = [
            r':::', r'請按\[Enter\].*?按\[Tab\]', r'首頁', r'訊息公告', r'最新消息',
            r'熱門活動', r'跳過此子選單列', r'網頁功能', r'列印內容',
            r'document\.addEventListener.*?\}', r'\$\([^)]*\).*?;', r'\); \}\);',
            r'另開新視窗', r'\[另開新視窗\]', r'分享 Facebook Plurk Twitter Line Email',
            r'回上一頁', r'回首頁', r'網站導覽', r'RSS訂閱', r'字級：', r'回最上面',
            r'p,\s*li\s*\{[^}]+\}', r'hr\s*\{[^}]+\}', r'li\.[^{]+\{[^}]+\}',
            r'定位點 跳到主要內容區塊.*?桃園觀光導覽網'
        ]
        for pattern in noise_patterns:
            clean_desc = re.sub(pattern, ' ', clean_desc, flags=re.I)
            
        clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
        event["clean_description"] = clean_desc
    else:
        event["clean_description"] = ""
        
    event = build_enriched_text(event)
    return event
