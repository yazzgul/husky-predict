import httpx
import logging
import asyncio
import sys
import random
import json
import re

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, List, Set, Dict, Any
from datetime import datetime, timedelta
from fastapi import HTTPException

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import playwright
from playwright.async_api import async_playwright
import tracemalloc

from core.database import session_scope
from core.config import settings
from core.parsersConfig import BREEDARCHIVE_API, BREEDARCHIVE_DOG_PATH, DELAY_RANGE, HEADERS, MAX_RETRIES
from utils.parser_utils import  get_photo_url, parse_coi, parse_datetime, parse_float, parse_int, parse_date
from models import Dog, Breeder, Owner, Title, Litter, DogBreederLink, DogOwnerLink, DogSiblingLink
from utils.dog_matcher import find_existing_dog, detect_conflicts, merge_dog_data

tracemalloc.start()
logger = logging.getLogger(__name__)

# Проверка дампа HTML файла
# HTML_DUMP_DIR = "html_dumps"
# os.makedirs(HTML_DUMP_DIR, exist_ok=True)

# Для Windows требуется установка event loop policy
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

                
async def get_dog_by_uuid(uuid: str, session: AsyncSession) -> Optional[Dog]:
    result = await session.execute(
        select(Dog)
        .where(Dog.uuid == uuid)
        .options(selectinload('*'))  # Жадная загрузка всех отношений
        .with_for_update()
    )
    return result.scalars().first()

async def get_dog_id_by_uuid(uuid: Optional[str], session: AsyncSession) -> Optional[int]:
    if not uuid:
        return None
    
    result = await session.execute(
        select(Dog.id)
        .where(Dog.uuid == uuid)
    )
    
    return result.scalar_one_or_none()

async def fetch_recent_updates_dogs(session, isFullSync: bool = True, pagesCount: Optional[int] = None, startPage: Optional[int] = 0, isRefresh: bool = False) -> List:
    async with httpx.AsyncClient() as client:
        async with session.begin():
            try:
                start = startPage * 25
                parsed_dog_ids = []
                parsedRowsCounter = 0 # Счетчик количества обработанных строк
                available_pages = int((250 - startPage * 25) / 25)
                has_more = True
                
                logger.info(f'Start fetching recent updates data from BreedArchive API...')
                
                if(not isFullSync):            
                    logger.info(f'Start page: {startPage} \nPages to parse: {pagesCount} \nAvailable pages: {available_pages}')

                while True:
                    await asyncio.sleep(random.uniform(*DELAY_RANGE))
                    # Данный запрос только для новых данных / возвращает максимум 250 собак (самых новых по дате), с меткой is_new если новая запись, и без если просто обновились данные, т.е. макс start=225
                    url = f"{BREEDARCHIVE_API}/ng_animal/get_entries?operation=all&start={start}"
                    response = await client.get(url, headers=HEADERS)
                    data = response.json()
                    logger.info(f"response.json(): {data}")
                    # Обрабатываем каждое животное из списка
                    for animal in data["animals"]:
                        try:
                            # Используем данные из списка как основу
                            dog = await process_animal(client, session, animal, isRefresh)
                            logger.info(f"process_animal return: {dog}")
                            parsed_dog_ids.append(dog.id)
                        except Exception as e:
                            logger.error(f"Failed to process {animal['uuid']}: {str(e)}")

                    if not data.get("has_more", False) or (not isFullSync and start >= pagesCount * 25):
                        logger.info("No more dogs to fetch.")
                        break

                    start += 25

                await session.commit()
                logger.info(f"parsedDogs len: {len(parsed_dog_ids)}")
                return parsed_dog_ids
            except Exception as e:
                logger.error(f"Error then fetch list, start: {start}, pagesCount: {pagesCount}, isFullSync: {isFullSync} \n error: {str(e)}")
                await session.rollback()
                raise
            # finally:
            #     await session.close()

async def process_animal_with_new_session(client: httpx.AsyncClient, animal_data: Dict, isRefresh: bool) -> int:
    async with session_scope() as session:
        try:
            dog = await process_animal(client, session, animal_data, 6, isRefresh)
            await session.commit()

            return dog.id
        except Exception as e:
            logger.error(f"Failed to process {animal_data['uuid']}: {str(e)}")
            raise

async def process_animal(client: httpx.AsyncClient, session: AsyncSession, animal_data: Dict, maxDeep = 3, isRefresh: bool = False):
    try:
        uuid = animal_data.get("uuid")
        link_name = animal_data.get('link_name', 'unknown')  # значение по умолчанию

        if not uuid or not link_name:
            logger.error(f"Missing required data in animal_data: {animal_data}")
            return None

        # Запрашиваем детальные данные (предки + доп. поля)
        detailed_url = f"{BREEDARCHIVE_API}/animal/get_ancestors/{uuid}?generations=5"
        response = await client.get(detailed_url, headers=HEADERS)
        detailed_data = response.json()

        # Объединяем данные: приоритет у детальных данных, но сохраняем специфичные поля из списка
        merged_data = {
            **detailed_data,  # Основные данные из детального запроса
            **{k: v for k, v in animal_data.items() if k not in detailed_data},  # Уникальные поля из списка
            "modified_at": animal_data.get("modified_at"),  # Пример приоритетного поля из списка
            "is_new": animal_data.get("is_new")
        }

        # Создаем множество для отслеживания уже обработанных собак
        processed_uuids = set()

        dog = await process_dog_data(merged_data, session, processed_uuids, maxDeep)
        logger.info(f"Processed dog: {dog.registered_name}")

        # await session.refresh(dog, ["dam", "sire", "titles"])
        await session.refresh(dog)

        return dog

        # # Повторное открытие сессии для сериализации
        # async with session.begin():
        #     await session.refresh(dog, ["dam", "sire", "titles"])
        #     return dog
    except Exception as e:
        logger.error(f"Error processing (process_animal) {uuid}: {str(e)}")
        await session.rollback()
        raise

