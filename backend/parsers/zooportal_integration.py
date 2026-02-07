import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union, Any, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import Title
from parsers.zooportal import (
    parse_zooportal_search_page,
    parse_zooportal_dog_page, normalize_zooportal_basic
)
from parsers.breedarchive import search_breedarchive_by_name, process_animal_by_uuid, fetch_breedarchive_basic_info, \
    normalize_breedarchive_basic

from models.dog import Dog
from models.people import Breeder, Owner
from models.associations import DogBreederLink, DogOwnerLink
from utils.dog_matcher import find_existing_dog, detect_conflicts, merge_dog_data, detect_dict_conflicts
from core.database import session_scope
from utils.parser_utils import transliterate_russian_to_english, parse_int, parse_date, parse_datetime, get_photo_url, \
    parse_coi, parse_float, parse_titles_from_text
import time

logger = logging.getLogger(__name__)

# Глобальный кэш для запросов к BreedArchive (в памяти)
_breedarchive_cache = {
    'search': {},  # name -> uuid
    'processed': {},  # uuid -> dog_data
    'search_timestamps': {}  # name -> timestamp (для инвалидации)
}

# Время жизни кэша (секунды)
CACHE_TTL = 300


def _clear_expired_cache():
    """Очистка устаревших записей кэша"""
    current_time = time.time()
    expired_keys = []
    for key, timestamp in _breedarchive_cache['search_timestamps'].items():
        if current_time - timestamp > CACHE_TTL:
            expired_keys.append(key)

    for key in expired_keys:
        _breedarchive_cache['search'].pop(key, None)
        _breedarchive_cache['search_timestamps'].pop(key, None)

# TODO Переделать
async def search_in_breedarchive_with_cache(dog_name: str, session_id: str = "") -> Optional[str]:
    """Ищет собаку в BreedArchive по имени с кэшированием (если будут дублированные запросы, могли получить из кеша данные)"""
    if not dog_name:
        return None

    # Очищаем устаревший кэш
    _clear_expired_cache()

    # Нормализуем имя для кэша
    cache_key = f"{session_id}:{dog_name.lower().strip()}"

    # Проверяем кэш
    if cache_key in _breedarchive_cache['search']:
        logger.info(f"Cache hit for: '{dog_name}'")
        return _breedarchive_cache['search'].get(cache_key)

    # Если нет в кэше - делаем запрос
    logger.info(f"Searching BreedArchive for: '{dog_name}'")

    # Прямой поиск
    try:
        uuid = await search_breedarchive_by_name(dog_name)
        if uuid:
            _breedarchive_cache['search'][cache_key] = uuid
            _breedarchive_cache['search_timestamps'][cache_key] = time.time()
            return uuid
    except Exception as e:
        logger.error(f"Error searching breedarchive for {dog_name}: {e}")

        uuid = await search_breedarchive_by_name(dog_name)
        if uuid:
            _breedarchive_cache['search'][cache_key] = uuid
            _breedarchive_cache['search_timestamps'][cache_key] = time.time()
            return uuid

    # Сохраняем None в кэш, чтобы не искать снова
    _breedarchive_cache['search'][cache_key] = None
    _breedarchive_cache['search_timestamps'][cache_key] = time.time()
    return None


async def search_in_breedarchive(dog_name: str, return_basic_info: bool = False) -> Optional[Union[str, Dict]]:
    """Ищет собаку в BreedArchive по имени через модуль breedarchive"""
    if not dog_name:
        return None

    # Используем функцию из breedarchive.py
    try:
        from parsers.breedarchive import search_breedarchive_by_name
        result = await search_breedarchive_by_name(dog_name, return_basic_info)
        return result
    except Exception as e:
        logger.error(f"Error searching breedarchive for {dog_name}: {e}")
        return None


def create_uuid_from_str(str: str) -> str:
    # Создаем строку в формате "zooportal_{dog_id}"
    uuid_str = f"zooportal_{str}"

    # Генерируем MD5 хеш
    return hashlib.md5(uuid_str.encode()).hexdigest()

