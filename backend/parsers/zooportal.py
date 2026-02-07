import asyncio
import re
import hashlib
import logging
from typing import Dict, List, Optional, Tuple, Any
from bs4 import BeautifulSoup

from playwright.async_api import async_playwright
from core.parsersConfig import ZOOPORTAL_BASE_URL, ZOOPORTAL_DOG_PATH, ZOOPORTAL_COOKIES
from utils.parser_utils import parse_date, transliterate_russian_to_english, parse_titles_from_html

logger = logging.getLogger(__name__)

MAIN_ZOOPORTAL_URL = "https://zooportal.pro"
def prepare_zooportal_cookies():
    """Преобразует куки в формат для Playwright"""
    cookies_list = []
    for name, value in ZOOPORTAL_COOKIES.items():
        if value:
            cookies_list.append({
                'name': name,
                'value': value,
                'domain': '.zooportal.pro',
                'path': '/'
            })
    return cookies_list


async def create_zooportal_browser_context():
    """Создает браузерный контекст с куками"""
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-gpu"
        ]
    )

    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )

    cookies = prepare_zooportal_cookies()
    if cookies:
        await context.add_cookies(cookies)

    return playwright, browser, context


# async def fetch_zooportal_page(url: str) -> str:
#     """Загружает страницу с использованием Playwright"""
#     playwright, browser, context = await create_zooportal_browser_context()
#
#     try:
#         page = await context.new_page()
#         await page.goto(url, wait_until='networkidle', timeout=90000)
#         await asyncio.sleep(10)
#
#         html = await page.content()
#         return html
#     finally:
#         await browser.close()
#         await playwright.stop()
async def fetch_zooportal_page(url: str) -> str:
    playwright, browser, context = await create_zooportal_browser_context()

    try:
        page = await context.new_page()

        logger.info(f"Загрузка: {url}")
        await page.goto(url, wait_until='networkidle', timeout=90000)

        await asyncio.sleep(5)

        html = await page.content()

        # Проверка
        if "pedigree/view" not in html:
            logger.info(f"Нет данных. Повторная попытка загрузки: {url}")
            await asyncio.sleep(5)
            html = await page.content()
        return html
    finally:
        await browser.close()
        await playwright.stop()

def parse_zooportal_search_results(html: str) -> List[Dict]:
    """Парсит результаты страницы поиска собак"""
    soup = BeautifulSoup(html, 'html.parser')
    dogs = []

    wrappers = soup.find_all('span', class_='item-wrapper')

    for wrapper in wrappers:
        try:
            item = wrapper.find('div', class_='item')
            if not item or 'PRO-аккаунт' in str(item):
                continue

            name_link = item.find('a', class_='name')
            if not name_link:
                continue

            name = name_link.get_text(strip=True)
            href = name_link.get('href', '')

            link_name = href if href.startswith('http') else f"{ZOOPORTAL_BASE_URL}{href}"

            match = re.search(r'/view/(\d+)/', href)
            if not match:
                continue

            dog_id = match.group(1)

            item_classes = item.get('class', [])
            sex = 0
            if 'red' in item_classes:
                sex = 2  # сука
            elif 'blue' in item_classes:
                sex = 1  # кобель

            # uuid_str = f"zooportal_{dog_id}"
            # uuid = hashlib.md5(uuid_str.encode()).hexdigest()

            dogs.append({
                'dog_id': dog_id,
                'registered_name': name,
                'sex': sex,
                # 'uuid': uuid,
                'url': f"{ZOOPORTAL_BASE_URL}{href}",
                'source': 'zooportal.pro'
            })
            # logger.info(f"------------------------ DOGS: {dogs}")


        except Exception as e:
            logger.error(f"Error parsing dog card: {e}")
            continue

    return dogs