async def process_animal_by_uuid(uuid: str, maxDeep: int = 5) -> Dict:
    async with httpx.AsyncClient() as client:
        async with session_scope() as session:
        # async with session.begin():
            try:
                detailed_url = f"{BREEDARCHIVE_API}/animal/get_ancestors/{uuid}?generations=5"
                logger.info(f"Fetching data from: {detailed_url}")

                response = await client.get(detailed_url, headers=HEADERS)

                # Проверяем статус ответа
                if response.status_code != 200:
                    logger.error(f"API returned status {response.status_code} for UUID {uuid}")
                    raise HTTPException(status_code=response.status_code, detail=f"API returned status {response.status_code}")

                # Проверяем, что ответ не пустой
                if not response.text.strip():
                    logger.error(f"Empty response from API for UUID {uuid}")
                    raise HTTPException(status_code=404, detail="Empty response from API")

                try:
                    detailed_data = response.json()
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON response for UUID {uuid}: {response.text[:200]}...")
                    raise HTTPException(status_code=500, detail=f"Invalid JSON response: {str(e)}")

                # Проверяем, что получены данные
                if not detailed_data:
                    logger.error(f"No data received for UUID {uuid}")
                    raise HTTPException(status_code=404, detail="No data received from API")

                logger.info(f"Successfully fetched data for UUID {uuid}")

                processed_uuids = set()
                dog = await process_dog_data(detailed_data, session, processed_uuids, maxDeep)

                await session.refresh(dog, ["dam", "sire", "titles"])
                logger.info(f"process_animal_by_uuid() after refresh: {dog}")
                await session.commit()
                logger.info(f"process_animal_by_uuid() after commit: {dog.id}")
                return dog

            except HTTPException:
                # Перебрасываем HTTPException как есть
                raise
            except Exception as e:
                logger.error(f"Error processing {uuid}: {str(e)}")
                await session.rollback()
                raise HTTPException(status_code=500, detail=f"Error processing dog: {str(e)}")

@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError, playwright._impl._errors.Error)),
    reraise=True
)
async def parse_data_from_page_scripts(url):
    async with async_playwright() as pw:
        # Выбор браузера (chromium, firefox, webkit)
        browser =  await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu"
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        try:
            # Переход на страницу и ожидание загрузки
            await page.goto(url, wait_until="networkidle", timeout=60000)

            scripts = await page.evaluate("""() => {
                return Array.from(document.scripts)
                    .filter(s => s.innerHTML.includes('var animal ='))
                    .map(s => s.innerHTML)
            }""")

            animal_data = {
                "animal": {},
                "health": {
                    "breed_relevant": [],
                    "other_screenings": [],
                },
                "siblings": [],
                "litters": [],
            }

            for script in scripts:
                script_content = script.replace('\n', ' ')

                if "var animal =" in script_content:
                    matchAnimal = re.search(r"var animal\s*=\s*({.*?});", script, re.DOTALL)
                    if matchAnimal:
                        animal_data["animal"] = json.loads(matchAnimal.group(1))

                    matchHealthScreenings = re.search(r"var health_screenings\s*=\s*(\[.*?\]);", script, re.DOTALL)
                    if matchHealthScreenings:
                        animal_data["health"]["breed_relevant"] = json.loads(matchHealthScreenings.group(1))

                    matchAnimalHealthInfos = re.search(r"var animal_healthinfos\s*=\s*(\[.*?\]);", script, re.DOTALL)
                    if matchAnimalHealthInfos:
                        animal_data["health"]["other_screenings"] = json.loads(matchAnimalHealthInfos.group(1))

                    matchSiblings = re.search(r"var siblings\s*=\s*(\[.*?\]);", script, re.DOTALL)
                    if matchSiblings:
                        animal_data["siblings"] = json.loads(matchSiblings.group(1))

                    matchLitters = re.search(r"var litters\s*=\s*({.*?});", script, re.DOTALL)
                    if matchLitters:
                        animal_data["litters"] = json.loads(matchLitters.group(1))["litters"]

                    break

            return animal_data
        finally:
            await browser.close()

# Вспомогательная функция для обработки связанных собак
async def process_related_dog(related_data: Optional[Dict], session: AsyncSession, processed_uuids: Set[str], max_depth: int) -> Optional[Dog]:
    if not related_data or not related_data.get("uuid"):
        return None

    uuid = related_data.get('uuid')
    if uuid in processed_uuids:
        existing_dog, _, _ = await find_existing_dog(session, related_data, "breedarchive")
        return existing_dog

    logger.info(f"Processing related dog with uuid: {related_data.get('uuid')}")

    existing_dog, match_method, similarity = await find_existing_dog(
        session, related_data, "breedarchive"
    )

    if existing_dog and max_depth == 0:
        logger.info(f"Found existing dog by {match_method} (similarity: {similarity:.2f}): {existing_dog.registered_name}")
        return existing_dog

    if uuid in processed_uuids and not existing_dog:
        logger.warning(f"Circular reference detected for dog {uuid}. Skipping recursive processing.")
        return None

    # Рекурсивно обрабатываем собаку
    processed_uuids.add(uuid) # Добавляем UUID в список обрабатываемых
    return await process_dog_data(related_data, session, processed_uuids, max_depth)