async def process_ancestor_from_zooportal(
    session: AsyncSession,
    ancestor_data: Dict[str, Any],
    *,
    cache_by_name: Optional[Dict[str, int]] = None,  # ancestor_name -> Dog.id
) -> Optional[Dog]:
    """Обрабатывает предка из Zooportal (кеш по ancestor_name)."""
    try:
        ancestor_name = (ancestor_data.get("name") or "").strip()
        if not ancestor_name:
            return None

        low = ancestor_name.lower()
        if "не указан" in low or "не указана" in low:
            return None


        sex = int(ancestor_data.get("sex") or 0)
        zooportal_id = ancestor_data.get("zooportal_id")
        guid = ancestor_data.get("guid")
        raw_text = (ancestor_data.get("raw_text") or "").strip()

        # ===== 0) CACHE (по ancestor_name) =====
        cache_key = low

        if cache_by_name is not None:
            cached_id = cache_by_name.get(cache_key)
            if cached_id:
                return await session.get(Dog, cached_id)


        # 1) СНАЧАЛА ищем в БД — по zooportal_id, если он есть (по zoo_hash)
        # if zooportal_id:
        #     existingDog = await find_dog_by_zooportal_id(str(zooportal_id), session)
        #     if existingDog:
        #         dog = existingDog
        #         # ===== cache set =====
        #         if cache_by_name is not None and getattr(dog, "id", None):
        #             cache_by_name[cache_key] = dog.id
        #         return dog
        dog_hash = generate_zoo_hash(ancestor_data)
        existingDog = await find_dog_by_zoo_hash(dog_hash, session)
        if existingDog:
            # ===== cache set =====
            if cache_by_name is not None and getattr(existingDog, "id", None):
                cache_by_name[cache_key] = existingDog.id
            return existingDog

        # 2) Потом лезем в BreedArchive
        # (Бывают собаки-предки, у которых нет вообще данных, кроме имени.
        # И, чтобы получить больше данных, отправляем запрос на бридарчив)
        breedarchive_uuid = await search_in_breedarchive(ancestor_name)

        if breedarchive_uuid:
            try:
                result = await session.execute(
                    select(Dog).where(Dog.uuid == breedarchive_uuid)
                )
                existing_by_uuid = result.scalars().first()

                if existing_by_uuid:
                    logger.info(f"Dog with UUID {breedarchive_uuid} already exists")
                    if cache_by_name is not None and getattr(existing_by_uuid, "id", None):
                        cache_by_name[cache_key] = existing_by_uuid.id
                    return existing_by_uuid

                basic_data = await fetch_breedarchive_basic_info(breedarchive_uuid)
                if basic_data:
                    # Создаем новую собаку
                    new_dog = create_dog_from_basic_info_with_breedarchive(
                        basic_data, ancestor_data, zooportal_id, sex
                    )

                    session.add(new_dog)
                    await session.flush()

                    # Сохранение титулов
                    dogTitles = parse_titles_from_text(
                        basic_data.get('prefix_titles') or basic_data.get('prefixTitles'),
                        "breedarchive"
                    )
                    basic_data["titles"] = dogTitles
                    await save_dog_titles(new_dog, basic_data, session)

                    if cache_by_name is not None and getattr(new_dog, "id", None):
                        cache_by_name[cache_key] = new_dog.id
                    return new_dog
            except Exception as e:
                logger.error(f"Error processing BreedArchive ancestor {ancestor_name}: {e}")
                # ОТКАТ ТРАНЗАКЦИИ при ошибке
                try:
                    await session.rollback()
                except:
                    pass
                # basic_data = await fetch_breedarchive_basic_info(breedarchive_uuid)
                # if basic_data:
                    # 2.1) если уже есть в БД по BA uuid (дополнительная проверка)
                    # res = await session.execute(select(Dog).where(Dog.uuid == breedarchive_uuid))
                    # existing = res.scalars().first()
                    #
                    # if existing:
                    #     dog = existing
                    #     has_changes, _ = merge_dog_data(dog, basic_data, "breedarchive.com")
                    #     if has_changes:
                    #         session.add(dog)
                    #         await session.flush()

                        # ===== cache set =====
                        # if cache_by_name is not None and getattr(dog, "id", None):
                        #     cache_by_name[cache_key] = dog.id
                        # return dog

                    # 2.2) иначе создаём нового предка из BA basic
                    # new_dog = create_dog_from_basic_info_with_breedarchive(
                    #     basic_data, ancestor_data, zooportal_id, sex
                    # )
                    # session.add(new_dog)
                    # await session.flush()

                    # # Сохранение титулов из бридарчив
                    # dogTitles = parse_titles_from_text(
                    #     basic_data.get('prefix_titles') or basic_data.get('prefixTitles'), "breedarchive")
                    # basic_data["titles"] = dogTitles
                    # await save_dog_titles(new_dog, basic_data, session)

                    # ===== cache set =====
                    # if cache_by_name is not None and getattr(new_dog, "id", None):
                    #     cache_by_name[cache_key] = new_dog.id
                    #
                    # return new_dog

            # except Exception as e:
            #     logger.error(f"Error processing basic BreedArchive ancestor {ancestor_name}: {e}")
                # fallback дальше

        else:
            normalized = normalize_zooportal_ancestor_node(ancestor_data)
            # logger.info(f"------------------Logger normalized data {normalized}: {normalized}")
            new_dog = parse_normal_dog_data_and_create_dog(normalized, source="zooportal.pro")
            session.add(new_dog)
            await session.flush()
            # ===== cache set =====
            if cache_by_name is not None and getattr(new_dog, "id", None):
                cache_by_name[cache_key] = new_dog.id
                return new_dog
    except Exception as e:
        logger.error(f"Error processing ancestor: {e}")
        try:
            await session.rollback()
        except:
            pass
        return None


