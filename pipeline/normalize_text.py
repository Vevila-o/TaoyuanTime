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
        
    return event