async def clear_relationships(dog: Dog, session: AsyncSession):
    await session.execute(delete(DogBreederLink).where(DogBreederLink.dog_id == dog.id))
    await session.execute(delete(DogOwnerLink).where(DogOwnerLink.dog_id == dog.id))
    await session.execute(delete(DogSiblingLink).where(DogSiblingLink.dog_id == dog.id))
    await session.flush()
    logger.error("CLEAR RELAT")

async def process_relationships(dog: Dog, data: Dict, session: AsyncSession, processed_uuids: Set[str], max_depth: int):
    # Параллельная обработка всех связей
    # breeders, owners, titles, siblings, litters = await asyncio.gather(
    #     process_breeders(data.get("breeders", []), session),
    #     process_owners(data.get("owners", []), session),
    #     process_titles(data.get("titles", []), session, dog.id),
    #     process_siblings(data.get("siblings", []), session, processed_uuids, max_depth-1),
    #     process_litters(data.get("litters", []), session, processed_uuids, max_depth-1)
    # )

    logger.error("PROCESS_RELATIONSHIPS START")
    logger.error(f"breeders: {data.get('breeders', [])}")
    logger.error(f"owners: {data.get('owners', [])}")
    logger.error(f"titles: {data.get('titles', [])}")
    logger.error(f"siblings: {data.get('siblings', [])}")
    logger.error(f"litters: {data.get('litters', [])}")
    # await session.flush()  # Если необходимо
    logger.error(f"titles_data : {data.get('titles', [])}")

    breeders = [parse_breeder(b) for b in data.get("breeders", [])]
    owners = [parse_owner(o) for o in data.get("owners", [])]
    titles = [parse_title(t, dog.id) for t in data.get("titles", [])]
    siblings = data.get("siblings", [])
    litters = data.get("litters", [])

    logger.error(f"breeders: {breeders}")
    logger.error(f"owners: {owners}")
    logger.error(f"titles: {titles}")

    validated_breeders = await process_breeders(breeders, session)
    logger.error(f"validated_breeders: {validated_breeders}")

    validated_owners = await process_owners(owners, session)
    logger.error(f"validated_owners: {validated_owners}")

    validated_titles = await process_titles(titles, session, dog.id)
    session.add_all(validated_titles)
    await session.flush()

    logger.error(f"validated_titles: {validated_titles}")

    if len(validated_titles) > 0:
        # dog.titles = validated_titles
        await session.flush()
        await session.refresh(dog, attribute_names=["titles"], with_for_update=True)
    await clear_relationships(dog, session)
    logger.error("after clear_relationships")

    for breeder in validated_breeders:
        logger.info(f"Adding breeder: {breeder}")
        session.add(DogBreederLink(dog_id=dog.id, breeder_id=breeder.id))
    await session.flush()
    for owner in validated_owners:
        logger.info(f"Adding owner: {owner}")
        session.add(DogOwnerLink(dog_id=dog.id, owner_id=owner.id))

        logger.error("Assigning titles")
    await session.flush()

    logger.error("Assigned titles")

    validated_siblings = await process_siblings(siblings, session, processed_uuids)
    logger.error(f"validated_siblings: {validated_siblings}")
    for sibling in validated_siblings:
        logger.error(f"Adding sibling {sibling}")
        session.add(DogSiblingLink(dog_id=dog.id, sibling_id=sibling.id))
    await session.flush()
    logger.error(f"data.get('litters'), []: {data.get('litters', [])}")

    # validated_litters = await process_litters(litters, session, processed_uuids, max_depth)
    # logger.error(f"validated_litters: {validated_litters}")
    # "litters_as_dam", "litters_as_sire", "litters_as_mating_partner"
    await session.refresh(dog, ["breeders", "owners", "titles", "siblings"])
    await session.flush()
    logger.error("after session.refresh(dog): {dog}")

async def create_new_dog(dog_data: Dict, dam: Optional[Dog], sire: Optional[Dog], session: AsyncSession, processed_uuids: Set[str], max_depth: int) -> Dog:
    # Обработка связей
    try:
        # Проверяем существование родителей
        if dam and not dam.id:
            logger.error(f"Dam {dam.uuid} not persisted")
            # raise ValueError(f"Dam {dam.uuid} not persisted")

        if sire and not sire.id:
            logger.error(f"Sire {sire.uuid} not persisted")
            # raise ValueError(f"Sire {sire.uuid} not persisted")

        new_dog = parse_dog_data(dog_data, dam, sire)

        # logger.info(f"NEW Dog {new_dog.uuid} dam: {new_dog.dam} sire: {new_dog.sire}")

        session.add(new_dog)
        await session.flush()
        await session.refresh(new_dog)

        return new_dog

    except Exception as e:
        # await session.rollback()
        logger.error(f"Foreign key violation: {str(e)}")
        raise ValueError("Parent dogs must be processed first") from e

