import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from bs4 import BeautifulSoup

from playwright.async_api import async_playwright
from core.parsersConfig import ZOOPORTAL_BASE_URL, ZOOPORTAL_DOG_PATH, ZOOPORTAL_COOKIES
from utils.parser_utils import parse_date, parse_titles_from_html
from utils.memory_cache import cached, get_dog_data_from_cache, save_dog_data_to_cache
import asyncio

logger = logging.getLogger(__name__)

MAIN_ZOOPORTAL_URL = "https://zooportal.pro"


# Глобальные переменные для управления браузером
_browser_instance = None
_browser_lock = asyncio.Lock()
_browser_created_at = None
_MAX_BROWSER_AGE_MINUTES = 60  # Браузер умрет через 60 минут
_cleanup_task = None  # Фоновая задача для очистки


async def _create_new_browser():
    """Создать новый экземпляр браузера"""
    global _browser_instance, _browser_created_at, _browser_pages_count

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled"
        ]
    )

    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )

    cookies = prepare_zooportal_cookies()
    if cookies:
        await context.add_cookies(cookies)

    _browser_instance = (playwright, browser, context)
    _browser_created_at = datetime.now()
    _browser_pages_count = 0

    logger.info(f"Создан новый браузер (будет удален через {_MAX_BROWSER_AGE_MINUTES} минут)")

    # Запускаем фоновую задачу для очистки
    _start_background_cleanup()

    return _browser_instance


async def _cleanup_old_browser():
    """Удалить старый браузер, если он существует и устарел"""
    global _browser_instance, _browser_created_at

    async with _browser_lock:
        if _browser_instance is None:
            return

        if _browser_created_at is None:
            return

        now = datetime.now()
        browser_age = now - _browser_created_at

        if browser_age > timedelta(minutes=_MAX_BROWSER_AGE_MINUTES):
            minutes = browser_age.total_seconds() / 60
            logger.info(f"Браузер устарел ({minutes:.1f} мин), удаляем...")
            await _force_cleanup_browser()


async def _force_cleanup_browser():
    """Принудительно закрыть браузер"""
    global _browser_instance, _browser_created_at, _browser_pages_count

    if _browser_instance:
        try:
            playwright, browser, context = _browser_instance
            await context.close()
            await browser.close()
            await playwright.stop()
            logger.info("Браузер успешно закрыт")
        except Exception as e:
            logger.error(f"Ошибка при закрытии браузера: {e}")
        finally:
            _browser_instance = None
            _browser_created_at = None
            _browser_pages_count = 0


def _start_background_cleanup():
    """Запустить фоновую задачу для периодической проверки и очистки"""
    global _cleanup_task

    async def cleanup_checker():
        """Фоновая задача проверки устаревания браузера"""
        while True:
            try:
                await asyncio.sleep(60)  # Проверяем каждую минуту
                await _cleanup_old_browser()

                # Если браузер удален, выходим из цикла
                if _browser_instance is None:
                    break

            except Exception as e:
                logger.error(f"Ошибка в фоновой задаче очистки: {e}")
                await asyncio.sleep(60)

    # Запускаем только если нет активной задачи
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(cleanup_checker())


async def get_browser():
    """Получить браузер: создает новый или возвращает существующий"""
    global _browser_instance, _browser_created_at

    async with _browser_lock:
        # Если браузер не существует или отключен
        if _browser_instance is None:
            return await _create_new_browser()

        # Проверяем соединение с браузером
        playwright, browser, context = _browser_instance
        try:
            if not browser.is_connected():
                logger.warning("Браузер отключен, создаем новый")
                await _force_cleanup_browser()
                return await _create_new_browser()
        except:
            logger.warning("Ошибка проверки соединения браузера, создаем новый")
            await _force_cleanup_browser()
            return await _create_new_browser()

        # Проверяем, не устарел ли браузер
        now = datetime.now()
        if _browser_created_at:
            browser_age = now - _browser_created_at
            if browser_age > timedelta(minutes=_MAX_BROWSER_AGE_MINUTES):
                minutes = browser_age.total_seconds() / 60
                logger.info(f"Браузер устарел ({minutes:.1f} мин), пересоздаем")
                await _force_cleanup_browser()
                return await _create_new_browser()

        return _browser_instance


async def shutdown_browser():
    """Корректное завершение работы браузера"""
    global _cleanup_task

    # Останавливаем фоновую задачу
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass

    # Закрываем браузер
    await _force_cleanup_browser()
    logger.info("Браузер завершен")


