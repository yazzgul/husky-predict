import asyncio
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import logging
import httpx

from models.dog import Dog
from core.parsersConfig import BREEDARCHIVE_API, BREEDARCHIVE_DOG_PATH, HEADERS
from core.database import session_scope
from parsers.breedarchive import parse_data_from_page_scripts, process_animal_by_uuid, process_animal_with_new_session, parse_breedarchive_browse_page

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/dog/fetchPages", tags=["breedarchive"])
async def sync_breedarchive_data(
    pagesCount: Optional[int] = Query(
        1, 
        ge=1, 
        le=10,
        description="Количество страниц (1-10)"
    ), 
    startPage: int = Query(
        0, 
        ge=0, 
        le=9,
        description="Стартовый индекс (0-9)"
    ),
    isFullSync: bool = False, 
    isRefresh: bool = False,
):
    try:
        async with httpx.AsyncClient() as client:
            start = startPage * 25
            parsed_dog_ids = []
            parsedRowsCounter = 0
            available_pages = int((250 - startPage * 25) / 25)
            has_more = True

            logger.info(f'Start fetching recent updates data from BreedArchive API...')
            
            if(not isFullSync):
                logger.info(f'Start page: {startPage} \nPages to parse: {pagesCount} \nAvailable pages: {available_pages}')
            
            while True:
                url = f"{BREEDARCHIVE_API}/ng_animal/get_entries?operation=all&start={start}"
                response = await client.get(url, headers=HEADERS)
                data = response.json()

                semaphore = asyncio.Semaphore(8)
                tasks = []
                            
                for animal in data["animals"]:
                    async with semaphore:
                        tasks.append(
                            process_animal_with_new_session(client, animal, isRefresh)
                        )
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                parsed_dog_ids.extend([r for r in results if isinstance(r, int)])
                
                parsedRowsCounter += 25
                start += 25
                
                if not data.get("has_more", False) or (not isFullSync and parsedRowsCounter >= pagesCount * 25 or start > 225):
                    has_more = False
                    break    
                    
                logger.info(f'Start: {start}, parsed_dog_ids: {parsed_dog_ids}, "processed_dogs_count": {len(parsed_dog_ids)}')
                                
            return {"status": "success", "parsed_dog_ids": parsed_dog_ids, "processed_dogs_count": len(parsed_dog_ids)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/dog/parseRecentPage", tags=["breedarchive"])
async def parse_breedarchive_recent_dogs(
    recent_days: int = Query(
        1,
        ge=1,
        le=30,
        description="Количество дней для фильтрации записей по дате модификации (1-30)"
    )
):

    try:
        logger.info(f"Starting breedarchive browse page parsing with recent_days={recent_days}")
        
        result = await parse_breedarchive_browse_page(recent_days)
        
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["error"])
            
        return result
        
    except Exception as e:
        logger.error(f"Error in parse_breedarchive_browse_page_route: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dog/fetch/{uuid}", response_model=Dog, tags=["breedarchive"])
async def fetch_breedarchive_dog(uuid: str, with_update: bool = True, maxDeep: int = 5):
    try:
        async with session_scope() as check_session:
            if not with_update:
                result = await check_session.execute(
                    select(Dog)
                    .where(Dog.uuid == uuid)
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
                
        logger.info(f"maxDeep param: {maxDeep}")
        dog = await process_animal_by_uuid(uuid, maxDeep)
                
        if not dog:
            raise HTTPException(status_code=404, detail="Dog not found in breedarchive.com database")
            
        return dog

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dog/parseDogPage/{dogPath}", tags=["breedarchive"])
async def parse_breedarchive_dog(dogPath: str):
    dogUrl = f"{BREEDARCHIVE_API}{BREEDARCHIVE_DOG_PATH}/{dogPath}"
    parsed_data = await parse_data_from_page_scripts(dogUrl)
    
    if not parsed_data:
        raise HTTPException(status_code=404, detail="Can't parse it")
    return parsed_data