async def update_existing_dog(dog: Dog, new_data: Dict, dam: Optional[Dog], sire: Optional[Dog], session: AsyncSession, processed_uuids: Set[str], max_depth: int) -> Dog:
    #  Валидация родителей
    if dam and not await session.get(Dog, dam.id):
        raise ValueError(f"Dam with id {dam.id} does not exist")
    if sire and not await session.get(Dog, sire.id):
        raise ValueError(f"Sire with id {sire.id} does not exist")

    updatedDog = parse_dog_data(new_data, dam, sire)
    updatedDogDict = updatedDog.model_dump(exclude_unset=True)

    dog.sqlmodel_update(updatedDogDict)
    session.add(dog)
    await session.flush()

    # Обновление связей
    dog.dam_id = dam.id if dam else None
    dog.sire_id = sire.id if sire else None

    await session.flush()
    await session.refresh(dog)

    return dog

async def process_dog_data(dog_data: Dict[str, Any], session: AsyncSession, processed_uuids: Set[str], max_depth: int = 6) -> Optional[Dog]:
    try:
        if max_depth <= 0:
            logger.error("Max recursion depth reached")
            # raise ValueError("Max recursion depth reached")
            return None

        logger.info(f"Max_depth: {max_depth}, dog: {dog_data.get('uuid')}")
        if not dog_data:
            logger.error("Empty data")
            return None

        uuid = dog_data.get("uuid")
        if not uuid:
            logger.error("Dog data missing UUID")
            return None
        existing_dog, match_method, similarity = await find_existing_dog(
            session, dog_data, "breedarchive"
        )

        dam = await process_related_dog(dog_data.get("dam"), session, processed_uuids, max_depth - 1)
        sire = await process_related_dog(dog_data.get("sire"), session, processed_uuids, max_depth - 1)

        # Основная обработка собаки
        dog: Optional[Dog] = None

        # "breedarchive"
        # Парсим данные со страницы (которых нет в детальном запросе)
        parsed_data = {}

        # if max_depth > 1: # Для экономии запросов, парсим страницу только для основных собак (?)
        url = f"{BREEDARCHIVE_API}{BREEDARCHIVE_DOG_PATH}/{dog_data.get('link_name')}-{dog_data.get('uuid')}"
        parsed_data = await parse_data_from_page_scripts(url)

                # Объединяем данные
        full_data = {
            **dog_data,  # Основные данные из детального запроса
            **parsed_data.get("animal", {}),  # Данные из animal с приоритетом
            "health_info_general": parsed_data["health"]["breed_relevant"],
            "health_info_genetic": parsed_data["health"]["other_screenings"],
            "siblings": parsed_data.get("siblings", []),
            "litters": parsed_data.get("litters", []),
            "dam": dog_data.get("dam"),
            "sire": dog_data.get("sire"),
        }

        if existing_dog:
            logger.info(f"Found existing dog by {match_method} (similarity: {similarity:.2f}): {existing_dog.registered_name}")
            has_conflicts, conflicts = detect_conflicts(existing_dog, full_data, "breedarchive")

            if has_conflicts:
                logger.warning(f"Conflicts detected for dog {existing_dog.registered_name}: {conflicts}")
                existing_dog.has_conflicts = True
                if existing_dog.conflicts is None:
                    existing_dog.conflicts = {}
                for field, field_conflicts in conflicts.items():
                    if field not in existing_dog.conflicts:
                        existing_dog.conflicts[field] = {}
                    existing_dog.conflicts[field].update(field_conflicts)
            has_changes, _ = merge_dog_data(existing_dog, full_data, "breedarchive")

            if has_changes:
                await session.flush()
                logger.info(f"Updated existing dog {existing_dog.registered_name} with new data")

            dog = existing_dog
        else:
            # Если записи нет - создаем новую
            logger.info(f"Creating new dog {uuid}")
            dog = await create_new_dog(full_data, dam, sire, session, processed_uuids, max_depth)

        # await process_relationships(dog, dog_data, session, max_depth)

        await session.flush()

        return dog

    except Exception as e:
        logger.error(f"Error processing dog {dog_data.get('uuid')}: {str(e)}")
        return None

# Обработка связей
async def process_breeders(breeders: List[Breeder], session: AsyncSession):
    if len(breeders) == 0:
        return []

    processed_breeders = []
    for breeder in breeders:
        result = await session.execute(
            select(Breeder).where(Breeder.uuid == breeder.uuid)
        )
        existing_breeder = result.scalar_one_or_none()

        logger.error(f"existing Breeder: {existing_breeder}")

        if not existing_breeder:
            session.add(breeder)
            processed_breeders.append(breeder)
        else:
            update_dict = breeder.model_dump(exclude={"id", "uuid"})
            for key, value in update_dict.items():
                setattr(existing_breeder, key, value)
            processed_breeders.append(existing_breeder)

    await session.flush()

    for breeder in processed_breeders:
        await session.refresh(breeder)

    return processed_breeders

async def process_owners(owners: List[Owner], session: AsyncSession) -> List[Owner]:
    if len(owners) == 0:
        return []

    processed_owners = []
    for owner in owners:
        # Проверяем существование владельца по UUID
        result = await session.execute(
            select(Owner).where(Owner.uuid == owner.uuid)
        )
        existing_owner = result.scalars().first()

        if not existing_owner:
            # Создаем нового владельца
            session.add(owner)
            await session.flush()
            await session.refresh(owner)
            processed_owners.append(owner)
        else:
            # Обновляем поля существующего
            update_dict = owner.model_dump(exclude={"id", "uuid"})
            for key, value in update_dict.items():
                setattr(existing_owner, key, value)
            processed_owners.append(existing_owner)

    return processed_owners