async def parse_zooportal_search_page(page_num: int = 1) -> List[Dict]:
    """Парсит страницу поиска собак"""
    base_url = "https://zooportal.pro/pedigree/?bxajaxid=&AJAX_CALL=N&APPLY=Y&RESET=N&RAND=0.4655610706446941&FILTER_NAME=arrFilter&KENNEL_ID=&SHORT=&OWNER=&F%5BNAME%5D=&F%5BNICKNAME%5D=&F%5BDOCUMENT%5D=0&F%5BDOCUMENT_NUMBER%5D=&F%5BSTAMP%5D=&F%5BTHEME%5D=1209&F%5BSEX%5D=0&F%5BBREED%5D=16747920&F%5BBREED_PARAMETER1%5D=0&F%5BBREED_PARAMETER2%5D=0&F%5BBREED_PARAMETER3%5D=0&F%5BCOUNTRY%5D=0&F%5BREGION%5D=0&F%5BRAION%5D=0&F%5BCITY%5D=0&F%5BPUNKT%5D=0"
    url = f"{base_url}&PAGEN_1={page_num}"

    html = await fetch_zooportal_page(url)
    # logger.info(f"------------------------ HTML: {html}")
    return parse_zooportal_search_results(html)


def parse_zooportal_dog_info(soup: BeautifulSoup, dog_id: str) -> Dict:
    """Парсит основную информацию собаки со страницы собаки с Zooportal"""
    info = {'zooportal_id': dog_id}

    # ПАРСИНГ ФОТО
    photo_url = ""

    # 1. Сначала fancybox (оригинальное фото)
    fancybox = soup.find('a', class_='fancybox', rel='poto')
    if fancybox and fancybox.get('href'):
        href = fancybox.get('href')
        if href:
            if not href.startswith('http'):
                photo_url = f"{MAIN_ZOOPORTAL_URL}{href}"
            else:
                photo_url = href
            logger.info(f"Фото найдено через fancybox: {photo_url}")

    # 2. Если не нашли, пробуем через img
    if not photo_url:
        img = soup.find('img', class_='photo')
        if img and img.get('src'):
            src = img.get('src')
            if src:
                # Конвертируем уменьшенную версию в оригинал
                if 'resize_cache' in src:
                    original = src.replace('resize_cache/', '').replace('/300_170_2/', '/')
                    if not original.startswith('http'):
                        photo_url = f"{MAIN_ZOOPORTAL_URL}{original}"
                    else:
                        photo_url = original
                else:
                    if not src.startswith('http'):
                        photo_url = f"{MAIN_ZOOPORTAL_URL}{src}"
                    else:
                        photo_url = src
                # logger.info(f"Фото найдено через img: {photo_url}")

    # Сохраняем
    info['photo_url'] = photo_url if photo_url else ""

    # logger.info(f"Найдена ссылка на фото: {info['photo_url']}")

    # 1. Имя собаки
    h1 = soup.find('h1')
    if h1:
        info['registered_name'] = h1.get_text(strip=True)

    # 2. Кличка (русское имя)
    name_rus = soup.find('h2', class_='name_rus')
    if name_rus:
        info['call_name'] = name_rus.get_text(strip=True)

    # 3. Ищем блок "Личные данные"
    personal_data_text = None
    for element in soup.find_all(text=True):
        if 'Личные данные' in element:
            personal_data_text = element
            break

    if personal_data_text:
        parent = personal_data_text.parent
        all_tables_after = parent.find_all_next('table')

        if len(all_tables_after) > 0:
            main_table = all_tables_after[0]
            all_rows = main_table.find_all('tr')

            for row in all_rows:
                cells = row.find_all('td')
                for i in range(0, len(cells), 2):
                    if i + 1 < len(cells):
                        label_cell = cells[i]
                        value_cell = cells[i + 1]

                        label_text = label_cell.get_text(strip=True).lower()
                        value_text = value_cell.get_text(strip=True)

                        if not label_text or not value_text:
                            continue

                        if 'порода' in label_text:
                            info['breed'] = value_text
                        elif 'пол' in label_text:
                            if 'сука' in value_text.lower():
                                info['sex'] = 2
                            elif 'кобель' in value_text.lower():
                                info['sex'] = 1
                        elif 'дата рождения' in label_text:
                            info['date_of_birth'] = parse_date(value_text)
                        elif 'дата рождения:' in label_text:
                            info['date_of_birth'] = parse_date(value_text)
                        elif 'Дата рождения:' in label_text:
                            info['date_of_birth'] = parse_date(value_text)
                        elif 'клеймо' in label_text:
                            info['brand_chip'] = value_text
                        elif 'Клеймо' in label_text:
                            info['brand_chip'] = value_text
                        elif 'Клеймо:' in label_text:
                            info['brand_chip'] = value_text
                        elif 'чип' in label_text:
                            if 'brand_chip' in info:
                                info['brand_chip'] += f", {value_text}"
                            else:
                                info['brand_chip'] = value_text

    # 4. Окрас
    row2col_divs = soup.find_all('div', class_='row2col')
    for div in row2col_divs:
        col_text = div.find('div', class_='col-text')
        col_value = div.find('div', class_='col-value')

        if col_text and col_value:
            label = col_text.get_text(strip=True).lower()
            value = col_value.get_text(strip=True)

            if 'окрас' in label:
                info['color'] = value

    # 5. Номер родословной
    for element in soup.find_all(text=lambda t: t and '№ родословной' in t):
        parent = element.parent
        if parent.name == 'td':
            next_td = parent.find_next_sibling('td')
            if next_td:
                info['registration_number'] = next_td.get_text(strip=True)
                break


    breeder_found = False
    owner_found = False

    # Ищем все блоки с информацией
    labels = soup.find_all(text=True)

    for i, label in enumerate(labels):
        label_text = str(label).strip() if label else ""

        # Ищем родительский div с классом row2col
        parent = label.parent
        if parent and parent.name == 'div' and 'row2col' in parent.get('class', []):
            # Проверяем, есть ли у нас col-text и col-value
            col_text = parent.find('div', class_='col-text')
            col_value = parent.find('div', class_='col-value')

            if not col_text or not col_value:
                continue

            current_label = col_text.get_text(strip=True)

            if current_label == 'Заводчик:' and not breeder_found:
                breeder_found = True
                # Парсим заводчика
                breeder_link = col_value.find('a')
                if breeder_link:
                    info['breeder_name'] = breeder_link.get_text(strip=True)
                    info['breeder_url'] = breeder_link.get('href')
                    if info['breeder_url'] and not info['breeder_url'].startswith('http'):
                        info['breeder_url'] = f"{MAIN_ZOOPORTAL_URL}{info['breeder_url']}"
                else:
                    info['breeder_name'] = col_value.get_text(strip=True)

                # Ищем питомник заводчика в следующем row2col
                next_sibling = parent.find_next_sibling('div', class_='row2col')
                if next_sibling:
                    next_col_text = next_sibling.find('div', class_='col-text')
                    next_col_value = next_sibling.find('div', class_='col-value')

                    if next_col_text and next_col_text.get_text(strip=True) == 'Питомник:' and next_col_value:
                        kennel_link = next_col_value.find('a')
                        if kennel_link:
                            info['breeder_kennel'] = kennel_link.get_text(strip=True)
                            info['breeder_kennel_url'] = kennel_link.get('href')
                            if info['breeder_kennel_url'] and not info['breeder_kennel_url'].startswith('http'):
                                info['breeder_kennel_url'] = f"{MAIN_ZOOPORTAL_URL}{info['breeder_kennel_url']}"

            elif current_label == 'Владелец:' and not owner_found:
                owner_found = True
                # Парсим владельца
                owner_link = col_value.find('a')
                if owner_link:
                    info['owner_name'] = owner_link.get_text(strip=True)
                    info['owner_url'] = owner_link.get('href')
                    if info['owner_url'] and not info['owner_url'].startswith('http'):
                        info['owner_url'] = f"{MAIN_ZOOPORTAL_URL}{info['owner_url']}"
                else:
                    info['owner_name'] = col_value.get_text(strip=True)

                # Ищем питомник владельца в следующем row2col
                next_sibling = parent.find_next_sibling('div', class_='row2col')
                if next_sibling:
                    next_col_text = next_sibling.find('div', class_='col-text')
                    next_col_value = next_sibling.find('div', class_='col-value')

                    if next_col_text and next_col_text.get_text(strip=True) == 'Питомник:' and next_col_value:
                        kennel_link = next_col_value.find('a')
                        if kennel_link:
                            info['owner_kennel'] = kennel_link.get_text(strip=True)
                            info['owner_kennel_url'] = kennel_link.get('href')
                            if info['owner_kennel_url'] and not info['owner_kennel_url'].startswith('http'):
                                info['owner_kennel_url'] = f"{MAIN_ZOOPORTAL_URL}{info['owner_kennel_url']}"


    # 10. Парсинг титулов
    titles_data = parse_titles_from_html(soup)
    if titles_data:
        info['titles'] = titles_data
        # logger.info(f"Найдено титулов для собаки {dog_id}: {len(titles_data)}")

    # 9. Генерируем UUID (перенесено в parse_normal_dog_data_and_create_dog(raw: Dict[str, Any], source: str) в zooportal_integration
    # uuid_str = f"zooportal_{dog_id}"
    # info['uuid'] = hashlib.md5(uuid_str.encode()).hexdigest()

    # logger.info(f"======================== DOG_INFO: {info}")
    return info