async def safe_fetch_page(url: str, max_retries: int = 3) -> str:
    """Безопасная загрузка страницы с восстановлением браузера при ошибках"""
    for attempt in range(max_retries):
        try:
            playwright, browser, context = await get_browser()
            page = None

            try:
                page = await context.new_page()
                logger.info(f"Загрузка [{attempt + 1}/{max_retries}]: {url}")

                # Используем networkidle для надежности
                await page.goto(url, wait_until='networkidle', timeout=60000)

                # ДОБАВЬТЕ ЭТО: ожидание стабильности DOM
                await page.wait_for_function(
                    'document.readyState === "complete"',
                    timeout=10000
                )

                # Дополнительная пауза для JavaScript
                await asyncio.sleep(3)

                # Безопасное получение контента с обработкой ошибок
                try:
                    content = await page.content()
                except Exception as content_error:
                    logger.warning(f"Первая попытка content() не удалась: {content_error}")
                    await asyncio.sleep(2)
                    content = await page.content()

                return content

            finally:
                if page:
                    try:
                        await page.close()
                    except:
                        pass

        except Exception as e:
            logger.error(f"Ошибка при загрузке {url} (попытка {attempt + 1}): {e}")

            if attempt == max_retries - 1:
                raise

            # Ждем перед следующей попыткой
            await asyncio.sleep(3)

    raise Exception(f"Не удалось загрузить страницу после {max_retries} попыток")

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

@cached(ttl=7200)
async def fetch_zooportal_page(url: str) -> str:
    """Загружает страницу с использованием Playwright и кэширования"""
    return await safe_fetch_page(url)

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

            dogs.append({
                'dog_id': dog_id,
                'registered_name': name,
                'sex': sex,
                'url': f"{ZOOPORTAL_BASE_URL}{href}",
                'source': 'zooportal.pro'
            })


        except Exception as e:
            logger.error(f"Error parsing dog card: {e}")
            continue

    return dogs

@cached(ttl=7200)
async def parse_zooportal_search_page(page_num: int = 1) -> List[Dict]:
    """Парсит страницу поиска собак с кэшированием"""
    base_url = "https://zooportal.pro/pedigree/?bxajaxid=&AJAX_CALL=N&APPLY=Y&RESET=N&RAND=0.4655610706446941&FILTER_NAME=arrFilter&KENNEL_ID=&SHORT=&OWNER=&F%5BNAME%5D=&F%5BNICKNAME%5D=&F%5BDOCUMENT%5D=0&F%5BDOCUMENT_NUMBER%5D=&F%5BSTAMP%5D=&F%5BTHEME%5D=1209&F%5BSEX%5D=0&F%5BBREED%5D=16747920&F%5BBBREED_PARAMETER1%5D=0&F%5BBBREED_PARAMETER2%5D=0&F%5BBBREED_PARAMETER3%5D=0&F%5BCOUNTRY%5D=0&F%5BREGION%5D=0&F%5BRAION%5D=0&F%5BCITY%5D=0&F%5BPUNKT%5D=0"
    url = f"{base_url}&PAGEN_1={page_num}"

    html = await fetch_zooportal_page(url)
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
            # logger.info(f"Фото найдено через fancybox: {photo_url}")

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

@cached(ttl=7200)
async def parse_zooportal_dog_page(dog_id: str, generations: int = 3) -> Dict:
    """
    Основная функция парсинга страницы собаки с родословной
    Теперь с кэшированием
    """
    # Сначала проверяем специализированный кэш собаки
    cached_dog_data = await get_dog_data_from_cache(dog_id, "zooportal")
    if cached_dog_data and cached_dog_data.get('has_details', False):
        logger.info(f"Данные собаки {dog_id} взяты из кэша")
        return cached_dog_data.get('data')

    # Если нет в кэше, парсим
    url = f"{ZOOPORTAL_BASE_URL}{ZOOPORTAL_DOG_PATH}/{dog_id}/?COUNT_GENERATIONS={generations}"
    html = await fetch_zooportal_page(url)

    soup = BeautifulSoup(html, 'html.parser')
    dog_info = parse_zooportal_dog_info(soup, dog_id)
    pedigree = parse_zooportal_pedigree_table(soup, dog_id)

    dog_info['zooportal_id'] = dog_id

    result = {
        'dog_info': dog_info,
        'pedigree': pedigree,
        'generations': generations,
        'source': 'zooportal.pro'
    }

    # Сохраняем в специализированный кэш собак
    await save_dog_data_to_cache(
        dog_id,
        result,
        source="zooportal",
        has_details=True,
        ttl=7200  # 2 часа
    )

    return result

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
        "uuid": dog_zooportal_data.get("uuid") or "",  # это НЕ breedarchive uuid, а созданный из zooportal_id (вероятнее весго тут передатся "")
    }
    # Добавляем ссылки для владельца и заводчика
    for key in ['breeder_url', 'owner_url']:
        if key in dog_zooportal_data:
            normalized[key] = dog_zooportal_data[key]
    # logger.info(f"---------------------------------------------normalized info: {normalized}")
    return normalized