async def process_titles(titles: List[Title], session: AsyncSession, dog_id: int) -> List[Title]:
    if len(titles) == 0:
        return []

    processed_titles = []
    for title in titles:
        logger.error(f"Обработка титула: {title}")
        # Для титулов используем комбинацию полей для идентификации
        logger.error(f"Значения для поиска: {title.dog_id}, {title.short_name}, {title.long_name}")

        result = await session.execute(
            select(Title).where(
                (Title.dog_id == title.dog_id) &
                (Title.short_name == title.short_name) &
                (Title.long_name == title.long_name)
            )
        )
        existing_title = result.scalar_one_or_none()

        if existing_title:
            existing_title.winner_year = title.winner_year
            existing_title.has_winner_year = title.has_winner_year
            logger.error(f"Изменения в титуле: {existing_title.dog_id}")
            await session.flush()
            await session.refresh(existing_title)
            processed_titles.append(existing_title)
        else:
            processed_titles.append(title)

    return processed_titles

async def process_siblings(siblings: List[Dict], session: AsyncSession, processed_uuids: Set[str]) -> List[Dog]:
    if len(siblings) == 0:
        return []

    processed_siblings = []
    if siblings:
        for sibling_data in siblings:
            sibling_uuid = sibling_data.get("uuid") if isinstance(sibling_data, dict) else sibling_data

            if sibling_uuid:
                sibling, _, _ = await find_existing_dog(session, sibling_data, "breedarchive")

                if sibling:
                    processed_siblings.append(sibling)
                elif sibling_uuid not in processed_uuids:
                    # Обрабатываем сиблинга как полноценную собаку
                    sibling = await process_related_dog(sibling_data, session, processed_uuids, 1)

                    if sibling:
                        processed_siblings.append(sibling)

    return processed_siblings

async def get_existing_litter(session: AsyncSession, attrs: dict) -> Optional[Litter]:
    query = select(Litter).where(
        (Litter.dam_id == attrs.get("dam_id")) &
        (Litter.sire_id == attrs.get("sire_id")) &
        (Litter.date_of_birth == attrs.get("date_of_birth"))
    )
    result = await session.execute(query)
    return result.scalars().first()

async def process_litter_parents(litter_data: dict, session: AsyncSession, processed_uuids: Set[str], max_depth: int):
    dam = await process_related_dog(litter_data.get("dam"), session, processed_uuids, max_depth)
    sire = await process_related_dog(litter_data.get("sire"), session, processed_uuids, max_depth)
    mating_partner = await process_related_dog(litter_data.get("mating_partner"), session, processed_uuids, max_depth)
    logger.error(f"process_litter_parents(): \n {dam}")
    return dam, sire, mating_partner

async def process_puppies(litter_data: dict, session: AsyncSession, processed_uuids: Set[str], max_depth: int) -> List[Dog]:
    logger.error(f"process_puppies(): \n {litter_data.get('offspring')}")
    logger.error(f"len(litter_data.get('offspring'))")
    if len(litter_data.get("offspring")) == 0:
        return []

    puppies = []
    for puppy_data in litter_data.get("offspring", []):
        if isinstance(puppy_data, dict) and "uuid" in puppy_data:
            puppy = await process_related_dog(puppy_data, session, processed_uuids, max_depth)
            if puppy:
                puppies.append(puppy)
    return puppies

async def process_litters(litters_data: List[Dict], session: AsyncSession, processed_uuids: Set[str], max_depth: int = 2) -> List[Litter]:
    if  len(litters_data) == 0:
        return []

    processed_litters = []
    logger.debug(f"Processing litters_data: {litters_data}")

    for litter_data in litters_data:
        if not litter_data:
            continue

        logger.debug(f"Processing litter {litter_data.get('date_of_birth')}, sire uuid: {litter_data.get('sire').get('uuid')}, dam uuid: {litter_data.get('dam').get('uuid')} : {litter_data}")

        litter_attrs = parse_litter(litter_data)

        logger.debug(f"Parsed litter attributes: {litter_attrs}")

        if not isinstance(litter_attrs, dict):
            logger.error(f"Invalid litter data format: {litter_attrs}")
            continue

        # Проверяем существование помета в базе
        existing_litter = await get_existing_litter(session, litter_attrs)
        dam, sire, mating_partner = await process_litter_parents(
            litter_data, session, processed_uuids, max_depth
        )
        logger.error(f"process_litter_parents() FINISH: \n {dam}, {sire}, {mating_partner}")

        litter_attrs.update({
            "dam_id": dam.id if dam else None,
            "sire_id": sire.id if sire else None,
            "mating_partner_id": mating_partner.id if mating_partner else None
        })

        logger.error(f"litter_attrs.update FINISH: \n {litter_attrs}")

        # Create/update litter
        litter = existing_litter or Litter(**litter_attrs)

        # if not existing_litter:
        #     session.add(litter)
        #     await session.flush()

        logger.error(f"existing_litter (?): {existing_litter}")
        logger.error(f"New litter (?): {litter}")
        if existing_litter:
            for key, value in litter_attrs.items():
                setattr(existing_litter, key, value)

            if puppies:
                setattr(existing_litter, "puppies", puppies)

            await session.flush()
            await session.refresh(litter)
        else:
            session.add(litter)
            await session.flush()
            await session.refresh(litter)


        puppies = await process_puppies(litter_data, session, processed_uuids, max_depth)
        logger.error(f"process_puppies() FINISH: \n {puppies}")
        logger.error(f"puppies len: {len(puppies)}")
        if puppies:
            # setattr(litter, "puppies", puppies)
            # litter.puppies = puppies
            await session.flush()
            await session.refresh(litter)
            logger.error(f"setattr(litter, \"puppies\", puppies): \n {puppies}")
            logger.error(litter)

        # await session.flush()
        # await session.refresh(litter)
        processed_litters.append(litter)

    return processed_litters