# Главный метод, используемый в роутере
async def process_zooportal_dog_with_ancestors(
        dog_id: str,
        max_generations: int = 3,
        session: AsyncSession = None
) -> Optional[Dog]:
    """Основная функция обработки собаки с предками из Zooportal"""
    try:
        # 1. Парсим данные с Zooportal
        logger.info(f"Parsing dog {dog_id} from Zooportal...")
        parsed_data = await parse_zooportal_dog_page(dog_id, max_generations)

        if not parsed_data:
            logger.error(f"Failed to parse dog {dog_id}")
            return None

        dog_info = parsed_data['dog_info']
        pedigree = parsed_data['pedigree']
        # logger.info(f"************************** pedigree: {pedigree}")

        # Убедимся, что имя не пустое
        dog_name = dog_info.get('registered_name', '').strip()

        dog = None

        # 2. Ищем в БД, если есть
        # existingDog = await find_dog_by_zooportal_id(dog_id, session)
        dog_hash = generate_zoo_hash(dog_info)
        existingDog = await find_dog_by_zoo_hash(dog_hash, session)

        if existingDog:
            logger.info(f"Dog with Zooportal_ID {dog_id} already exists, using existing record")
            dog = existingDog
            # TODO доделать merge_dog_data на обновление данных
            has_changes, conflicts = merge_dog_data(dog, dog_info, "zooportal.pro")
            if has_changes:
                session.add(dog)
                await session.flush()
        else:
            # 3. Если в БД нет такой собаки, ищем в бридарчив
            breedarchive_uuid = None
            breedarchive_basic_info = None

            if dog_name:
                # Отправляем запрос в бридарчив, получаем сразу и UUID, и базовую информацию из результата поиска
                search_result = await search_in_breedarchive(dog_name, return_basic_info=True)
                if isinstance(search_result, dict):
                    breedarchive_uuid = search_result.get('uuid')
                    breedarchive_basic_info = search_result.get('breedarchive_data', {})
                else:
                    breedarchive_uuid = search_result

            # 4. Если нашли в BreedArchive, обрабатываем оттуда
            # if breedarchive_uuid:
            #     try:
            #         logger.info(f"Found in BreedArchive: {breedarchive_uuid}")
            #         # TODO в отдельную функцию вынести код
            #         # Получаем базовую информацию (если ещё не получили)
            #         if not breedarchive_basic_info:
            #             basic_data = await fetch_breedarchive_basic_info(breedarchive_uuid)
            #         else:
            #             basic_data = breedarchive_basic_info
            #         #
            #         # # TODO в отдельную функцию вынести код
            #         # res = await session.execute(
            #         #     select(Dog).where(Dog.uuid == breedarchive_uuid))
            #         # existingBreedarchiveDogInDB = res.scalars().first()
            #
            #         # if existingBreedarchiveDogInDB:
            #         #     dog = existingBreedarchiveDogInDB
            #         #     logger.info(f"Found in DB with BreedArchive UUID: {breedarchive_uuid}")
            #         # if basic_data:
            #         #     has_changes, conflicts = merge_dog_data(dog, basic_data, "zooportal.pro")
            #         #     if has_changes:
            #         #         session.add(dog)
            #         #         await session.flush()
            #         # else:
            #         # Создаем собаку из базовых данных и с zooportal данными
            #         dog = create_dog_from_basic_info_with_breedarchive(basic_data, dog_info, dog_id)
            #         session.add(dog)
            #         await session.flush()
            #
            #         # Сохранение титулов из бридарчив
            #         dogTitles = parse_titles_from_text(
            #             basic_data.get('prefix_titles') or basic_data.get('prefixTitles'), "breedarchive")
            #         basic_data["titles"] = dogTitles
            #         await save_dog_titles(dog, basic_data, session)
            #
            #     except Exception as e:
            #         logger.error(f"Error processing breedarchive dog: {e}")
            #         dog = None
            if breedarchive_uuid:
                try:
                    result = await session.execute(
                        select(Dog).where(Dog.uuid == breedarchive_uuid)
                    )
                    dog = result.scalars().first()

                    basic_data = await fetch_breedarchive_basic_info(breedarchive_uuid)

                    if dog:
                        logger.info(f"Dog with UUID {breedarchive_uuid} already exists")
                        has_changes, conflicts = merge_dog_data(dog, basic_data, "breedarchive.com")
                        if has_changes:
                            session.add(dog)
                            await session.flush()
                            # Сохранение титулов из бридарчив
                            dogTitles = parse_titles_from_text(
                                basic_data.get('prefix_titles') or basic_data.get('prefixTitles'), "breedarchive")
                            basic_data["titles"] = dogTitles
                            await save_dog_titles(dog, basic_data, session)
                    else:
                        dog = create_dog_from_basic_info_with_breedarchive(
                            basic_data, dog_info, dog_id, dog_info.get('sex')
                        )
                        session.add(dog)
                        await session.flush()
                        # Сохранение титулов из бридарчив
                        dogTitles = parse_titles_from_text(
                            basic_data.get('prefix_titles') or basic_data.get('prefixTitles'), "breedarchive")
                        basic_data["titles"] = dogTitles
                        await save_dog_titles(dog, basic_data, session)
                except Exception as e:
                    logger.error(f"Error processing breedarchive dog by uuid: {breedarchive_uuid}: {e}")
                    # ОТКАТ ТРАНЗАКЦИИ при ошибке
                    try:
                        await session.rollback()
                    except:
                        pass

            # 5. Если не нашли в BreedArchive, создаем из Zooportal с имеющимися данными
            else:
                logger.info(f"Creating from Zooportal: {dog_name}")
                try:
                    # Создаем новую собаку только из Zooportal
                    dog = create_dog_from_zooportal_only(dog_info)
                    session.add(dog)

                    await session.flush()
                except Exception as e:
                    logger.error(f"Error creating dog from Zooportal: {dog_name}: {e}")
                    await session.rollback()
                    dog = None

        try:
            await save_owner_and_breeder(dog, dog_info, session)
        except Exception as e:
            logger.warning(f"Не удалось сохранить связи для собаки с owner, breeder. Dog_id: {dog.id} , Dog_name: ({dog.registered_name}): {e}")
            logger.debug(f"Ошибка детально:", exc_info=True)

        try:
            # Сохранение титулов из зоопортал
            await save_dog_titles(dog, dog_info, session)
        except Exception as e:
            logger.warning(f"Не удалось сохранить титулы для собаки с Dog_id: {dog.id} , Dog_name: ({dog.registered_name}): {e}")
            logger.debug(f"Ошибка детально:", exc_info=True)


        # 6. Обрабатываем предков из таблицы родословной
        if pedigree and pedigree.get('ancestors'):
            cache_by_key: Dict[str, int] = {}
            ba_name_cache: Dict[str, Optional[str]] = {}
            ba_uuid_cache: Dict[str, int] = {}
            node_to_dog_id: Dict[str, int] = {}

            # ROOT node for текущей собаки
            root_key = f"{dog_id}:"
            node_to_dog_id[root_key] = dog.id

            # 7.1. Обрабатываем базовые child_id из таблицы (нужно, чтобы можно было ставить родителям связи)
            for base_key, base_meta in (pedigree.get('base_dogs') or {}).items():
                child_zoo_id = base_meta.get('zooportal_id')
                # logger.info(f"++++++++++++++++++ base_meta: {base_meta}")
                # child_zoo_name = base_meta.get('registered_name')

                if not child_zoo_id:
                    continue
                base_dog = await ensure_base_dog_cached(
                    session,
                    str(child_zoo_id),
                    root_dog_id=str(dog_id),
                    root_dog=dog,
                    cache_by_key=cache_by_key,
                    ba_name_cache=ba_name_cache,
                )
                if base_dog:
                    # logger.info(f"++++++++++++++++++ base_dog: {base_dog}")
                    node_to_dog_id[base_key] = base_dog.id

            # 7.2. Обрабатываем всех предков из таблицы (каждый предок = отдельная запись Dog)
            for node_key, ancestor_data in (pedigree.get('ancestors') or {}).items():
                try:
                    ancestor_dog = await process_ancestor_from_zooportal(
                        session,
                        ancestor_data,
                        # cache_by_key=cache_by_key,
                        cache_by_name=ba_name_cache,
                        # ba_uuid_cache=ba_uuid_cache,
                    )
                    if ancestor_dog:
                        node_to_dog_id[node_key] = ancestor_dog.id
                except Exception as e:
                    logger.error(f"Error processing ancestor {node_key}: {e}")

            # 7.3. Устанавливаем связи sire/dam по relationships
            for rel in (pedigree.get('relationships') or []):
                try:
                    child_key = rel.get('child_key')
                    parent_key = rel.get('parent_key')
                    relation = rel.get('relation')
                    if not child_key or not parent_key or relation not in ('sire', 'dam'):
                        continue
                    if child_key not in node_to_dog_id or parent_key not in node_to_dog_id:
                        continue

                    child_dog = await session.get(Dog, node_to_dog_id[child_key])
                    parent_dog = await session.get(Dog, node_to_dog_id[parent_key])
                    if not child_dog or not parent_dog:
                        continue

                    if relation == 'sire':
                        child_dog.sire_id = parent_dog.id
                        child_dog.sire_name = parent_dog.registered_name
                    else:
                        child_dog.dam_id = parent_dog.id
                        child_dog.dam_name = parent_dog.registered_name

                    session.add(child_dog)
                except Exception as e:
                    logger.error(f"Error setting relationship: {e}")

            await session.flush()

        logger.info(f"Successfully processed dog {dog.id}: {dog.registered_name}")

        return dog

    except Exception as e:
        logger.error(f"Error processing dog {dog_id}: {e}")
        return None