def parse_zooportal_pedigree_table(soup: BeautifulSoup, dog_id: str) -> Dict:
    """
    Парсит таблицу родословной Zooportal.

    Возвращает:
    - ancestors: словарь предков (node_key -> данные)
    - relationships: список связей между узлами
    - base_dogs: базовые узлы (сама собака и ее родители)
    """
    pedigree = {
        'parents': {'dam': None, 'sire': None},
        'ancestors': {},
        'relationships': [],
        'base_dogs': {}
    }

    pedigree_table = soup.find('table', class_='pedigree-table')
    if not pedigree_table:
        return pedigree

    cells = pedigree_table.find_all('td', attrs={'code': True, 'child_id': True})

    def _extract_name(cell) -> str:
        """Извлекает имя предка из ячейки таблицы"""
        parent_input = cell.find('input', {'name': 'PARENT'})
        if parent_input and parent_input.get('value'):
            return parent_input.get('value').strip()

        link = cell.find('a')
        if link:
            return link.get_text(strip=True)

        animal_info = cell.find('div', class_='animal-info')
        if animal_info:
            text = animal_info.get_text(' ', strip=True)
            return text.strip()

        return ''

    def _extract_raw_text(cell) -> str:
        """Извлекает полный текст из ячейки"""
        infos = cell.find_all('div', class_='animal-info')
        if not infos:
            return ''
        return ' '.join([d.get_text(' ', strip=True) for d in infos]).strip()

    for cell in cells:
        try:
            code = (cell.get('code') or '').strip()
            child_id = (cell.get('child_id') or '').strip()
            if not code or not child_id:
                continue

            # Базовый узел ребенка
            base_key = f"{child_id}:"
            if base_key not in pedigree['base_dogs']:
                pedigree['base_dogs'][base_key] = {'zooportal_id': child_id}

            # Пропускаем "не указан" и пустые ячейки
            if 'animal_parent_not_set' in str(cell):
                continue

            ancestor_name = _extract_name(cell)
            if not ancestor_name:
                continue

            # Фильтр на "не указан/не указана"
            lowered = ancestor_name.lower()
            if 'не указан' in lowered or 'не указана' in lowered:
                continue

            # Определяем пол по последнему сегменту кода
            last = code.split('_')[-1]
            sex = 1 if last == 'FATHER' else 2 if last == 'MOTHER' else 0

            # zooportal_id предка (только если есть ссылка)
            ancestor_id = None

            link = cell.find('a', href=True)
            if link:
                href = link.get('href', '')
                m = re.search(r'/pedigree/view/(\d+)/', href)
                # logger.info(f"++++++++ ancestor HREF: {href}")
                if m:
                    ancestor_id = m.group(1)


            ancestor_data = {
                'name': ancestor_name,
                'sex': sex,
                'zooportal_id': ancestor_id,
                'guid': cell.get('guid'),
                'raw_text': _extract_raw_text(cell),
                'code': code,
                'child_id': child_id,
                'childs_steck': cell.get('childs_steck', ''),
            }
            # logger.info(f"------------------------ ANCESTOR_DATA: {ancestor_data}")

            node_key = f"{child_id}:{code}"
            pedigree['ancestors'][node_key] = ancestor_data

            # Родители для ROOT собаки
            if child_id == str(dog_id) and code == 'FATHER':
                pedigree['parents']['sire'] = ancestor_data
            elif child_id == str(dog_id) and code == 'MOTHER':
                pedigree['parents']['dam'] = ancestor_data

            # Строим связь к непосредственному родителю
            segments = code.split('_')
            if not segments:
                continue
            parent_key = node_key
            child_code = '_'.join(segments[:-1])  # префикс без последнего сегмента
            child_key = f"{child_id}:{child_code}"

            relation = 'sire' if segments[-1] == 'FATHER' else 'dam' if segments[-1] == 'MOTHER' else None
            if relation is None:
                continue

            pedigree['relationships'].append({
                'child_key': child_key,
                'parent_key': parent_key,
                'relation': relation,
            })
            # logger.info(f"------------------------ pedigree: {pedigree}")

        except Exception as e:
            logger.error(f"Error parsing pedigree cell: {e}")
            continue

    return pedigree