def parse_dog_data(raw: Dict[str, Any], dam: Dog, sire: Dog, source: str = "breedarchive") -> Dog:
    # Основные поля
    base_data = {
        "uuid": raw.get("uuid"),
        "registered_name": raw.get("registered_name"),
        "link_name": raw.get("link_name"),
        "call_name": raw.get("call_name"),

        "dam_uuid": raw.get("dam_uuid"),
        "dam_name": raw.get("dam_name"),
        "dam_link_name": raw.get("dam_link_name"),

        "sire_uuid": raw.get("sire_uuid"),
        "sire_name": raw.get("sire_name"),
        "sire_link_name": raw.get("sire_link_name"),

        "sex": raw.get("sex", 0),
        "year_of_birth": parse_int(raw.get("year_of_birth")),
        "month_of_birth": parse_int(raw.get("month_of_birth")),
        "day_of_birth": parse_int(raw.get("day_of_birth")),
        "date_of_birth": parse_date(raw.get("date_of_birth")),

        "year_of_death": parse_int(raw.get("year_of_death")),
        "month_of_death": parse_int(raw.get("month_of_birth")),
        "day_of_death": parse_int(raw.get("day_of_birth")),
        "date_of_death": parse_date(raw.get("date_of_death")),

        "land_of_birth": raw.get("land_of_birth"),
        "land_of_birth_code": raw.get("land_of_birth_code"),
        "land_of_standing": raw.get("land_of_standing"),

        "size": parse_float(raw.get("size")),
        "weight": parse_float(raw.get("weight")),
        "color": raw.get("color"),
        "color_marking": raw.get("color_marking"),
        "variety": raw.get("variety"),

        "distinguishing_features": raw.get("distinguishing_features"),
        "prefix_titles": raw.get("prefix_titles"),
        "suffix_titles": raw.get("suffix_titles"),
        "other_titles": raw.get("other_titles"),

        "registration_status": raw.get("registration_status"),
        "registration_number": re.sub(r"\s+", "",raw.get("registration_number")),

        "coi": parse_coi(raw.get("coi")),
        "coi_updated_on": parse_date(raw.get("date_of_birth")),
        "incomplete_pedigree": raw.get("incomplete_pedigree"),

        "photo_url": get_photo_url(raw),

        "locked": raw.get("locked"),
        "removed": raw.get("removed"),
        "show_ad": raw.get("show_ad"),
        "is_new": raw.get("is_new"),
        "modified": raw.get("modified"),
        "modified_at": parse_datetime(raw.get("modified_at")),

        "health_info_general": raw.get("health_info_general", []),
        "health_info_genetic": raw.get("health_info_genetic", []),
        "neutered": raw.get("neutered", False),
        "approved_for_breeding": raw.get("approved_for_breeding", False),
        "frozen_semen": raw.get("frozen_semen", False),
        "artificial_insemination": raw.get("artificial_insemination", False),

        "kennel": raw.get("kennel"),
        "notes": raw.get("notes"),
        "data_correctness_notes": raw.get("data_correctness_notes"),
        "club": raw.get("club"),
        "sports": raw.get("sports", []),

        # Source
        "source": source,
        "dam_id":  dam.id if dam else None,
        "sire_id":  sire.id if sire else None,
    }

    dog = Dog(**base_data)
    # logger.info(f"Dog to create: {dog}")

    return dog

# Вспомогательные функции парсинга
def parse_title(raw: Dict, dog_id: int) -> Title:
    return Title(
        title_id=raw["id"],
        short_name=raw["short_name"],
        long_name=raw["long_name"],
        is_prefix=raw["is_prefix"],
        has_winner_year=raw["has_winner_year"],
        winner_year=raw["winner_year"],
        dog_id=dog_id
    )

def parse_breeder(raw: Dict) -> Breeder:
    return Breeder(
        uuid=raw["uuid"],
        name=raw["name"],
        is_breeder=raw.get("is_breeder", False)
    )

def parse_owner(raw: Dict) -> Owner:
    return Owner(
        uuid=raw["uuid"],
        name=raw["name"],
        is_main_owner=raw.get("is_main_owner", False)
    )

def parse_litter(raw: Dict) -> dict:
    # Явная проверка типа
    if not isinstance(raw, dict):
        raise TypeError(f"Expected dict, got {type(raw)}")

    return {
        "date_of_birth": parse_date(raw.get("date_of_birth")),
        "litter_male_count": raw.get("litter_male_count", 0),
        "litter_female_count": raw.get("litter_female_count", 0),
        "litter_undef_count": raw.get("litter_undef_count", 0),
        "dam_id": raw.get("dam", {}).get("id") if isinstance(raw.get("dam"), dict) else None,
        "sire_id": raw.get("sire", {}).get("id") if isinstance(raw.get("sire"), dict) else None,
        "mating_partner_id": raw.get("mating_partner",{}).get("id") if isinstance(raw.get("mating_partner"), dict) else None,
    }

