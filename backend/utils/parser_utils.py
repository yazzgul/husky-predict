import re
from datetime import date, datetime
from typing import Optional, Dict, Any

def extract_uuid(url):
    print(url)
    match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', url)
    print(match)
    print(match.group(1) if match else None)
    return match.group(1) if match else None

def parse_date(date_str):
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    formats = [
        "%d %b %Y",  # 5 Dec 2022
        "%d/%m/%Y",   # 05/12/2022
        "%Y-%m-%d",   # ISO 8601 (2022-12-05)
        "%b %d, %Y",  # Dec 5, 2022
        "%B %d, %Y"   # December 5, 2022
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None

def parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        # Преобразуем date в datetime
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            try:
                return datetime.strptime(value, "%m/%d/%Y, %H:%M")
            except ValueError:
                return None
    return None

def get_photo_url(raw: Dict) -> Optional[str]:
    path = raw.get("primary_photo_path")
    if path:
        return f"https://siberianhusky.breedarchive.com/resource/{path}"
    return None

def parse_int(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    return None

def parse_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value not in [None, "", " "] else None
    except (ValueError, TypeError):
        return None
    
def parse_coi(value: Any) -> Optional[float]:
    if isinstance(value, (float, int)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    return None
    
def to_snake_case(text):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', text).lower()

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip()
