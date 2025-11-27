from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import logging
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.parsersConfig import BREEDBASE_API, BREEDBASE_DOG_PATH
from core.database import session_scope
from models.dog import Dog
from parsers.breedbase import process_breedbase_pages, fetch_dog_page_by_url, parse_dog_page_recursive, save_to_database, parse_dog_info, map_to_dog_model

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/dog/fetchPages", tags=["breedbase"])
async def sync_breedbase_data(
    pagesCount: Optional[int] = Query(1, ge=1, description="Количество страниц для парсинга"),
    startPage: int = Query(0, ge=0, description="Стартовый индекс страниц"),
    recursive: bool = Query(True, description="Парсить рекурсивно"),
    pedigree_depth: int = Query(5, ge=1, le=10, description="Глубина родословной")
):
    try:
        result = await process_breedbase_pages(pages_count=pagesCount, start_page=startPage, recursive=recursive, pedigree_depth=pedigree_depth)
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"Error in sync_breedbase_data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dog/fetch/{dogId}", response_model=Dog, tags=["breedbase"])
async def fetch_breedbase_dog(dogId: str, with_update: bool = True, maxDeep: int = 5):
    try:
        async with session_scope() as session:
            if not with_update:
                result = await session.execute(
                    select(Dog)
                    .where(Dog.uuid == dogId)
                    .options(
                        selectinload(Dog.dam),
                        selectinload(Dog.sire),
                        selectinload(Dog.titles),
                        selectinload(Dog.owners),
                        selectinload(Dog.breeders),
                        selectinload(Dog.litters_as_dam),
                        selectinload(Dog.litters_as_sire),
                        selectinload(Dog.litters_as_mating_partner),
                        selectinload(Dog.birth_litter),
                        selectinload(Dog.siblings)
                    )
                )
                dog = result.scalars().first()
                if dog:
                    return dog
        dog_url = f"{BREEDBASE_API}{BREEDBASE_DOG_PATH}/details.php?name={dogId}&gens=6"
        async with httpx.AsyncClient() as client:
            html = await fetch_dog_page_by_url(client, dog_url)
            dog_data = await parse_dog_page_recursive(client, html, dogId, recursive=True, pedigree_depth=maxDeep)
        async with session_scope() as session:
            saved_dog = await save_to_database(dog_data, session)
            if saved_dog:
                return saved_dog
        raise HTTPException(status_code=404, detail="Dog not found in breedbase.ru database")
    except Exception as e:
        logger.error(f"Error in fetch_breedbase_dog: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dog/parseDogPage/{dogPath}", tags=["breedbase"])
async def parse_breedbase_dog(dogId: str):
    try:
        dog_url = f"{BREEDBASE_API}{BREEDBASE_DOG_PATH}/details.php?name={dogId}&gens=6"
        async with httpx.AsyncClient() as client:
            html = await fetch_dog_page_by_url(client, dog_url)
            soup = BeautifulSoup(html, 'lxml')
            dog_info = parse_dog_info(soup)
            dog_data = map_to_dog_model({'dog_info': dog_info}, max_depth=2)
        return dog_data
    except Exception as e:
        logger.error(f"Error in parse_breedbase_dog: {e}")
        raise HTTPException(status_code=500, detail=str(e))
