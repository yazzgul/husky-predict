import asyncio
import hashlib
import logging
import re
from datetime import datetime
from typing import Dict, Optional, Union, Any, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from models import Title
from parsers.zooportal import (
    parse_zooportal_search_page,
    parse_zooportal_dog_page, normalize_zooportal_basic
)
from parsers.breedarchive import fetch_breedarchive_basic_info, normalize_breedarchive_basic

from models.dog import Dog
from models.people import Breeder, Owner
from models.associations import DogBreederLink, DogOwnerLink
from utils.dog_matcher import merge_dog_data, detect_dict_conflicts
from core.database import session_scope
from utils.parser_utils import parse_int, parse_datetime, parse_coi, parse_float, parse_titles_from_text

from utils.memory_cache import get_dog_data_from_cache, _dog_db_cache, _dog_db_cache_expiry
from utils.memory_cache import get_dog_db_cache, set_dog_db_cache
import time
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


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

def create_uuid_from_dict(data: Dict[str, Any], source: str) -> str:
    """
    Генерирует стабильный UUID на основе источника данных.
    ПРИОРИТЕТЫ:
    1. BreedArchive UUID (если есть)
    2. Zooportal UUID на основе zooportal_id (если есть)
    3. Универсальный UUID на основе имени, пола, source
    """
    # 1. Если это BreedArchive и есть UUID из BA
    if source == "breedarchive.com" and data.get("uuid"):
        return data["uuid"]

    # 2. Если есть zooportal_id
    if source == "zooportal.pro" and data.get("zooportal_id"):
        zooportal_id = str(data.get("zooportal_id", "")).strip()
        if zooportal_id and zooportal_id != "0":
            return hashlib.md5(f"zooportal_{zooportal_id}".encode()).hexdigest()

    # 3. Если есть hash из zoo_hash
    if data.get("zoo_hash"):
        return data["zoo_hash"]  # zoo_hash уже hex-строка

    # 4. Универсальный fallback
    name = data.get("registered_name", "").strip()
    sex = data.get("sex", 0)

    base_string = f"{name}|{sex}|{source}"
    return hashlib.md5(base_string.encode()).hexdigest()