def stable_uuid_from_ancestor(*, zooportal_id: Optional[str], guid: Optional[str], name: str) -> str:
    """
    Делает стабильный uuid для предка, если нет настоящего uuid (как у zooportal page).
    Приоритет: zooportal_id -> guid -> name
    """
    base = (str(zooportal_id or "").strip() or str(guid or "").strip() or name.strip() or "unknown")
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def normalize_zooportal_ancestor_node(ancestor: Dict[str, Any]) -> Dict[str, Any]:
    """
    Zooportal pedigree['ancestors'][node_key] -> нормализованный dict под parse_dog_basic_data.

    Важно:
    - zooportal_id может быть None.
    """
    name = (ancestor.get("name") or "").strip()
    sex = int(ancestor.get("sex") or 0)

    zooportal_id = ancestor.get("zooportal_id")
    # zooportal_id_str = str(zooportal_id).strip() if zooportal_id not in (None, "", 0, "0") else ""
    guid = (ancestor.get("guid") or "").strip()
    raw_text = (ancestor.get("raw_text") or "").strip()
    source = "zooportal.pro"

    registration_number = (ancestor.get("registration_number") or "").strip()
    brand_chip = (ancestor.get("brand_chip") or "").strip()
    color = (ancestor.get("color") or "").strip()

    normalized: Dict[str, Any] = {
        # обязательные / важные
        # "uuid": stable_uuid_from_ancestor(zooportal_id=zooportal_id, guid=guid, name=name),
        "registered_name": name or "Unknown",
        "sex": sex,
        "source": source,
        "link_name": ancestor.get("link_name") or "",
        "zooportal_id": zooportal_id,
        # минимальные заметки (часто там титулы/рег.номер/окрас)
        "notes": raw_text[:1000] if raw_text else "",
        "guid": guid,
        "registration_number": registration_number,
        "brand_chip": brand_chip,
        "registration_status": None,
        "color": color,
    }
    return normalized

def create_dog_from_zooportal_ancestor_node(ancestor: Dict[str, Any]) -> Dog:
    """
    Создаёт Dog из одного узла pedigree['ancestors'].
    Использует существующий общий парсер parse_dog_basic_data.
    """
    normalized = normalize_zooportal_ancestor_node(ancestor)
    dog = parse_normal_dog_data_and_create_dog(normalized, source="zooportal.pro")
    return dog


async def ensure_base_dog_cached(
    session: "AsyncSession",
    child_zoo_id: str,
    *,
    root_dog_id: str,
    root_dog: "Dog",
    cache_by_key: Dict[str, int],
    ba_name_cache: Optional[Dict[str, Optional[str]]] = None,
) -> Optional["Dog"]:
    """
    - работает для ensure_base_dog
    - использует кэш cache_by_key по ключу base:{child_zoo_id}
    - если child_zoo_id == root_dog_id -> возвращает root_dog
    - парсит Zooportal с generations=1 (как и нужно для ensure)

    Суть в том, что на сайте даются предки в виде таблицы-графа,
    из-за чего необходимо полученными данными удостоверяться,
    что предок создан, чтобы для этого предка создать его предка
    и проставить связь корректно между ними

    """
    if not child_zoo_id or child_zoo_id == '0':
        logger.warning(f"Ignoring invalid zooportal_id: {child_zoo_id}")
        return None

    # 0) ROOT shortcut
    if str(child_zoo_id) == str(root_dog_id):
        return root_dog

    # 1) Cache shortcut
    cache_key = f"base:{child_zoo_id}"
    if cache_key in cache_by_key:
        dog_id = cache_by_key[cache_key]
        if dog_id:
            return await session.get(Dog, dog_id)
    # if cache_key in cache_by_key:
    #     return await session.get(Dog, cache_by_key[cache_key])

    # 1. Парсим данные с Zooportal
    logger.info(f"Parsing dog {child_zoo_id} from Zooportal...")
    parsed_data = await parse_zooportal_dog_page(str(child_zoo_id), 1)

    if not parsed_data:
        logger.error(f"Failed to parse dog {child_zoo_id}")
        return None

    dog_info = parsed_data['dog_info']
    # TODO сделать обработку и их предков (чтобы не отправлять еще больше запросов)
    # pedigree = parsed_data['pedigree']  # для ensure не обязателен

    # Убедимся, что имя не пустое
    dog_name = dog_info.get('registered_name', '').strip()

    # 2. Ищем в БД, если есть
    # existingDog = await find_dog_by_zooportal_id(str(child_zoo_id), session)
    dog_hash = generate_zoo_hash(dog_info)
    existingDog = await find_dog_by_zoo_hash(dog_hash, session)

    if existingDog:
        logger.info(f"Dog with Zooportal_ID {child_zoo_id} already exists, using existing record")
        dog = existingDog
        # TODO доделать merge_dog_data на обновление данных
        has_changes, conflicts = merge_dog_data(dog, dog_info, "zooportal.pro")
        if has_changes:
            session.add(dog)
            await session.flush()
    else:
        # 3. Если в БД нет такой собаки, ищем в бридарчив
        breedarchive_uuid = None
        breedarchive_basic_info = None
        dog = None

        if dog_name:
            # (ДОБАВЛЕНО ТОЛЬКО ДЛЯ ensure): кеш имени -> BA uuid
            if ba_name_cache is not None and dog_name in ba_name_cache:
                breedarchive_uuid = ba_name_cache[dog_name]
                breedarchive_basic_info = {}
            else:
                # Отправляем запрос в бридарчив, получаем сразу и UUID, и базовую информацию из результата поиска
                search_result = await search_in_breedarchive(dog_name, return_basic_info=True)
                if isinstance(search_result, dict):
                    breedarchive_uuid = search_result.get('uuid')
                    breedarchive_basic_info = search_result.get('breedarchive_data', {})
                else:
                    breedarchive_uuid = search_result

                if ba_name_cache is not None:
                    ba_name_cache[dog_name] = breedarchive_uuid

        # 4. Если нашли в BreedArchive, обрабатываем оттуда
        if breedarchive_uuid:
            try:
                logger.info(f"Found in BreedArchive: {breedarchive_uuid}")
                # TODO логику на проверку айди чтобы найти точно ту собаку (левенштейна)
                # TODO в отдельную функцию вынести код
                # Получаем базовую информацию (если ещё не получили)
                if not breedarchive_basic_info:
                    basic_data = await fetch_breedarchive_basic_info(breedarchive_uuid)
                else:
                    basic_data = breedarchive_basic_info

                # TODO в отдельную функцию вынести код
                res = await session.execute(
                    select(Dog).where(Dog.uuid == breedarchive_uuid))
                existingBreedarchiveDogInDB = res.scalars().first()

                if existingBreedarchiveDogInDB:
                    dog = existingBreedarchiveDogInDB
                    logger.info(f"Found in DB with BreedArchive UUID: {breedarchive_uuid}")
                    if basic_data:
                        has_changes, conflicts = merge_dog_data(dog, basic_data, "zooportal.pro")
                        if has_changes:
                            session.add(dog)
                            await session.flush()
                else:
                    # Создаем собаку из базовых данных и с zooportal данными
                    dog = create_dog_from_basic_info_with_breedarchive(basic_data, dog_info, str(child_zoo_id))
                    session.add(dog)
                    await session.flush()
            except Exception as e:
                logger.error(f"Error processing breedarchive dog: {e}")
                dog = None

        # 5. Если не нашли в BreedArchive, создаем из Zooportal с имеющимися данными
        else:
            logger.info(f"Creating from Zooportal: {dog_name}")
            try:
                # Создаем новую собаку только из Zooportal
                dog = create_dog_from_zooportal_only(dog_info)
                session.add(dog)

                await session.flush()
            except Exception as e:
                logger.error(f"Error creating dog from Zooportal: {dog_name}: {e}")
                await session.rollback()
                dog = None


    # Записываем в кеш, если собака получилась
    # if dog:
    #     cache_by_key[cache_key] = dog.id
    if dog and getattr(dog, "id", None):
        cache_by_key[cache_key] = dog.id

    return dog


