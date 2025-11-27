from bs4 import BeautifulSoup
from typing import Optional

class HTMLParser:
    @staticmethod
    def safe_find(soup, *args, **kwargs) -> Optional[BeautifulSoup]:
        try:
            return soup.find(*args, **kwargs)
        except:
            return None

    @staticmethod
    def get_text(element, default="") -> str:
        return element.get_text(strip=True) if element else default

    @staticmethod
    def parse_table(table, headers: list) -> list[dict]:
        if not table:
            return []
        
        rows = table.find_all('tr')[1:]
        results = []
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) != len(headers):
                continue
                
            item = {
                headers[i]: HTMLParser.get_text(cell) 
                for i, cell in enumerate(cells)
            }
            results.append(item)
            
        return results