def parse_sibling(raw: Dict) -> Dog:
    return Dog(
        uuid=raw.get("uuid"),
        link_name=raw.get("link_name"),
        registered_name=raw.get("registered_name"),
        sex=raw.get("sex"),
        registration_status=raw.get("registration_status"),
        year_of_birth=parse_int(raw.get("year_of_birth")),
        land_of_birth=raw.get("land_of_birth"),
        color=raw.get("color"),
        variety=raw.get("variety"),
        photo_url=get_photo_url(raw),
        prefix_titles=raw.get("prefix_titles"),
        suffix_titles=raw.get("suffix_titles"),
        source="breedarchive",
    )

async def parse_breedarchive_browse_page(recent_days: int = 1) -> Dict[str, Any]:

    parsed_dog_ids = []
    failed_dogs = []
    total_processed = 0

    try:
        async with async_playwright() as pw:
            # Запускаем браузер
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-gpu"
                ]
            )

            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )

            page = await context.new_page()

            # Переходим на страницу списка собак
            browse_url = "https://siberianhusky.breedarchive.com/animal/browse"

            try:
                logger.info(f"Navigating to: {browse_url}")
                await page.goto(browse_url, wait_until='networkidle', timeout=60000)

                # Ждем загрузки контейнера со списком собак
                await page.wait_for_selector('[data-bind="foreach: animals, visible: animals().length > 0"]', timeout=10000)

                # Получаем текущую дату для сравнения
                current_date = datetime.now()
                cutoff_date = current_date - timedelta(days=recent_days)

                logger.info(f"Filtering dogs modified after: {cutoff_date}")

                has_more_data = True
                page_count = 0

                while has_more_data:
                    page_count += 1
                    logger.info(f"Processing page {page_count}")

                    # Ждем загрузки элементов списка
                    await page.wait_for_selector('.itemBox.fullProfile.resultProfile.profileDetails', timeout=10000)

                    # Получаем все элементы списка собак
                    dog_elements = await page.query_selector_all('.itemBox.fullProfile.resultProfile.profileDetails')

                    logger.info(f"Found {len(dog_elements)} dogs on current page")

                    should_stop = False

                    for i, dog_element in enumerate(dog_elements):
                        try:
                            # Извлекаем данные о собаке
                            dog_data = await extract_dog_data_from_element(page, dog_element)

                            if not dog_data:
                                continue

                            # Проверяем дату модификации
                            modified_date_str = dog_data.get('modified_at', '')
                            if modified_date_str:
                                try:
                                    # Парсим дату в формате "22/6/2025, 20:24"
                                    modified_date = datetime.strptime(modified_date_str, "%d/%m/%Y, %H:%M")

                                    if modified_date < cutoff_date:
                                        logger.info(f"Stopping at dog {dog_data.get('registered_name', 'Unknown')} - modified date {modified_date} is older than cutoff {cutoff_date}")
                                        should_stop = True
                                        break

                                except ValueError as e:
                                    logger.warning(f"Could not parse date '{modified_date_str}': {e}")

                            # Обрабатываем собаку
                            logger.info(f"Processing dog: {dog_data.get('registered_name', 'Unknown')}")

                            try:
                                # Создаем HTTP клиент для API запросов
                                async with httpx.AsyncClient() as client:
                                    # Получаем детальные данные через API
                                    uuid = dog_data.get('uuid')
                                    if uuid:
                                        detailed_url = f"{BREEDARCHIVE_API}/animal/get_ancestors/{uuid}?generations=5"
                                        response = await client.get(detailed_url, headers=HEADERS)
                                        detailed_data = response.json()

                                        # Объединяем данные
                                        merged_data = {
                                            **detailed_data,
                                            **{k: v for k, v in dog_data.items() if k not in detailed_data},
                                            "modified_at": dog_data.get("modified_at"),
                                            "is_new": dog_data.get("is_new")
                                        }

                                        # Обрабатываем собаку
                                        dog_id = await process_animal_with_new_session(client, merged_data, False)
                                        if dog_id:
                                            parsed_dog_ids.append(dog_id)
                                            logger.info(f"Successfully processed dog {dog_data.get('registered_name', 'Unknown')} with ID: {dog_id}")
                                        else:
                                            failed_dogs.append({
                                                'name': dog_data.get('registered_name', 'Unknown'),
                                                'uuid': uuid,
                                                'error': 'Failed to save dog'
                                            })
                                            logger.warning(f"Failed to save dog {dog_data.get('registered_name', 'Unknown')}")
                                    else:
                                        failed_dogs.append({
                                            'name': dog_data.get('registered_name', 'Unknown'),
                                            'error': 'No UUID found'
                                        })
                                        logger.warning(f"No UUID found for dog {dog_data.get('registered_name', 'Unknown')}")

                            except Exception as e:
                                failed_dogs.append({
                                    'name': dog_data.get('registered_name', 'Unknown'),
                                    'uuid': dog_data.get('uuid'),
                                    'error': str(e)
                                })
                                logger.error(f"Error processing dog {dog_data.get('registered_name', 'Unknown')}: {str(e)}")

                            total_processed += 1

                            # Небольшая задержка между обработкой собак
                            await asyncio.sleep(random.uniform(0.5, 1.5))

                        except Exception as e:
                            logger.error(f"Error extracting data from dog element {i}: {str(e)}")
                            continue

                    if should_stop:
                        logger.info("Reached cutoff date, stopping processing")
                        break

                    # Проверяем наличие кнопки "Show more"
                    show_more_button = await page.query_selector('[data-bind="visible: showLoadMore() && !loading(), click: loadMore"].standardButton.alternative.showMore')

                    if show_more_button:
                        # Проверяем, видима ли кнопка
                        is_visible = await show_more_button.is_visible()

                        if is_visible:
                            logger.info("Clicking 'Show more' button")
                            await show_more_button.click()

                            # Ждем загрузки новых данных
                            await page.wait_for_timeout(2000)

                            # Ждем исчезновения индикатора загрузки (если есть)
                            try:
                                await page.wait_for_selector('[data-bind="visible: loading()"]', state='hidden', timeout=10000)
                            except:
                                pass  # Игнорируем, если индикатора загрузки нет
                        else:
                            logger.info("'Show more' button is not visible, no more data")
                            has_more_data = False
                    else:
                        logger.info("'Show more' button not found, no more data")
                        has_more_data = False
            finally:
                await browser.close()

            logger.info(f"Parsing completed. Total processed: {total_processed}, Successfully saved: {len(parsed_dog_ids)}, Failed: {len(failed_dogs)}")

            return {
                "status": "success",
                "parsed_dog_ids": parsed_dog_ids,
                "processed_dogs_count": len(parsed_dog_ids),
                "failed_dogs": failed_dogs,
                "total_processed": total_processed,
                "pages_processed": page_count
            }

    except Exception as e:
        logger.error(f"Error in parse_breedarchive_browse_page: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "parsed_dog_ids": parsed_dog_ids,
            "processed_dogs_count": len(parsed_dog_ids),
            "failed_dogs": failed_dogs,
            "total_processed": total_processed
        }