def create_dog_from_zooportal_only(dog_zooportal_data: Dict[str, Any]) -> Dog:
    zp = normalize_zooportal_basic(dog_zooportal_data)

    # date_of_birth -> year/month/day
    dob = zp.get("date_of_birth")
    if isinstance(dob, datetime):
        zp["year_of_birth"] = dob.year
        zp["month_of_birth"] = dob.month
        zp["day_of_birth"] = dob.day

    # создаём Dog через общий парсер
    dog = parse_normal_dog_data_and_create_dog(zp, source="zooportal.pro")
    # dog.zooportal_id = zp["zooportal_id"]

    return dog

def create_dog_from_basic_info_with_breedarchive(
    basic_breedarchive_data: Dict[str, Any],
    dog_zooportal_data: Dict[str, Any],
    dog_zooportal_id: Optional[str],
        sex: int = 0
) -> Dog:
    """
    Создает Dog:
    - приоритет полей BreedArchive basic
    - sex всегда из Zooportal
    - Zooportal дополняет отсутствующие поля (дата рождения, рег.номер, клеймо/чип, ссылка и т.п.)
    - sire_id/dam_id остаются None (как у вас)
    """
    # 1) нормализуем источники
    ba = normalize_breedarchive_basic(basic_breedarchive_data)
    zp = normalize_zooportal_basic(dog_zooportal_data)

    # if dog_zooportal_id:
    #     zp["zooportal_id"] = dog_zooportal_id

    # 2) гарантируем имя (если BA пустой) (перенесено вниз)
    # if not ba.get("registered_name"):
    #     ba["registered_name"] = zp.get("registered_name", "")

    # 3) мерж: BA приоритет, ZP только дополняет
    # merged = merge_prefer_left(ba, zp)

    merged, has_conflicts, conflicts = merge_prefer_left_with_conflicts(
        left=ba,
        right=zp,
        left_source="breedarchive.com",
        right_source="zooportal.pro",
    )
    # Если нет данных у собаки (типа предок с именем пока что)
    if sex == 0:
        sex = zp.get("sex", merged.get("sex", 0))

    # 4)
    # merged["sex"] = zp.get("sex", merged.get("sex", 0))
    merged["sex"] = sex
    # if dog_zooportal_id:
    #     merged["zooportal_id"] = dog_zooportal_id
    merged["zooportal_id"] = zp.get("zooportal_id", "")

    # 5) если у BA только year_of_birth, а Zooportal дал полноценный date_of_birth — сохраняем date_of_birth
    # parse_dog_basic_data умеет принять date_of_birth напрямую
    if isinstance(zp.get("date_of_birth"), datetime) and not merged.get("date_of_birth"):
        merged["date_of_birth"] = zp["date_of_birth"]
        merged["year_of_birth"] = zp["date_of_birth"].year
        merged["month_of_birth"] = zp["date_of_birth"].month
        merged["day_of_birth"] = zp["date_of_birth"].day

    # 6) создаём Dog из объединённых базовых данных (используем ваш парсер)
    dog = parse_normal_dog_data_and_create_dog(merged, source="breedarchive.com")

    # Merged owner, kennel, breeder info (в базовой информации не приходят данные из BreedArchive)
    merged["breeder_name"] = zp["breeder_name"]
    merged["owner_name"] = zp["owner_name"]
    merged["kennel"] = zp["kennel"]
    # Имя оставляем как в зоопортал
    merged["registered_name"] = zp.get("registered_name", "")

    # 7) пометка источников
    note = "Added basic data from BreedArchive"
    if getattr(dog, "notes", ""):
        dog.notes = f"{dog.notes} ({note})"
    else:
        dog.notes = note

    if has_conflicts:
        dog.has_conflicts = True

        if getattr(dog, "conflicts", None) is None:
            dog.conflicts = {}

        # аккумулируем (не затираем)
        for field, by_source in conflicts.items():
            dog.conflicts.setdefault(field, {})
            dog.conflicts[field].update(by_source)


    return dog


def generate_zoo_hash(dog_data: Dict[str, Any]) -> str:
    """
    Генерирует SHA-256 хэш для уникальной идентификации собаки.
    Основан на имени (registered_name) и  поле (sex) собаки.

    Args:
        dog_data: Словарь с данными собаки

    Returns:
        SHA-256 хэш в hex формате (64 символа)
    """
    # Базовые данные для хэша
    # name = dog_data.get('registered_name', '').strip()
    name = dog_data.get('registered_name') or dog_data.get('name') or dog_data.get('registeredName') or ''
    sex = dog_data.get('sex', 0)

    normalized_name = name.strip().upper()
    # kennel = dog_data.get('kennel', '').strip()
    # birth_date = dog_data.get('date_of_birth')

    # Нормализация пола (для совместимости)
    sex_str = "male" if sex == 1 else "female" if sex == 2 else "unknown"

    # Формируем строку для хэширования

    # Только имя и пол (минимальные данные)
    base_string = f"{normalized_name}|{sex_str}"

    # Генерация SHA-256 хэша
    return hashlib.sha256(base_string.encode('utf-8')).hexdigest()