#
# def parse_titles_from_html(soup: BeautifulSoup) -> List[Dict[str, Any]]:
#     """
#     Полный парсер титулов из HTML страницы Zooportal.
#     Обрабатывает: "GrCH.RUS, CH.RUS, CH.CL RUS" и другие форматы.
#     """
#     titles_data = []
#
#     # Ищем div с классом 'titles' (исключаем subtitle с весом/ростом)
#     titles_div = soup.find('div', class_='titles')
#     if not titles_div:
#         return titles_data
#
#     # Проверяем, что это не блок с весом/ростом
#     div_classes = titles_div.get('class', [])
#     if 'subtitle' in div_classes:
#         return titles_data
#
#     titles_text = titles_div.get_text(strip=True)
#     if not titles_text:
#         return titles_data
#
#     logger.info(f"Найден текст титулов: '{titles_text}'")
#
#     # Нормализуем текст: убираем лишние пробелы, приводим к единому формату
#     normalized_text = re.sub(r'\s+', ' ', titles_text.strip())
#
#     # Разделяем титулы по запятым
#     raw_titles = [t.strip() for t in normalized_text.split(',')]
#
#     for raw_title in raw_titles:
#         if not raw_title:
#             continue
#
#         # Извлекаем код страны
#         country = extract_country_code(raw_title)
#
#         # Приводим к нижнему регистру для сравнения
#         title_lower = raw_title.lower()
#
#         # Инициализируем значения по умолчанию
#         short_name = raw_title
#         long_name = raw_title
#         is_prefix = True
#
#         # ОПРЕДЕЛЯЕМ ТИП ТИТУЛА (от специфичного к общему)
#
#         # 1. GrCH - Гранд Чемпион (самый высокий титул)
#         if 'grch' in title_lower or 'гранд чемпион' in title_lower:
#             short_name = "GrCH"
#             long_name = "Гранд Чемпион"
#             is_prefix = True
#
#         # 2. CH.CL - Чемпион Национального клуба породы
#         elif 'ch.cl' in title_lower or 'нкп' in title_lower or 'ch club' in title_lower:
#             short_name = "CH.CL"
#             long_name = "Чемпион Национального клуба породы"
#             is_prefix = True
#
#         # 3. JCH - Юниор Чемпион
#         elif 'jch' in title_lower or 'юниор' in title_lower:
#             short_name = "JCH"
#             long_name = "Юниор Чемпион"
#             is_prefix = True
#
#         # 4. VCH - Ветеран Чемпион
#         elif 'vch' in title_lower or 'ветеран' in title_lower:
#             short_name = "VCH"
#             long_name = "Ветеран Чемпион"
#             is_prefix = True
#
#         # 5. INT - Интернациональный Чемпион
#         elif 'int' in title_lower or 'интер' in title_lower or 'international' in title_lower:
#             short_name = "INT"
#             long_name = "Интернациональный Чемпион"
#             is_prefix = True
#
#         # 6. EU - Европейский Чемпион
#         elif 'eu' in title_lower or 'европ' in title_lower or 'european' in title_lower:
#             short_name = "EU"
#             long_name = "Европейский Чемпион"
#             is_prefix = True
#
#         # 7. WORLD - Чемпион Мира
#         elif 'world' in title_lower or 'мир' in title_lower:
#             short_name = "WORLD"
#             long_name = "Чемпион Мира"
#             is_prefix = True
#
#         # 8. BCH - Чемпион породы
#         elif 'bch' in title_lower or 'breed champion' in title_lower:
#             short_name = "BCH"
#             long_name = "Чемпион породы"
#             is_prefix = True
#
#         # 9. CH - Чемпион (общий случай - проверяем в последнюю очередь)
#         elif 'ch' in title_lower or 'чемпион' in title_lower:
#             # Проверяем, что это не часть другого титула
#             if not any(x in title_lower for x in ['grch', 'jch', 'vch', 'bch', 'ich']):
#                 short_name = "CH"
#                 long_name = "Чемпион"
#                 is_prefix = True
#
#         # 10. CACIB - Сертификат международной выставки
#         elif 'cacib' in title_lower:
#             short_name = "CACIB"
#             long_name = "Сертификат международной выставки"
#             is_prefix = False
#
#         # 11. CAC - Сертификат соответствия породе
#         elif 'cac' in title_lower and 'cacib' not in title_lower:
#             short_name = "CAC"
#             long_name = "Сертификат соответствия породе"
#             is_prefix = False
#
#         # 12. ЧК, КЧК - Чемпион клуба, Кандидат в чемпионы клуба
#         elif 'чк' in title_lower or 'кчк' in title_lower:
#             if 'чк' in title_lower:
#                 short_name = "ЧК"
#                 long_name = "Чемпион клуба"
#             else:
#                 short_name = "КЧК"
#                 long_name = "Кандидат в чемпионы клуба"
#             is_prefix = False
#
#         # 13. ЛП, ЛС - Лучший представитель породы, Лучший щенок
#         elif 'лп' in title_lower or 'лс' in title_lower:
#             if 'лп' in title_lower:
#                 short_name = "ЛП"
#                 long_name = "Лучший представитель породы"
#             else:
#                 short_name = "ЛС"
#                 long_name = "Лучший щенок"
#             is_prefix = False
#
#
#         # Проверяем, есть ли год в титуле
#         winner_year = None
#         has_winner_year = False
#         year_match = re.search(r'\b(19|20)\d{2}\b', raw_title)
#         if year_match:
#             winner_year = int(year_match.group())
#             has_winner_year = True
#
#         # Сохраняем титул со всеми данными
#         titles_data.append({
#             'short_name': short_name,
#             'long_name': long_name.strip(),
#             'country': country,  # Код страны: "RUS", "RKF", "BY" и т.д.
#             'raw_text': raw_title,  # Оригинальный текст
#             'is_prefix': is_prefix,  # True для префиксов (GrCH, CH и т.д.)
#             'has_winner_year': has_winner_year,  # Есть ли год
#             'winner_year': winner_year  # Год получения титула
#         })
#
#     logger.info(f"Распарсено {len(titles_data)} титулов")
#     return titles_data
#
#
# def extract_country_code(raw_title: str) -> Optional[str]:
#     """
#     Извлекает код страны из текста титула.
#
#     Примеры:
#     - "GrCH.RUS" → "RUS"
#     - "CH.CL RUS" → "RUS"
#     - "CH RUS" → "RUS"
#     - "Чемпион России" → "RUS"
#     - "INT.RKF" → "RKF"
#     """
#     # Приводим к верхнему регистру для поиска
#     title_upper = raw_title.upper()
#
#     # 1. Ищем код страны после точки: GrCH.RUS, CH.RUS
#     match = re.search(r'\.([A-Z]{2,4})\b', title_upper)
#     if match:
#         country = match.group(1)
#         # Проверяем, что это действительно код страны, а не часть титула
#         if country not in ['CH', 'CL', 'CAC', 'CACIB', 'INT', 'EU', 'WORLD']:
#             return country
#
#     # 2. Ищем код страны после пробела: CH.CL RUS, CH CL RUS
#     match = re.search(r'\s([A-Z]{2,4})\b', title_upper)
#     if match:
#         country = match.group(1)
#         if country not in ['CH', 'CL', 'CAC', 'CACIB']:
#             return country
#
#     # 3. Ищем русские названия стран
#     if 'РОССИИ' in title_upper or 'RUS' in title_upper or 'РФ' in title_upper:
#         return "RUS"
#     elif 'РКФ' in title_upper or 'RKF' in title_upper:
#         return "RKF"
#     elif 'БЕЛАРУСИ' in title_upper or 'BY' in title_upper or 'БЕЛ' in title_upper:
#         return "BY"
#     elif 'УКРАИНЫ' in title_upper or 'UA' in title_upper or 'УКР' in title_upper:
#         return "UA"
#     elif 'КАЗАХСТАНА' in title_upper or 'KZ' in title_upper or 'КАЗ' in title_upper:
#         return "KZ"
#
#     # 4. Ищем в скобках
#     match = re.search(r'\(([A-Z]{2,4})\)', title_upper)
#     if match:
#         return match.group(1)
#
#     return None
#
#
# def get_country_display_name(country_code: str) -> str:
#     """
#     Преобразует код страны в читаемое название на русском.
#     """
#     country_map = {
#         # Основные
#         'RUS': 'Россия',
#         'RU': 'Россия',
#         'РФ': 'Россия',
#
#         # РКФ
#         'RKF': 'РКФ',
#
#         # СНГ
#         'BY': 'Беларусь',
#         'BLR': 'Беларусь',
#         'UA': 'Украина',
#         'UKR': 'Украина',
#         'KZ': 'Казахстан',
#         'KAZ': 'Казахстан',
#
#         # Балтия
#         'LV': 'Латвия',
#         'LVA': 'Латвия',
#         'LT': 'Литва',
#         'LTU': 'Литва',
#         'EE': 'Эстония',
#         'EST': 'Эстония',
#
#         # Европа
#         'PL': 'Польша',
#         'POL': 'Польша',
#         'CZ': 'Чехия',
#         'CZE': 'Чехия',
#         'SK': 'Словакия',
#         'SVK': 'Словакия',
#         'HU': 'Венгрия',
#         'HUN': 'Венгрия',
#         'RO': 'Румыния',
#         'ROU': 'Румыния',
#         'BG': 'Болгария',
#         'BGR': 'Болгария',
#
#         # FCI
#         'FCI': 'FCI',
#
#         # Другие
#         'MD': 'Молдова',
#         'MDA': 'Молдова',
#         'GE': 'Грузия',
#         'GEO': 'Грузия',
#         'AM': 'Армения',
#         'ARM': 'Армения',
#         'AZ': 'Азербайджан',
#         'AZE': 'Азербайджан',
#     }
#
#     return country_map.get(country_code.upper(), country_code)