async def process_ancestor_from_zooportal(
    session: AsyncSession,
    ancestor_data: Dict[str, Any],
    *,
    current_dog_id: Optional[str] = None,
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


        dog_hash = generate_zoo_hash(ancestor_data)
        existingDog = await find_dog_cached(session, zoo_hash=dog_hash)
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
                    try:
                        await save_update_dog_titles(new_dog, basic_data, session)
                    except Exception as e:
                        logger.error(f"Error processing breedarchive dog`s titles by uuid: {breedarchive_uuid}: {e}")

                    if cache_by_name is not None and getattr(new_dog, "id", None):
                        cache_by_name[cache_key] = new_dog.id
                    return new_dog
            except Exception as e:
                logger.error(f"Error processing BreedArchive ancestor {ancestor_name}: {e}")
                raise


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
        raise
        return None


# Главный метод, используемый в роутере
async def process_zooportal_dog_with_ancestors(
        dog_id: str,
        max_generations: int = 3,
        session: AsyncSession = None
) -> Optional[Dog]:
    """Основная функция обработки собаки с предками из Zooportal"""
    try:

        # 1. Проверяем кэш собаки
        cached_dog_data = await get_dog_data_from_cache(dog_id, "zooportal")

        if cached_dog_data and cached_dog_data.get('has_details', False):
            logger.info(f"Данные собаки {dog_id} из кэша, пропускаем парсинг")
            dog_data = cached_dog_data['data']
        else:
            # 2. Парсим данные с Zooportal (автоматически кэшируется в zooportal.py)
            logger.info(f"Парсинг собаки {dog_id} из Zooportal")
            dog_data = await parse_zooportal_dog_page(dog_id, max_generations)

        dog_info = dog_data['dog_info']
        pedigree = dog_data['pedigree']
        dog_name = dog_info.get('registered_name', '').strip()
        basic_data = None
        # 3. Ищем в БД (с кэшированием)
        dog_hash = generate_zoo_hash(dog_info)
        existingDog = await find_dog_cached(session, zoo_hash=dog_hash, zooportal_id=dog_id)

        if existingDog:
            logger.info(f"Dog with Zooportal_ID {dog_id} already exists, using existing record")
            dog = existingDog

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
                            # session.add(dog)
                            await session.flush()
                            # Сохранение титулов из бридарчив
                            dogTitles = parse_titles_from_text(
                                basic_data.get('prefix_titles') or basic_data.get('prefixTitles'), "breedarchive")
                            basic_data["titles"] = dogTitles
                            try:
                                await save_update_dog_titles(dog, basic_data, session)
                            except Exception as e:
                                logger.error(
                                    f"Error processing breedarchive dog`s titles by uuid: {breedarchive_uuid}: {e}")
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
                        try:
                            await save_update_dog_titles(dog, basic_data, session)
                        except Exception as e:
                            logger.error(f"Error processing breedarchive dog`s titles by uuid: {breedarchive_uuid}: {e}")
                except Exception as e:
                    logger.error(f"Error processing breedarchive dog by uuid: {breedarchive_uuid}: {e}")
                    raise

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
                    # await session.rollback()
                    dog = None
                    raise

        try:
            await save_owner_and_breeder(dog, dog_info, session)
        except Exception as e:
            logger.warning(f"Не удалось сохранить связи для собаки с owner, breeder. Dog_id: {dog.id} , Dog_name: ({dog.registered_name}): {e}")
            logger.debug(f"Ошибка детально:", exc_info=True)

        try:
            # Сохранение титулов из зоопортал
            await save_update_dog_titles(dog, dog_info, session)
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
                    node_to_dog_id[base_key] = base_dog.id

            # 7.2. Обрабатываем всех предков из таблицы (каждый предок = отдельная запись Dog)
            for node_key, ancestor_data in (pedigree.get('ancestors') or {}).items():
                try:
                    ancestor_dog = await process_ancestor_from_zooportal(
                        session,
                        ancestor_data,
                        # cache_by_key=cache_by_key,
                        current_dog_id=dog_id,
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

# Старая (временная) функция
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
    # pedigree = parsed_data['pedigree']  # для ensure не обязателен

    # Убедимся, что имя не пустое
    dog_name = dog_info.get('registered_name', '').strip()

    # 2. Ищем в БД, если есть
    # existingDog = await find_dog_by_zooportal_id(str(child_zoo_id), session)
    dog_hash = generate_zoo_hash(dog_info)
    # existingDog = await find_dog_by_zoo_hash(dog_hash, session)
    existingDog = await find_dog_cached(session, zoo_hash=dog_hash)
    if existingDog:
        logger.info(f"Dog with Zooportal_ID {child_zoo_id} already exists, using existing record")
        dog = existingDog

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


                # Получаем базовую информацию (если ещё не получили)
                if not breedarchive_basic_info:
                    basic_data = await fetch_breedarchive_basic_info(breedarchive_uuid)
                else:
                    basic_data = breedarchive_basic_info


                res = await session.execute(
                    select(Dog).where(Dog.uuid == breedarchive_uuid))
                existingBreedarchiveDogInDB = res.scalars().first()

                if existingBreedarchiveDogInDB:
                    dog = existingBreedarchiveDogInDB
                    logger.info(f"Found in DB with BreedArchive UUID: {breedarchive_uuid}")
                    if basic_data:
                        has_changes, conflicts = merge_dog_data(dog, basic_data, "zooportal.pro")
                        if has_changes:
                            # session.add(dog)
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
                # await session.rollback()
                dog = None
                raise


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


    # Парсинг incomplete_pedigree
    incomplete_pedigree = False
    incomplete_raw = raw.get("incomplete_pedigree")
    if isinstance(incomplete_raw, bool):
        incomplete_pedigree = incomplete_raw
    elif isinstance(incomplete_raw, str):
        incomplete_pedigree = incomplete_raw.lower() in ['true', '1', 'yes', 't']

    # Получаем и валидируем UUID
    uuid_value = create_uuid_from_dict(data=raw, source=source)
    if not uuid_value or uuid_value == "0" * 64:  # Все нули
        # Аварийная генерация с временной меткой
        timestamp = int(time.time() * 1000)
        uuid_value = hashlib.md5(f"emergency_{timestamp}".encode()).hexdigest()

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
        max_dogs: int = 11,
        delay_between_dogs: float = 2.0
) -> Dict:
    """Обрабатывает страницу поиска на Zooportal и сохраняет собак так,
    чтобы ошибка одной собаки НЕ откатывала остальных.
    """
    try:
        logger.info(f"Processing Zooportal search page {page_num}")
        dogs_list = await parse_zooportal_search_page(page_num)

        if not dogs_list:
            return {
                "status": "success",
                "page": page_num,
                "processed_dogs": 0,
                "message": "No dogs found"
            }

        dogs_to_process = dogs_list[:max_dogs]
        processed_dogs = []
        failed_dogs = []

        async with session_scope() as session:
            for i, dog_data in enumerate(dogs_to_process):
                dog_id = dog_data.get("dog_id")
                dog_name = dog_data.get("registered_name")

                logger.info(f"*** [{i + 1}/{len(dogs_to_process)}] Processing dog {dog_id}: {dog_name}")

                try:
                    dog = await process_zooportal_dog_with_ancestors(
                        dog_id=str(dog_id),
                        session=session
                    )

                    if not dog:
                        failed_dogs.append({
                            "dog_id": dog_id,
                            "name": dog_name,
                            "error": "Failed to process (returned None)"
                        })
                        # IMPORTANT: откатим всё, что могло частично набраться
                        await session.rollback()
                        continue

                    # ВАЖНО: фиксируем результаты этой собаки отдельным коммитом
                    await session.commit()

                    processed_dogs.append({
                        "dog_id": dog_id,
                        "dog_db_id": dog.id,
                        "name": dog.registered_name,
                        "source": dog.source,
                        "status": "processed"
                    })

                except IntegrityError as e:
                    # Сессия после IntegrityError "сломана" пока не rollback
                    await session.rollback()
                    logger.error(f"IntegrityError processing dog {dog_id}: {e}", exc_info=True)
                    failed_dogs.append({
                        "dog_id": dog_id,
                        "name": dog_name,
                        "error": f"IntegrityError: {str(e)}"
                    })

                except Exception as e:
                    await session.rollback()
                    logger.error(f"Error processing dog {dog_id}: {e}", exc_info=True)
                    failed_dogs.append({
                        "dog_id": dog_id,
                        "name": dog_name,
                        "error": str(e)
                    })

                if i < len(dogs_to_process) - 1 and delay_between_dogs > 0:
                    await asyncio.sleep(delay_between_dogs)

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
        logger.error(f"Error processing Zooportal search page {page_num}: {e}", exc_info=True)
        return {"status": "error", "page": page_num, "error": str(e)}


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


def normalize_title_fields(short_name: str, long_name: str, country: str) -> tuple:
    """
    Нормализует поля титула к нижнему регистру и обрезает пробелы.
    Возвращает кортеж (short_name_lower, long_name_clean, country_lower)
    """
    # Нормализация short_name
    short_name_clean = str(short_name).strip() if short_name is not None else ""
    short_name_lower = short_name_clean.lower()

    # Нормализация long_name
    long_name_clean = str(long_name).strip() if long_name is not None else ""
    if not long_name_clean and short_name_clean:
        long_name_clean = short_name_clean  # fallback

    # Нормализация country
    country_clean = str(country).strip() if country is not None else ""
    if not country_clean:
        country_clean = "unknown"
    country_lower = country_clean.lower()

    return short_name_lower, long_name_clean, country_lower


async def save_update_dog_titles(dog: Dog, dog_data: Dict[str, Any], session: AsyncSession) -> None:
    """
    Сохраняет титулы собаки с нормализацией регистра и UPSERT логикой.
    """
    if dog is None:
        return

    titles_list = dog_data.get('titles', [])
    if not titles_list:
        logger.debug(f"У собаки {dog.id} ({dog.registered_name}) нет титулов для сохранения")
        return

    # logger.info(f"Сохранение {len(titles_list)} титулов для собаки {dog.id} ({dog.registered_name})")

    successful_titles = 0
    failed_titles = 0

    for title_info in titles_list:
        try:
            # Безопасное извлечение данных с защитой от None
            short_name_raw = title_info.get('short_name')
            long_name_raw = title_info.get('long_name')
            country_raw = title_info.get('country')

            # Нормализация полей
            short_name_lower, long_name_clean, country_lower = normalize_title_fields(
                short_name=short_name_raw,
                long_name=long_name_raw,
                country=country_raw
            )

            # Пропускаем титулы без короткого имени
            if not short_name_lower:
                # logger.warning(f"Пустой short_name в титуле для собаки {dog.id}, пропускаем")
                failed_titles += 1
                continue

            # Дополнительные поля с безопасным извлечением
            raw_text = str(title_info.get('raw_text', '')).strip() if title_info.get('raw_text') is not None else ""

            # Парсинг boolean полей с защитой
            is_prefix = False
            is_prefix_raw = title_info.get('is_prefix')
            if isinstance(is_prefix_raw, bool):
                is_prefix = is_prefix_raw
            elif isinstance(is_prefix_raw, (str, int)):
                is_prefix = str(is_prefix_raw).lower() in ['true', '1', 'yes', 't']

            has_winner_year = False
            has_winner_year_raw = title_info.get('has_winner_year')
            if isinstance(has_winner_year_raw, bool):
                has_winner_year = has_winner_year_raw
            elif isinstance(has_winner_year_raw, (str, int)):
                has_winner_year = str(has_winner_year_raw).lower() in ['true', '1', 'yes', 't']

            # Получаем winner_year
            winner_year = None
            winner_year_raw = title_info.get('winner_year')
            if winner_year_raw is not None:
                try:
                    winner_year = int(winner_year_raw)
                except (ValueError, TypeError):
                    pass  # Оставляем None если не удалось преобразовать

            # Подготовка данных для UPSERT
            current_time = datetime.now()
            title_data = {
                'dog_id': dog.id,
                'short_name': short_name_lower,  # Сохраняем в нижнем регистре
                'long_name': long_name_clean[:500] if long_name_clean else None,  # Ограничиваем длину
                'country': country_lower,  # Сохраняем в нижнем регистре
                'is_prefix': is_prefix,
                'has_winner_year': has_winner_year,
                'winner_year': winner_year,
            }

            # Используем INSERT ... ON CONFLICT DO UPDATE (UPSERT)
            stmt = insert(Title).values(**title_data)

            # Определяем, какие поля обновлять при конфликте
            update_dict = {
                'long_name': title_data['long_name'],
                'is_prefix': title_data['is_prefix'],
                'has_winner_year': title_data['has_winner_year'],
                'winner_year': title_data['winner_year'],
            }

            # Убираем None значения из update_dict (кроме winner_year)
            update_dict = {k: v for k, v in update_dict.items()
                           if k == 'winner_year' or v is not None}

            # Выполняем UPSERT
            stmt = stmt.on_conflict_do_update(
                index_elements=['dog_id', 'short_name', 'country'],
                set_=update_dict
            )

            await session.execute(stmt)
            successful_titles += 1

            # logger.debug(f"Титул сохранен: собака={dog.id}, short={short_name_lower}, country={country_lower}")

        except Exception as e:
            failed_titles += 1
            logger.warning(
                f"Ошибка при сохранении титула для собаки {dog.id}: {e}\n"
                f"Данные титула: {title_info}"
            )
            # Продолжаем обработку остальных титулов

    # Выполняем один flush в конце
    try:
        await session.flush()
    except Exception as e:
        logger.error(f"Ошибка при flush титулов для собаки {dog.id}: {e}")
        raise

    logger.info(f"Титулы сохранены для собаки {dog.id}: "
                f"успешно {successful_titles}, с ошибками {failed_titles}")


async def find_dog_cached(session: AsyncSession, zoo_hash: str = None, zooportal_id: str = None, check_session: bool = True) -> Optional[Dog]:
    """Поиск собаки в БД с кэшированием"""
    cache_key = None

    if zoo_hash:
        cache_key = f"db_zoo_hash:{zoo_hash}"
    elif zooportal_id:
        cache_key = f"db_zooportal_id:{zooportal_id}"

    # if cache_key:
    #     # Проверяем кэш БД
    #     cached_dog_id = get_dog_db_cache(cache_key)
    #     if cached_dog_id:
    #         dog = await session.get(Dog, cached_dog_id)
    #         if dog:
    #             return dog

    if cache_key:
        # Проверяем кэш БД
        cached_dog_id = get_dog_db_cache(cache_key)
        if cached_dog_id:
            # ВАЖНОЕ ИЗМЕНЕНИЕ: используем select вместо get() (чтобы, если транзакция собаки с предками откатилась, не получать ошибку)
            result = await session.execute(
                select(Dog).where(Dog.id == cached_dog_id)
            )
            dog = result.scalars().first()
            if dog:
                return dog
            else:
                # Если ID из кэша не найден в БД - очищаем кэш
                logger.debug(f"Невалидный кэш для ключа {cache_key}, dog_id={cached_dog_id}")
                # Дополнительно можем очистить кэш:
                _dog_db_cache.pop(cache_key, None)
                if hasattr(_dog_db_cache_expiry, 'pop'):
                    _dog_db_cache_expiry.pop(cache_key, None)

    # Ищем в session
    if check_session:
        # Смотрим все "новые" собаки в сессии
        for obj in session.new:  # Объекты добавленные через add()
            if isinstance(obj, Dog):
                if zoo_hash and obj.zoo_hash == zoo_hash:
                    return obj
                elif zooportal_id and obj.zooportal_id == zooportal_id:
                    return obj

        # Смотрим все "грязные" (измененные) собаки
        for obj in session.dirty:
            if isinstance(obj, Dog):
                if zoo_hash and obj.zoo_hash == zoo_hash:
                    return obj
                elif zooportal_id and obj.zooportal_id == zooportal_id:
                    return obj


    # Ищем в БД
    if zoo_hash:
        result = await session.execute(
            select(Dog).where(Dog.zoo_hash == zoo_hash)
        )
        dog = result.scalars().first()
    elif zooportal_id:
        result = await session.execute(
            select(Dog).where(Dog.zooportal_id == zooportal_id)
        )
        dog = result.scalars().first()
    else:
        return None

    # Сохраняем в кэш БД
    if dog and cache_key:
        set_dog_db_cache(cache_key, dog.id, ttl=3600)  # 60 минут

    return dog


def get_integration_cache_stats() -> Dict[str, Any]:
    """Получить статистику кэша интеграции"""
    from utils.memory_cache import _dog_db_cache, _dog_data_cache

    return {
        "dog_db_cache_size": len(_dog_db_cache),
        "dog_data_cache_size": len(_dog_data_cache),
        "dog_db_cache_keys": list(_dog_db_cache.keys())[:10] if _dog_db_cache else [],
        "dog_data_cache_keys": list(_dog_data_cache.keys())[:10] if _dog_data_cache else []
    }