# Основная функция для создания собаки
def parse_normal_dog_data_and_create_dog(raw: Dict[str, Any], source: str) -> Dog:
    """
    Парсит данные собаки для создания объекта Dog.
    """

    current_time = datetime.now()

    # Парсинг registration_status - ДОЛЖЕН БЫТЬ INTEGER или None
    reg_status = raw.get("registration_status")
    if isinstance(reg_status, str):
        reg_status_int = parse_int(reg_status)
    else:
        reg_status_int = reg_status

    dog_zoo_hash = generate_zoo_hash(raw)

    # Парсинг даты рождения
    date_of_birth = None
    year = raw.get("year_of_birth")
    month = raw.get("month_of_birth")
    day = raw.get("day_of_birth")

    # 1. Сначала пробуем готовую дату
    if raw.get('date_of_birth'):
        try:
            date_of_birth = parse_datetime(raw['date_of_birth'])
        except:
            pass  # Не получилось - пробуем дальше

    # 2. Если готовой даты нет - создаем из полей
    if not date_of_birth and year:
        try:
            # Безопасно парсим числа
            year_int = int(year) if str(year).isdigit() else None
            month_int = int(month) if month and str(month).isdigit() else 1
            day_int = int(day) if day and str(day).isdigit() else 1

            if year_int:
                # Ограничиваем границы
                month_int = max(1, min(12, month_int))
                day_int = max(1, min(31, day_int))

                # Пробуем создать дату
                date_of_birth = datetime(year_int, month_int, day_int)
        except:
            # Если ошибка - пробуем проще
            try:
                # ставим месяц 1, день 1 (загрушка)
                date_of_birth = datetime(year_int, 1, 1)
            except:
                date_of_birth = None

    # 3. Безопасно получаем год, месяц, день
    if date_of_birth:
        final_year = date_of_birth.year
        final_month = date_of_birth.month
        final_day = date_of_birth.day
    else:
        # Если даты нет - пробуем взять отдельные поля
        final_year = int(year) if year and str(year).isdigit() else None
        final_month = int(month) if month and str(month).isdigit() else None
        final_day = int(day) if day and str(day).isdigit() else None


    # Парсинг coi_updated_on
    coi_updated_on = None
    if raw.get("coi_updated_on"):
        coi_updated_on = parse_datetime(raw.get("coi_updated_on"))

    # # Безопасное получение URL фото
    # photo_url = None
    # try:
    #     if raw.get("primary_photo_path"):
    #         photo_url = get_photo_url({'primary_photo_path': raw['primary_photo_path']})
    # except Exception:
    #     photo_url = None

    # Парсинг incomplete_pedigree
    incomplete_pedigree = False
    incomplete_raw = raw.get("incomplete_pedigree")
    if isinstance(incomplete_raw, bool):
        incomplete_pedigree = incomplete_raw
    elif isinstance(incomplete_raw, str):
        incomplete_pedigree = incomplete_raw.lower() in ['true', '1', 'yes', 't']

    # Получаем и валидируем UUID
    existing_uuid = raw.get("uuid")
    uuid_value = None

    # 1. Проверяем существующий UUID
    if existing_uuid is not None:
        cleaned = str(existing_uuid).strip()
        if cleaned and cleaned.lower() not in {"null", "none", "n/a", ""}:
            uuid_value = cleaned

    # 2. Если UUID невалиден или отсутствует - создаем новый
    if not uuid_value:
        # Используем registered_name как источник
        name_for_uuid = raw.get("registered_name")
        uuid_value = create_uuid_from_str(name_for_uuid)

    # logger.info(f"UUID: {uuid_value}")

    # Базовые данные
    base_data = {
        # Базовые поля
        # "uuid": raw.get("uuid"),
        "uuid": uuid_value,
        "registered_name": raw.get("registered_name") or "",
        "link_name": raw.get("link_name") or "",
        "zooportal_id": raw.get("zooportal_id") or "",
        "source": source,
        "zoo_hash": dog_zoo_hash,

        # Демографические данные
        "sex": raw.get("sex", 0),
        "year_of_birth": final_year,
        "month_of_birth": final_month,
        "day_of_birth": final_day,
        # "year_of_birth": parse_int(year),
        # "month_of_birth": parse_int(month),
        # "day_of_birth": parse_int(day),
        "date_of_birth": date_of_birth,

        # Место рождения
        "land_of_birth": raw.get("land_of_birth") or "",
        "land_of_standing": raw.get("land_of_standing") or "",
        "land_of_birth_code": raw.get("land_of_birth_code") or "",

        # Внешний вид
        "color": raw.get("color") or "",
        "variety": raw.get("variety") or "",

        # Титулы
        "prefix_titles": raw.get("prefix_titles") or "",
        "suffix_titles": raw.get("suffix_titles") or "",

        # Регистрация
        "registration_status": reg_status_int,
        "coi": parse_coi(raw.get("coi")),
        "coi_updated_on": coi_updated_on,  # <-- datetime или None
        "incomplete_pedigree": incomplete_pedigree,

        # Фото
        "photo_url": raw.get("photo_url") or "",

        # Поля, которые могут быть
        "call_name": raw.get("call_name") or "",
        "year_of_death": parse_int(raw.get("year_of_death")),
        "month_of_death": parse_int(raw.get("month_of_death")),
        "day_of_death": parse_int(raw.get("day_of_death")),
        "date_of_death": parse_datetime(raw.get("date_of_death")),  # <-- parse_datetime вместо parse_date
        "land_of_standing": raw.get("land_of_standing") or "",
        "size": parse_float(raw.get("size")),
        "weight": parse_float(raw.get("weight")),
        "color_marking": raw.get("color_marking") or "",
        "eyes_color": raw.get("eyes_color") or "",
        "distinguishing_features": raw.get("distinguishing_features") or "",
        "other_titles": raw.get("other_titles") or "",
        "registration_number": re.sub(r"\s+", "", raw.get("registration_number") or ""),
        "brand_chip": raw.get("brand_chip") or "",
        "locked": raw.get("locked"),
        "removed": raw.get("removed"),
        "show_ad": raw.get("show_ad"),
        "is_new": raw.get("is_new"),
        "modified": raw.get("modified"),
        # "modified_at": parse_datetime(raw.get("modified_at")),
        # Текущее время для modified_at
        "modified_at": current_time,
        "health_info_general": raw.get("health_info_general", []),
        "health_info_genetic": raw.get("health_info_genetic", []),
        "neutered": raw.get("neutered", False),
        "approved_for_breeding": raw.get("approved_for_breeding", False),
        "frozen_semen": raw.get("frozen_semen", False),
        "artificial_insemination": raw.get("artificial_insemination", False),
        "kennel": raw.get("kennel") or "",
        "notes": raw.get("notes") or "",
        "data_correctness_notes": raw.get("data_correctness_notes") or "",
        "club": raw.get("club") or "",
        "sports": raw.get("sports", []),

        # Конфликты и родители
        "has_conflicts": False,
        "conflicts": {},
        "dam_id": None,
        "sire_id": None,
        "dam_uuid": raw.get("dam_uuid") or "",
        "dam_name": raw.get("dam_name") or "",
        "dam_link_name": raw.get("dam_link_name") or "",
        "sire_uuid": raw.get("sire_uuid") or "",
        "sire_name": raw.get("sire_name") or "",
        "sire_link_name": raw.get("sire_link_name") or "",
    }

    # Убираем None значения
    cleaned_data = {k: v for k, v in base_data.items() if v is not None}

    # Убедимся, что обязательные поля не пустые
    if not cleaned_data.get("registered_name"):
        cleaned_data["registered_name"] = f"Unknown Dog {cleaned_data.get('uuid', 'unknown')[:8]}"

    # Создаем собаку
    dog = Dog(**cleaned_data)

    return dog


