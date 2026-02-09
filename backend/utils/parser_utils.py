import re
from datetime import date, datetime
import re
from typing import List, Dict, Any, Optional, Tuple

def extract_uuid(url):
    print(url)
    match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', url)
    print(match)
    print(match.group(1) if match else None)
    return match.group(1) if match else None


def parse_date(date_str):
    """Парсит дату из разных форматов в datetime.
    Zooportal часто отдаёт dd.mm.yyyy.
    """
    if not date_str:
        return None

    date_str = str(date_str).strip()
    if not date_str:
        return None

    # Если это уже datetime, возвращаем как есть
    if isinstance(date_str, datetime):
        return date_str

    # Если это date, преобразуем в datetime
    if isinstance(date_str, date):
        return datetime.combine(date_str, datetime.min.time())

    formats = [
        "%d.%m.%Y",  # 08.02.2025
        "%d.%m.%y",  # 08.02.25
        "%d %b %Y",  # 8 Jul 1957
        "%d %B %Y",  # 8 July 1957
        "%d/%m/%Y",  # 05/12/2022
        "%Y-%m-%d",  # 2022-12-05
        "%b %d, %Y",  # Dec 5, 2022
        "%B %d, %Y",  # December 5, 2022
        "%Y%m%d",  # 20221205
        "%m/%d/%Y",  # 12/05/2022
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
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        value = value.strip()
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%d/%m/%Y, %H:%M",
                "%d.%m.%Y %H:%M:%S",
                "%d.%m.%Y",
                "%Y-%m-%d",
                "%d/%m/%Y",
                "%m/%d/%Y",
                "%b %d, %Y",
                "%B %d, %Y",
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        except Exception:
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
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value in ["", " ", "nan", "NaN", "null", "None"]:
            return None
        # Убираем нечисловые символы, кроме точки и минуса
        value = re.sub(r'[^\d\.\-]', '', value)
        if value in ["", "-", "."]:
            return None
    try:
        return float(value) if value else None
    except (ValueError, TypeError):
        return None


def parse_coi(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if value in ["", " ", "nan", "NaN", "null", "None"]:
            return None
        try:
            # Убираем нечисловые символы, кроме точки и минуса
            clean_value = re.sub(r'[^\d\.\-]', '', value)
            if clean_value in ["", "-", "."]:
                return None
            return float(clean_value)
        except (ValueError, TypeError):
            return None
    return None


def to_snake_case(text):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', text).lower()


def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip()


def transliterate_russian_to_english(text: str) -> str:
    """Транслитерация русских букв в английские"""
    translit_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd',
        'е': 'e', 'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i',
        'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
        'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
        'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch',
        'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '',
        'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D',
        'Е': 'E', 'Ё': 'E', 'Ж': 'Zh', 'З': 'Z', 'И': 'I',
        'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N',
        'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T',
        'У': 'U', 'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch',
        'Ш': 'Sh', 'Щ': 'Shch', 'Ъ': '', 'Ы': 'Y', 'Ь': '',
        'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
    }

    result = []
    for char in text:
        if char in translit_map:
            result.append(translit_map[char])
        else:
            result.append(char)
    return ''.join(result)


def transliterate_english_to_russian(text: str) -> str:
    """Транслитерация английских букв в русские (обратная)"""
    translit_map = {
        'a': 'а', 'b': 'б', 'v': 'в', 'g': 'г', 'd': 'д',
        'e': 'е', 'zh': 'ж', 'z': 'з', 'i': 'и', 'y': 'й',
        'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н', 'o': 'о',
        'p': 'п', 'r': 'р', 's': 'с', 't': 'т', 'u': 'у',
        'f': 'ф', 'kh': 'х', 'ts': 'ц', 'ch': 'ч', 'sh': 'ш',
        'shch': 'щ', 'yu': 'ю', 'ya': 'я',
        'A': 'А', 'B': 'Б', 'V': 'В', 'G': 'Г', 'D': 'Д',
        'E': 'Е', 'Zh': 'Ж', 'Z': 'З', 'I': 'И', 'Y': 'Й',
        'K': 'К', 'L': 'Л', 'M': 'М', 'N': 'Н', 'O': 'О',
        'P': 'П', 'R': 'Р', 'S': 'С', 'T': 'Т', 'U': 'У',
        'F': 'Ф', 'Kh': 'Х', 'Ts': 'Ц', 'Ch': 'Ч', 'Sh': 'Ш',
        'Shch': 'Щ', 'Yu': 'Ю', 'Ya': 'Я'
    }

    # Сначала обрабатываем многобуквенные сочетания
    text_lower = text.lower()
    result = []
    i = 0

    while i < len(text):
        found = False
        # Проверяем многобуквенные сочетания
        for length in [4, 3, 2, 1]:
            if i + length <= len(text):
                substr = text_lower[i:i + length]
                if substr in translit_map:
                    # Сохраняем регистр первой буквы
                    if text[i].isupper():
                        result.append(translit_map[substr].capitalize())
                    else:
                        result.append(translit_map[substr])
                    i += length
                    found = True
                    break

        if not found:
            result.append(text[i])
            i += 1

    return ''.join(result)

def normalize_name_case(name: str) -> str:
    """
    Делает первую букву каждого слова заглавной,
    остальные — строчными
    """
    if not name:
        return name
    return ' '.join(word.capitalize() for word in name.split())

def remove_titles(name: str) -> str:
    """
    Убирает выставочные титулы из имени собаки
    """
    if not name:
        return name

    name = re.sub(
        r'\b(CH\.?|INT\.?CH\.?|JCH\.?|GR\.?CH\.?|RUS|RKF|CL|J\.?CH\.?|BIS|BISS|WD|WB|BOB|BOS|BOG|BIG|BIS\d*)\b',
        '',
        name,
        flags=re.IGNORECASE
    )
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def parse_titles_from_html(soup, logger=None):
    """
    Совместимая функция для парсинга титулов из HTML (старый интерфейс).
    """
    titles_data = []

    # Ищем div с классом 'titles'
    titles_div = soup.find('div', class_='titles')
    if not titles_div:
        return titles_data

    # Проверяем, что это не блок с весом/ростом
    div_classes = titles_div.get('class', [])
    if 'subtitle' in div_classes:
        return titles_data

    titles_text = titles_div.get_text(strip=True)
    if not titles_text:
        return titles_data

    if logger:
        logger.info(f"Найден текст титулов: '{titles_text}'")

    # Используем новую универсальную функцию
    titles_data = parse_titles_from_text(titles_text, source="zooportal")

    if logger:
        logger.info(f"Распарсено {len(titles_data)} титулов")

    return titles_data

# -----------
def parse_titles_from_text(text: str, source: str = "zooportal") -> List[Dict[str, Any]]:
    """
    Универсальный парсер титулов из текста.

    Аргументы:
        text: Текст с титулами
        source: Источник данных ("zooportal", "breedarchive", "rkf")

    Возвращает список словарей с информацией о титулах.
    """
    if not text:
        return []

    # Нормализуем текст
    normalized_text = re.sub(r'\s+', ' ', text.strip())

    # Разделяем титулы в зависимости от источника
    if source == "zooportal":
        # Zooportal использует запятые для разделения титулов
        raw_titles = [t.strip() for t in normalized_text.split(',')]
    elif source == "breedarchive":
        # BreedArchive часто использует запятые для разделения
        # Пример: "RU CH, UA CH, AZ CH"
        raw_titles = []

        # Если есть запятые, делим по ним
        if ',' in normalized_text:
            parts = [part.strip() for part in normalized_text.split(',')]
            raw_titles.extend(parts)
        else:
            # Если нет запятых, обрабатываем как единый титул
            raw_titles.append(normalized_text)
    else:
        # Для других источников используем запятые
        raw_titles = [t.strip() for t in normalized_text.split(',') if t.strip()]

    titles_data = []

    for raw_title in raw_titles:
        if not raw_title:
            continue

        # Для BreedArchive: специальная обработка форматов "RU CH", "UA CH" и т.д.
        if source == "breedarchive":
            title_info = parse_breedarchive_title(raw_title)
        else:
            # Для Zooportal и других источников
            title_info = parse_zooportal_title(raw_title)

        if title_info:
            titles_data.append(title_info)

    return titles_data

def parse_breedarchive_title(raw_title: str) -> Optional[Dict[str, Any]]:
    """
    Специальный парсер титулов для BreedArchive.
    Обрабатывает форматы: "RU CH", "UA CH", "TH CH", "RU JCH", "CA CH", "RU Club CH" и т.д.
    """
    if not raw_title:
        return None

    # Обработка формата "Club CH" (без указания страны)
    if raw_title.upper() == "CLUB CH" or raw_title.upper() == "CLUB.CH":
        return {
            'short_name': "CH.CL",
            'long_name': "Чемпион Национального клуба породы",
            'country': None,
            'raw_text': raw_title,
            'is_prefix': True,
            'has_winner_year': False,
            'winner_year': None
        }

    # Разделяем на слова
    words = raw_title.split()

    # Обработка формата "RU Club CH"
    if len(words) >= 3:
        first_word = words[0].upper()
        second_word = words[1].upper()
        third_word = words[2].upper() if len(words) > 2 else ""

        country_codes = {
            'RU': 'RUS', 'RUS': 'RUS', 'RF': 'RUS',
            'UA': 'UA', 'UKR': 'UA',
            'BY': 'BY', 'BLR': 'BY',
            'KZ': 'KZ', 'KAZ': 'KZ',
            'AZ': 'AZ', 'AZE': 'AZ',
            'CY': 'CY', 'CYP': 'CY',
            'ME': 'ME', 'MNE': 'ME',
            'MD': 'MD', 'MDA': 'MD',
            'GE': 'GE', 'GEO': 'GE',
            'AM': 'AM', 'ARM': 'AM',
            'PL': 'PL', 'POL': 'PL',
            'CZ': 'CZ', 'CZE': 'CZ',
            'SK': 'SK', 'SVK': 'SK',
            'LV': 'LV', 'LVA': 'LV',
            'LT': 'LT', 'LTU': 'LT',
            'EE': 'EE', 'EST': 'EE',
            'FI': 'FIN', 'FIN': 'FIN',
            'SE': 'SWE', 'SWE': 'SWE',
            'NO': 'NOR', 'NOR': 'NOR',
            'DK': 'DNK', 'DNK': 'DNK',
            'DE': 'DEU', 'DEU': 'DEU', 'GER': 'DEU',
            'FR': 'FRA', 'FRA': 'FRA',
            'IT': 'ITA', 'ITA': 'ITA',
            'ES': 'ESP', 'ESP': 'ESP',
            'PT': 'PRT', 'PRT': 'PRT',
            'NL': 'NLD', 'NLD': 'NLD',
            'BE': 'BEL', 'BEL': 'BEL',
            'CH': 'CHE', 'CHE': 'CHE', 'SWI': 'CHE',
            'AT': 'AUT', 'AUT': 'AUT',
            'HU': 'HUN', 'HUN': 'HUN',
            'RO': 'ROU', 'ROU': 'ROU',
            'BG': 'BGR', 'BGR': 'BGR',
            'GR': 'GRC', 'GRC': 'GRC',
            'TR': 'TUR', 'TUR': 'TUR',
            'IL': 'ISR', 'ISR': 'ISR',
            'US': 'USA', 'USA': 'USA',
            'CA': 'CAN', 'CAN': 'CAN',
            'AU': 'AUS', 'AUS': 'AUS',
            'NZ': 'NZL', 'NZL': 'NZL',
            'JP': 'JPN', 'JPN': 'JPN',
            'KR': 'KOR', 'KOR': 'KOR',
            'CN': 'CHN', 'CHN': 'CHN',
            'IN': 'IND', 'IND': 'IND',
            'BR': 'BRA', 'BRA': 'BRA',
            'AR': 'ARG', 'ARG': 'ARG',
            'MX': 'MEX', 'MEX': 'MEX',
            'ZA': 'ZAF', 'ZAF': 'ZAF',
        }

        if first_word in country_codes and second_word == "CLUB" and third_word == "CH":
            country_code = country_codes[first_word]
            country_display = get_country_display_name(country_code)

            return {
                'short_name': "CH.CL",
                'long_name': f"Чемпион Национального клуба породы {country_display}",
                'country': country_code,
                'raw_text': raw_title,
                'is_prefix': True,
                'has_winner_year': False,
                'winner_year': None
            }

    # Обработка формата "CA CH" (Канадский Чемпион)
    if len(words) >= 2:
        first_word = words[0].upper()
        second_word = words[1].upper()

        if first_word == "CA" and second_word == "CH":
            return {
                'short_name': "CA CH",
                'long_name': "Канадский Чемпион",
                'country': "CAN",
                'raw_text': raw_title,
                'is_prefix': True,
                'has_winner_year': False,
                'winner_year': None
            }

        # Обработка других форматов с кодом страны
        country_codes = {
            'RU': 'RUS', 'RUS': 'RUS', 'RF': 'RUS',
            'UA': 'UA', 'UKR': 'UA',
            'BY': 'BY', 'BLR': 'BY',
            'KZ': 'KZ', 'KAZ': 'KZ',
            'AZ': 'AZ', 'AZE': 'AZ',
            'CY': 'CY', 'CYP': 'CY',
            'ME': 'ME', 'MNE': 'ME',
            'MD': 'MD', 'MDA': 'MD',
            'GE': 'GE', 'GEO': 'GE',
            'AM': 'AM', 'ARM': 'AM',
            'PL': 'PL', 'POL': 'PL',
            'CZ': 'CZ', 'CZE': 'CZ',
            'SK': 'SK', 'SVK': 'SK',
            'LV': 'LV', 'LVA': 'LV',
            'LT': 'LT', 'LTU': 'LT',
            'EE': 'EE', 'EST': 'EE',
            'FI': 'FIN', 'FIN': 'FIN',
            'SE': 'SWE', 'SWE': 'SWE',
            'NO': 'NOR', 'NOR': 'NOR',
            'DK': 'DNK', 'DNK': 'DNK',
            'DE': 'DEU', 'DEU': 'DEU', 'GER': 'DEU',
            'FR': 'FRA', 'FRA': 'FRA',
            'IT': 'ITA', 'ITA': 'ITA',
            'ES': 'ESP', 'ESP': 'ESP',
            'PT': 'PRT', 'PRT': 'PRT',
            'NL': 'NLD', 'NLD': 'NLD',
            'BE': 'BEL', 'BEL': 'BEL',
            'CH': 'CHE', 'CHE': 'CHE', 'SWI': 'CHE',
            'AT': 'AUT', 'AUT': 'AUT',
            'HU': 'HUN', 'HUN': 'HUN',
            'RO': 'ROU', 'ROU': 'ROU',
            'BG': 'BGR', 'BGR': 'BGR',
            'GR': 'GRC', 'GRC': 'GRC',
            'TR': 'TUR', 'TUR': 'TUR',
            'IL': 'ISR', 'ISR': 'ISR',
            'US': 'USA', 'USA': 'USA',
            'CA': 'CAN', 'CAN': 'CAN',
            'AU': 'AUS', 'AUS': 'AUS',
            'NZ': 'NZL', 'NZL': 'NZL',
            'JP': 'JPN', 'JPN': 'JPN',
            'KR': 'KOR', 'KOR': 'KOR',
            'CN': 'CHN', 'CHN': 'CHN',
            'IN': 'IND', 'IND': 'IND',
            'BR': 'BRA', 'BRA': 'BRA',
            'AR': 'ARG', 'ARG': 'ARG',
            'MX': 'MEX', 'MEX': 'MEX',
            'ZA': 'ZAF', 'ZAF': 'ZAF',
        }

        if first_word in country_codes:
            country_code = country_codes[first_word]
            title_type = second_word

            # Определяем short_name, long_name и is_prefix
            if title_type == "CH":
                short_name = "CH"
                country_display = get_country_display_name(country_code)
                long_name = f"Чемпион {country_display}"
                is_prefix = True

            elif title_type in ["JCH", "J.CH"]:
                short_name = "JCH"
                country_display = get_country_display_name(country_code)
                long_name = f"Юниор Чемпион {country_display}"
                is_prefix = True

            elif title_type in ["GRCH", "GR.CH"]:
                short_name = "GrCH"
                country_display = get_country_display_name(country_code)
                long_name = f"Гранд Чемпион {country_display}"
                is_prefix = True

            elif title_type in ["VCH", "V.CH"]:
                short_name = "VCH"
                country_display = get_country_display_name(country_code)
                long_name = f"Ветеран Чемпион {country_display}"
                is_prefix = True

            elif title_type in ["TCH", "THCH", "TH.CH"]:
                short_name = "TCH"
                long_name = "Трехкратный Чемпион"
                is_prefix = True
                country_code = None

            else:
                # Неизвестный тип титула - используем общий парсер
                return parse_zooportal_title(raw_title)

            # Проверяем, есть ли год в титуле
            winner_year = None
            has_winner_year = False
            year_match = re.search(r'\b(19|20)\d{2}\b', raw_title)
            if year_match:
                winner_year = int(year_match.group())
                has_winner_year = True

            return {
                'short_name': short_name,
                'long_name': long_name,
                'country': country_code,
                'raw_text': raw_title,
                'is_prefix': is_prefix,
                'has_winner_year': has_winner_year,
                'winner_year': winner_year
            }

    # Если не попали ни в один из форматов, используем общий парсер
    return parse_zooportal_title(raw_title)

def parse_zooportal_title(raw_title: str) -> Optional[Dict[str, Any]]:
    """
    Парсер титулов для Zooportal и других источников.
    Обрабатывает форматы: "GrCH.RUS", "CH.RUS", "Чемпион России" и т.д.
    """
    if not raw_title:
        return None

    # Извлекаем код страны
    country = extract_country_code(raw_title)

    # Приводим к нижнему регистру для сравнения
    title_lower = raw_title.lower()

    # Инициализируем значения по умолчанию
    short_name = raw_title
    long_name = raw_title
    is_prefix = True

    # Словарь соответствий титулов для Zooportal
    title_patterns = {
        # Гранд Чемпион
        'grch': ("GrCH", "Гранд Чемпион", True),
        'гранд чемпион': ("GrCH", "Гранд Чемпион", True),
        'grand champion': ("GrCH", "Гранд Чемпион", True),

        # Чемпион Национального клуба породы
        'ch.cl': ("CH.CL", "Чемпион Национального клуба породы", True),
        'нкп': ("CH.CL", "Чемпион Национального клуба породы", True),
        'ch club': ("CH.CL", "Чемпион Национального клуба породы", True),

        # Юниор Чемпион
        'jch': ("JCH", "Юниор Чемпион", True),
        'юниор': ("JCH", "Юниор Чемпион", True),
        'junior champion': ("JCH", "Юниор Чемпион", True),

        # Ветеран Чемпион
        'vch': ("VCH", "Ветеран Чемпион", True),
        'ветеран': ("VCH", "Ветеран Чемпион", True),
        'veteran champion': ("VCH", "Ветеран Чемпион", True),

        # Интернациональный Чемпион
        'int': ("INT", "Интернациональный Чемпион", True),
        'интер': ("INT", "Интернациональный Чемпион", True),
        'international': ("INT", "Интернациональный Чемпион", True),

        # Европейский Чемпион
        'eu': ("EU", "Европейский Чемпион", True),
        'европ': ("EU", "Европейский Чемпион", True),
        'european': ("EU", "Европейский Чемпион", True),

        # Чемпион Мира
        'world': ("WORLD", "Чемпион Мира", True),
        'мир': ("WORLD", "Чемпион Мира", True),
        'world champion': ("WORLD", "Чемпион Мира", True),

        # Чемпион породы
        'bch': ("BCH", "Чемпион породы", True),
        'breed champion': ("BCH", "Чемпион породы", True),

        # Чемпион (общий) - проверяем последним
        'ch': ("CH", "Чемпион", True),
        'чемпион': ("CH", "Чемпион", True),
        'champion': ("CH", "Чемпион", True),

        # Сертификаты
        'cacib': ("CACIB", "Сертификат международной выставки", False),
        'cac': ("CAC", "Сертификат соответствия породе", False),

        # Клубные титулы
        'чк': ("ЧК", "Чемпион клуба", False),
        'кчк': ("КЧК", "Кандидат в чемпионы клуба", False),

        # Лучшие представители
        'лп': ("ЛП", "Лучший представитель породы", False),
        'лс': ("ЛС", "Лучший щенок", False),
    }

    # Ищем совпадения
    for pattern, (short, long, prefix) in title_patterns.items():
        if pattern in title_lower:
            # Проверяем, что это не часть более длинного слова
            if pattern == 'ch':
                # "ch" может быть частью других титулов
                if any(x in title_lower for x in ['grch', 'jch', 'vch', 'bch', 'ich', 'ch.cl']):
                    continue

            short_name = short
            long_name = long

            # Если есть страна в титуле, добавляем ее к long_name
            if country and country != short and 'чемпион' in long.lower():
                country_display = get_country_display_name(country)
                long_name = f"{long} {country_display}"

            is_prefix = prefix
            break

    # Проверяем, есть ли год в титуле
    winner_year = None
    has_winner_year = False
    year_match = re.search(r'\b(19|20)\d{2}\b', raw_title)
    if year_match:
        winner_year = int(year_match.group())
        has_winner_year = True

    return {
        'short_name': short_name,
        'long_name': long_name,
        'country': country,
        'raw_text': raw_title,
        'is_prefix': is_prefix,
        'has_winner_year': has_winner_year,
        'winner_year': winner_year
    }


def get_country_display_name(country_code: str) -> str:
    """
    Преобразует код страны в читаемое название на русском.
    """
    country_map = {
        # Основные
        'RUS': 'России',
        'RU': 'России',
        'РФ': 'России',

        # РКФ
        'RKF': 'РКФ',

        # СНГ
        'BY': 'Беларуси',
        'BLR': 'Беларуси',
        'UA': 'Украины',
        'UKR': 'Украины',
        'KZ': 'Казахстана',
        'KAZ': 'Казахстана',
        'AZ': 'Азербайджана',
        'AZE': 'Азербайджана',

        # Европа
        'CY': 'Кипра',
        'CYP': 'Кипра',
        'ME': 'Черногории',
        'MNE': 'Черногории',
        'MD': 'Молдовы',
        'MDA': 'Молдовы',
        'GE': 'Грузии',
        'GEO': 'Грузии',
        'AM': 'Армении',
        'ARM': 'Армении',
        'PL': 'Польши',
        'POL': 'Польши',
        'CZ': 'Чехии',
        'CZE': 'Чехии',
        'SK': 'Словакии',
        'SVK': 'Словакии',
        'LV': 'Латвии',
        'LVA': 'Латвии',
        'LT': 'Литвы',
        'LTU': 'Литвы',
        'EE': 'Эстонии',
        'EST': 'Эстонии',
        'FI': 'Финляндии',
        'FIN': 'Финляндии',
        'SE': 'Швеции',
        'SWE': 'Швеции',
        'NO': 'Норвегии',
        'NOR': 'Норвегии',
        'DK': 'Дании',
        'DNK': 'Дании',
        'DE': 'Германии',
        'DEU': 'Германии',
        'FR': 'Франции',
        'FRA': 'Франции',
        'IT': 'Италии',
        'ITA': 'Италии',
        'ES': 'Испании',
        'ESP': 'Испании',
        'PT': 'Португалии',
        'PRT': 'Португалии',
        'NL': 'Нидерландов',
        'NLD': 'Нидерландов',
        'BE': 'Бельгии',
        'BEL': 'Бельгии',
        'CH': 'Швейцарии',
        'CHE': 'Швейцарии',
        'AT': 'Австрии',
        'AUT': 'Австрии',
        'HU': 'Венгрии',
        'HUN': 'Венгрии',
        'RO': 'Румынии',
        'ROU': 'Румынии',
        'BG': 'Болгарии',
        'BGR': 'Болгарии',
        'GR': 'Греции',
        'GRC': 'Греции',
        'TR': 'Турции',
        'TUR': 'Турции',

        # Америка
        'US': 'США',
        'USA': 'США',
        'CA': 'Канады',
        'CAN': 'Канады',
        'MX': 'Мексики',
        'MEX': 'Мексики',
        'BR': 'Бразилии',
        'BRA': 'Бразилии',
        'AR': 'Аргентины',
        'ARG': 'Аргентины',

        # Азия
        'IL': 'Израиля',
        'ISR': 'Израиля',
        'JP': 'Японии',
        'JPN': 'Японии',
        'KR': 'Кореи',
        'KOR': 'Кореи',
        'CN': 'Китая',
        'CHN': 'Китая',
        'IN': 'Индии',
        'IND': 'Индии',

        # Океания
        'AU': 'Австралии',
        'AUS': 'Австралии',
        'NZ': 'Новой Зеландии',
        'NZL': 'Новой Зеландии',

        # Африка
        'ZA': 'ЮАР',
        'ZAF': 'ЮАР',
    }

    return country_map.get(country_code.upper(), country_code)

def extract_country_code(raw_title: str) -> Optional[str]:
    """
    Извлекает код страны из текста титула.
    """
    title_upper = raw_title.upper()

    # 1. Ищем код страны после точки: GrCH.RUS, CH.RUS
    match = re.search(r'\.([A-Z]{2,4})\b', title_upper)
    if match:
        country = match.group(1)
        # Проверяем, что это действительно код страны, а не часть титула
        if country not in ['CH', 'CL', 'CAC', 'CACIB', 'INT', 'EU', 'WORLD']:
            return country

    # 2. Ищем код страны после пробела: CH.CL RUS, CH CL RUS
    match = re.search(r'\s([A-Z]{2,4})\b', title_upper)
    if match:
        country = match.group(1)
        if country not in ['CH', 'CL', 'CAC', 'CACIB']:
            return country

    # 3. Ищем русские названия стран
    if 'РОССИИ' in title_upper or 'RUS' in title_upper or 'РФ' in title_upper:
        return "RUS"
    elif 'РКФ' in title_upper or 'RKF' in title_upper:
        return "RKF"
    elif 'БЕЛАРУСИ' in title_upper or 'BY' in title_upper or 'БЕЛ' in title_upper:
        return "BY"
    elif 'УКРАИНЫ' in title_upper or 'UA' in title_upper or 'УКР' in title_upper:
        return "UA"
    elif 'КАЗАХСТАНА' in title_upper or 'KZ' in title_upper or 'КАЗ' in title_upper:
        return "KZ"
    elif 'АЗЕРБАЙДЖАНА' in title_upper or 'AZ' in title_upper:
        return "AZ"
    elif 'КИПРА' in title_upper or 'CY' in title_upper:
        return "CY"
    elif 'ЧЕРНОГОРИИ' in title_upper or 'ME' in title_upper:
        return "ME"

    # 4. Ищем в скобках
    match = re.search(r'\(([A-Z]{2,4})\)', title_upper)
    if match:
        return match.group(1)

    return None