async def extract_dog_data_from_element(page, dog_element) -> Optional[Dict[str, Any]]:
    try:
        # Извлекаем UUID и link_name из ссылки
        link_element = await dog_element.query_selector('a.profilePhoto')
        if not link_element:
            return None
            
        href = await link_element.get_attribute('href')
        if not href:
            return None
            
        # Парсим UUID из href: /animal/view/lodgepoles-life-finds-a-way-720a0e40-3951-4538-b61d-3e2ba222c468
        uuid_match = re.search(r'-([a-f0-9-]{36})$', href)
        if not uuid_match:
            return None
            
        uuid = uuid_match.group(1)
        link_name = href.split('/')[-1].replace(f'-{uuid}', '')
        
        # Извлекаем зарегистрированное имя
        name_element = await dog_element.query_selector('.registeredNameLink span[data-bind="text: registered_name"]')
        registered_name = await name_element.text_content() if name_element else None
        
        # Извлекаем префикс титулов
        prefix_element = await dog_element.query_selector('.prefixTitles')
        prefix_titles = await prefix_element.text_content() if prefix_element else None
        
        # Извлекаем суффикс титулов
        suffix_element = await dog_element.query_selector('.suffixTitles')
        suffix_titles = await suffix_element.text_content() if suffix_element else None
        
        # Извлекаем пол
        male_icon = await dog_element.query_selector('.icon-male')
        female_icon = await dog_element.query_selector('.icon-female')
        sex = 1 if male_icon and await male_icon.is_visible() else 2 if female_icon and await female_icon.is_visible() else None
        
        # Извлекаем родителей
        parents_element = await dog_element.query_selector('.italic')
        sire_name = None
        dam_name = None
        if parents_element:
            parent_spans = await parents_element.query_selector_all('span')
            if len(parent_spans) >= 3:
                sire_name = await parent_spans[0].text_content()
                dam_name = await parent_spans[2].text_content()
        
        # Извлекаем цвет
        color_element = await dog_element.query_selector('[data-bind="text: color"]')
        color = await color_element.text_content() if color_element else None
        
        # Извлекаем место рождения и год
        birth_element = await dog_element.query_selector('div:has(span[data-bind="text: land_of_birth"])')
        land_of_birth = None
        year_of_birth = None
        if birth_element:
            land_span = await birth_element.query_selector('span[data-bind="text: land_of_birth"]')
            year_span = await birth_element.query_selector('span[data-bind="text: (year_of_birth != \'\' ? \' \' : \'\') + year_of_birth"]')
            
            land_of_birth = await land_span.text_content() if land_span else None
            year_text = await year_span.text_content() if year_span else None
            if year_text:
                year_match = re.search(r'(\d{4})', year_text)
                if year_match:
                    year_of_birth = int(year_match.group(1))
        
        # Извлекаем дату модификации
        date_element = await dog_element.query_selector('.dateModified')
        modified_at = await date_element.text_content() if date_element else None
        
        # Проверяем, является ли запись новой
        new_ribbon = await dog_element.query_selector('.ribbon')
        is_new = new_ribbon is not None and await new_ribbon.is_visible()
        
        # Собираем данные
        dog_data = {
            'uuid': uuid,
            'link_name': link_name,
            'registered_name': registered_name,
            'prefix_titles': prefix_titles,
            'suffix_titles': suffix_titles,
            'sex': sex,
            'sire_name': sire_name,
            'dam_name': dam_name,
            'color': color,
            'land_of_birth': land_of_birth,
            'year_of_birth': year_of_birth,
            'modified_at': modified_at,
            'is_new': is_new
        }
        
        return dog_data
        
    except Exception as e:
        logger.error(f"Error extracting dog data from element: {str(e)}")
        return None