def merge_prefer_left_with_conflicts(
    left: Dict[str, Any],
    right: Dict[str, Any],
    left_source: str = "breedarchive.com",
    right_source: str = "zooportal.pro",
) -> Tuple[Dict[str, Any], bool, Dict[str, Dict[str, Any]]]:
    """
    - left имеет приоритет
    - right дополняет только пустые поля
    - конфликты детектятся между словарями
    """

    # 1) detect conflicts
    has_conflicts, conflicts = detect_dict_conflicts(
        left, right, left_source, right_source
    )

    # 2) merge prefer left
    out = dict(left)

    def is_empty(v: Any) -> bool:
        return v is None or v == ""

    for k, rv in right.items():
        if rv in (None, ""):
            continue

        if k not in out or is_empty(out.get(k)):
            out[k] = rv

    return out, has_conflicts, conflicts


def merge_prefer_left(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """
    Мерж: берём left как основу (приоритет), а из right докидываем только если в left пусто.
    Пусто = None / "" / 0 (для некоторых полей 0 может быть валиден — если это важно).
    """
    out = dict(left)

    def is_empty(v: Any) -> bool:
        return v is None or v == ""  # намеренно НЕ считаем 0 пустым по умолчанию

    for k, rv in right.items():
        if k not in out or is_empty(out.get(k)):
            if rv is not None and rv != "":
                out[k] = rv
    return out

async def process_zooportal_search_page_and_save(
        page_num: int = 1,
        max_dogs: int = 10,
        delay_between_dogs: float = 2.0
) -> Dict:
    """Обрабатывает страницу поиска на Zooportal и сохраняет всех собак в базу"""
    try:
        logger.info(f"Processing Zooportal search page {page_num}")

        # 1. Парсим страницу поиска
        dogs_list = await parse_zooportal_search_page(page_num)

        if not dogs_list:
            return {
                "status": "success",
                "page": page_num,
                "processed_dogs": 0,
                "message": "No dogs found"
            }

        # 2. Ограничиваем количество собак для обработки
        dogs_to_process = dogs_list[:max_dogs]

        processed_dogs = []
        failed_dogs = []

        # 3. Используем единую сессию для всех собак на странице
        async with session_scope() as session:
            # 4. Обрабатываем каждую собаку
            for i, dog_data in enumerate(dogs_to_process):
                try:
                    dog_id = dog_data['dog_id']
                    dog_name = dog_data['registered_name']

                    logger.info(f"[{i + 1}/{len(dogs_to_process)}] Processing dog {dog_id}: {dog_name}")

                    # или тут проверять существование в бд и рекурсивно по предкам проходиться с ссылками или
                    # не проверять и пройтись по каждой собаке

                    # Обрабатываем собаку с предками
                    dog = await process_zooportal_dog_with_ancestors(
                        dog_id=dog_id,
                        # max_generations=3,
                        session=session
                    )

                    if dog:
                        processed_dogs.append({
                            # zooportal_id
                            'dog_id': dog_id,
                            # id in DB
                            'dog_db_id': dog.id,
                            'name': dog.registered_name,
                            'source': dog.source,
                            'status': 'processed'
                        })
                    else:
                        failed_dogs.append({
                            'dog_id': dog_id,
                            'name': dog_name,
                            'error': 'Failed to process'
                        })

                    # Задержка между обработкой собак
                    if i < len(dogs_to_process) - 1 and delay_between_dogs > 0:
                        await asyncio.sleep(delay_between_dogs)

                except Exception as e:
                    logger.error(f"Error processing dog {dog_data.get('dog_id')}: {e}")
                    failed_dogs.append({
                        'dog_id': dog_data.get('dog_id', 'unknown'),
                        'name': dog_data.get('registered_name', 'unknown'),
                        'error': str(e)
                    })

            # 5. Сохраняем все изменения
            await session.commit()

        return {
            "status": "success",
            "page": page_num,
            "total_found": len(dogs_list),
            "processed": len(processed_dogs),
            "failed": len(failed_dogs),
            "processed_dogs": processed_dogs,
            "failed_dogs": failed_dogs
        }

    except Exception as e:
        logger.error(f"Error processing Zooportal search page {page_num}: {e}")
        return {
            "status": "error",
            "page": page_num,
            "error": str(e)
        }


async def find_dog_by_zooportal_id(zooportal_id: str, session: AsyncSession) -> Dog | None:

    result = await session.execute(
        select(Dog).where(Dog.zooportal_id == str(zooportal_id))
    )

    return result.scalars().first()


async def find_dog_by_zoo_hash(zoo_hash: str, session: AsyncSession) -> Dog | None:
    """
    Находит собаку по точному совпадению zoo_hash.

    Args:
        zoo_hash: SHA-256 хэш (64 символа)
        session: Асинхронная сессия базы данных

    Returns:
        Dog или None, если не найдено
    """
    try:
        if not zoo_hash or len(zoo_hash) != 64:
            logging.warning(f"Некорректный zoo_hash: {zoo_hash}")
            return None

        result = await session.execute(
            select(Dog).where(Dog.zoo_hash == zoo_hash)
        )
        dog = result.scalars().first()

        if dog:
            logging.debug(f"Найдена собака по zoo_hash: {zoo_hash}...")
        else:
            logging.debug(f"Собака с zoo_hash {zoo_hash}... не найдена")

        return dog

    except Exception as e:
        logging.error(f"Ошибка при поиске собаки по zoo_hash {zoo_hash}: {e}")
        return None

# TODO: добавить колонку для ссылки на странциу владельцев (+доп инфа с их страницы, +зоопртал айди с их аккаунта)
async def save_owner_and_breeder(dog: Dog, dog_data: Dict[str, Any], session: AsyncSession) -> None:
    """
    Сохраняет владельца и заводчика и устанавливает связи.
    Питомник уже сохранен в Dog.kennel как строка.
    """

    if dog is None:
        return

    # 1. Обработка владельца
    owner_name = dog_data.get('owner_name')
    owner_url = dog_data.get('owner_url') or ""
    owner_kennel_url = dog_data.get('owner_kennel_url') or ""
    owner_kennel = dog_data.get('owner_kennel') or ""

    if owner_name:
        # Генерация UUID для владельца
        owner_uuid = create_uuid_from_str(owner_name)

        # Проверяем существование
        owner_query = select(Owner).where(Owner.uuid == owner_uuid)
        owner_result = await session.execute(owner_query)
        owner = owner_result.scalars().first()


        if not owner:
            # Создаем нового владельца
            owner = Owner(
                uuid=owner_uuid,
                name=owner_name,
                owner_url=owner_url,
                kennel=owner_kennel,
                kennel_url=owner_kennel_url,
                is_main_owner=True,
            )
            session.add(owner)
            await session.flush()
        # logger.info(f"--------------------------- owner: {owner}")

        # Создаем связь собака-владелец
        link_exists = await session.execute(
            select(DogOwnerLink).where(
                DogOwnerLink.dog_id == dog.id,
                DogOwnerLink.owner_id == owner.id
            )
        )
        if not link_exists.scalar_one_or_none():
            session.add(DogOwnerLink(dog_id=dog.id, owner_id=owner.id))

    # 2. Обработка заводчика
    breeder_name = dog_data.get('breeder_name')
    breeder_url = dog_data.get('breeder_url') or ""
    breeder_kennel_url = dog_data.get('breeder_kennel_url') or ""
    breeder_kennel = dog_data.get('breeder_kennel') or ""

    if breeder_name:
        breeder_uuid = create_uuid_from_str(breeder_name)

        breeder_query = select(Breeder).where(Breeder.uuid == breeder_uuid)
        breeder_result = await session.execute(breeder_query)
        breeder = breeder_result.scalars().first()

        if not breeder:
            breeder = Breeder(
                uuid=breeder_uuid,
                name=breeder_name,
                breeder_url=breeder_url,
                kennel=breeder_kennel,
                kennel_url=breeder_kennel_url,
                is_breeder=True,
            )
            session.add(breeder)
            await session.flush()

        # Создаем связь собака-заводчик
        link_exists = await session.execute(
            select(DogBreederLink).where(
                DogBreederLink.dog_id == dog.id,
                DogBreederLink.breeder_id == breeder.id
            )
        )
        if not link_exists.scalar_one_or_none():
            session.add(DogBreederLink(dog_id=dog.id, breeder_id=breeder.id))

    await session.flush()

# RU CH, UA CH, AZ CH, CY CH, ME CH
async def save_dog_titles(dog: Dog, dog_data: Dict[str, Any], session: AsyncSession) -> None:
    """
    Сохраняет титулы собаки и устанавливает связи.
    """
    # Получаем титулы из данных

    if dog is None:
        return

    titles_list = dog_data.get('titles', [])
    # logger.info(f"++++++++++++++++++++++++++ titles_list:  {titles_list}")

    if not titles_list:
        # logger.info(f"У собаки {dog.id} нет титулов для сохранения")
        return

    # logger.info(f"Сохранение {len(titles_list)} титулов для собаки {dog.id}")

    for title_info in titles_list:
        try:
            # Получаем данные титула
            short_name = title_info.get('short_name', '').strip()
            long_name = title_info.get('long_name', '').strip()
            raw_text = title_info.get('raw_text', '').strip()

            if not short_name:
                # Пробуем получить short_name из raw_text
                short_name = raw_text[:50] if raw_text else "UNKNOWN"

            if not long_name:
                long_name = raw_text if raw_text else short_name

            # Проверяем, существует ли уже такой титул у собаки
            title_query = select(Title).where(
                Title.dog_id == dog.id,
                Title.short_name == short_name
            )
            title_result = await session.execute(title_query)
            existing_title = title_result.scalars().first()

            if not existing_title:
                # Создаем новый титул
                title = Title(
                    dog_id=dog.id,
                    short_name=short_name,
                    long_name=long_name,
                    is_prefix=title_info.get('is_prefix', False),
                    has_winner_year=title_info.get('has_winner_year', False),
                    winner_year=title_info.get('winner_year'),
                    country=title_info.get('country')
                )
                session.add(title)
                # logger.debug(f"Добавлен новый титул для собаки {dog.id}: {short_name}")
            else:
                # Обновляем существующий титул
                update_needed = False

                if existing_title.long_name != long_name:
                    existing_title.long_name = long_name
                    update_needed = True

                if existing_title.raw_text != raw_text:
                    existing_title.raw_text = raw_text
                    update_needed = True

                if existing_title.is_prefix != title_info.get('is_prefix', False):
                    existing_title.is_prefix = title_info.get('is_prefix', False)
                    update_needed = True

                if update_needed:
                    logger.debug(f"Обновлен титул для собаки {dog.id}: {short_name}")

        except Exception as e:
            logger.warning(f"Ошибка при сохранении титула '{title_info.get('short_name')}' для собаки {dog.id}: {e}")
            continue

    await session.flush()
    # logger.info(f"Титулы успешно сохранены для собаки {dog.id}")