async def parse_zooportal_dog_page(dog_id: str, generations: int = 3) -> Dict:
    """
    Основная функция парсинга (без сохранения в БД) страницы собаки с родословной

    Args:
        dog_id: ID собаки на Zooportal
        generations: глубина родословной (реализовано для 3)

    Returns:
        Словарь с информацией о собаке и родословной
    """
    url = f"{ZOOPORTAL_BASE_URL}{ZOOPORTAL_DOG_PATH}/{dog_id}/?COUNT_GENERATIONS={generations}"
    html = await fetch_zooportal_page(url)

    soup = BeautifulSoup(html, 'html.parser')
    dog_info = parse_zooportal_dog_info(soup, dog_id)
    pedigree = parse_zooportal_pedigree_table(soup, dog_id)

    dog_info['zooportal_id'] = dog_id
    logger.info(f"-------------------------- DOG_DATA 2: {dog_info}")

    # logger.info(f"-------------------------- dog_info: {dog_info}")
    # logger.info(f"-------------------------- pedigree: {pedigree}")
    # logger.info(f"-------------------------- generations: {generations}")

    return {
        'dog_info': dog_info,
        'pedigree': pedigree,
        'generations': generations,
        'source': 'zooportal.pro'
    }


def normalize_zooportal_basic(dog_zooportal_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Отдельный парсер Zooportal -> нормализованный dict для дальнейшего merge.
    Специально для мерджа.
    """
    # Zooportal у вас уже snake_case, просто стабилизируем типы/ключи
    normalized: Dict[str, Any] = {
        "zooportal_id": str(dog_zooportal_data.get("zooportal_id") or ""),
        "registered_name": dog_zooportal_data.get("registered_name") or "",
        "breed": dog_zooportal_data.get("breed") or "",
        "sex": dog_zooportal_data.get("sex", 0),

        "photo_url": dog_zooportal_data.get("photo_url", ""),

        "date_of_birth": dog_zooportal_data.get("date_of_birth"),  # ожидаем datetime
        "brand_chip": dog_zooportal_data.get("brand_chip") or "",
        "color": dog_zooportal_data.get("color") or "",
        "registration_number": (dog_zooportal_data.get("registration_number") or "").replace(" ", ""),
        "titles": dog_zooportal_data.get("titles", []),

        # Данные заводчика
        "breeder_name": dog_zooportal_data.get("breeder_name") or "",
        "breeder_url": dog_zooportal_data.get("breeder_url") or "",
        "breeder_kennel_url": dog_zooportal_data.get("breeder_kennel_url") or "",
        "breeder_kennel": dog_zooportal_data.get("breeder_kennel") or "",

        # Данные владельца
        "owner_name": dog_zooportal_data.get("owner_name") or "",
        "owner_url": dog_zooportal_data.get("owner_url") or "",
        "owner_kennel_url": dog_zooportal_data.get("owner_kennel_url") or "",
        "owner_kennel": dog_zooportal_data.get("owner_kennel") or "",

        # Для обратной совместимости
        "kennel": dog_zooportal_data.get("kennel") or "",

        "link_name": dog_zooportal_data.get("link_name") or "",
        "uuid": dog_zooportal_data.get("uuid") or "",  # ВАЖНО: это НЕ breedarchive uuid, а созданный из zooportal_id (вероятнее весго тут передатся "")
    }
    # Добавляем ссылки для владельца и заводчика
    for key in ['breeder_url', 'owner_url']:
        if key in dog_zooportal_data:
            normalized[key] = dog_zooportal_data[key]
    # logger.info(f"---------------------------------------------normalized info: {normalized}")
    return normalized