from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional, List
import logging
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from core.parsersConfig import HUSKY_PEDIGREE_NET_API, HUSKY_PEDIGREE_NET_DOG_PATH
from core.database import session_scope
from models.dog import Dog
from models.response import DogListResponse
from parsers.huskypedigree import (
    process_huskypedigree_dogs, 
    fetch_dog_page_by_url, 
    parse_dog_page_recursive, 
    save_to_database, 
    parse_dog_info, 
    map_to_dog_model,
    process_single_huskypedigree_dog,
    process_huskypedigree_list
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/huskypedigree", tags=["huskypedigree"])

class ParseRequest(BaseModel):
    dog_id: str
    recursive: bool = True
    pedigree_depth: int = 3

class FetchAndSaveRequest(BaseModel):
    dog_id: str
    recursive: bool = True
    pedigree_depth: int = 3

class ListParseRequest(BaseModel):
    start_page: int = 1
    max_pages: int = 5
    recursive: bool = True
    pedigree_depth: int = 3

@router.post("/parse-list")
async def parse_dog_list(request: ListParseRequest):
    try:
        result = await process_huskypedigree_list(
            start_page=request.start_page,
            max_pages=request.max_pages,
            recursive=request.recursive,
            pedigree_depth=request.pedigree_depth
        )
        
        return {
            "message": "Dog list processing completed",
            "parsed_dog_ids": result["parsed_dog_ids"],
            "processed_dogs_count": result["processed_dogs_count"],
            "failed_dogs": result["failed_dogs"],
            "total_attempted": result["total_attempted"],
            "success_rate": f"{(result['processed_dogs_count'] / result['total_attempted'] * 100):.1f}%" if result['total_attempted'] > 0 else "0%"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing dog list: {str(e)}") 

@router.get("/dog/fetch/{dogId}", response_model=Dog, tags=["huskypedigree"])
async def fetch_huskypedigree_dog(
    dogId: str, 
    with_update: bool = Query(True, description="Обновить данные если собака уже существует"),
    maxDeep: int = Query(3, ge=1, le=10, description="Глубина родословной")
):

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
            
            dog_url = f"{HUSKY_PEDIGREE_NET_API}{HUSKY_PEDIGREE_NET_DOG_PATH}{dogId}&gen={maxDeep}"
            async with httpx.AsyncClient() as client:
                html = await fetch_dog_page_by_url(client, dog_url)
                dog_data = await parse_dog_page_recursive(
                    client, 
                    html, 
                    dogId, 
                    recursive=True, 
                    pedigree_depth=maxDeep
                )
            
            async with session_scope() as session:
                saved_dog = await save_to_database(dog_data, session)
                if saved_dog:
                    return saved_dog
                    
        raise HTTPException(status_code=404, detail=f"Dog with ID {dogId} not found in husky.pedigre.net database")
    except Exception as e:
        logger.error(f"Error in fetch_huskypedigree_dog: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dog/parseDogPage/{dogId}", tags=["huskypedigree"])
async def parse_huskypedigree_dog(
    dogId: str,
    gen: int = Query(3, ge=1, le=10, description="Количество поколений для отображения")
):

    try:
        dog_url = f"{HUSKY_PEDIGREE_NET_API}{HUSKY_PEDIGREE_NET_DOG_PATH}{dogId}&gen={gen}"
        async with httpx.AsyncClient() as client:
            html = await fetch_dog_page_by_url(client, dog_url)
            soup = BeautifulSoup(html, 'lxml')
            dog_info = parse_dog_info(client, soup, dogId)
            dog_data = map_to_dog_model({'dog_info': dog_info}, max_depth=gen)
        return dog_data
    except Exception as e:
        logger.error(f"Error in parse_huskypedigree_dog: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/dog/fetchSingle", tags=["huskypedigree"])
async def fetch_single_huskypedigree_dog(
    dogId: str,
    recursive: bool = Query(True, description="Включить рекурсивный парсинг"),
    pedigree_depth: int = Query(3, ge=1, le=10, description="Глубина родословной")
):

    try:
        saved_dog, json_path = await process_single_huskypedigree_dog(
            dog_id=dogId,
            recursive=recursive,
            pedigree_depth=pedigree_depth
        )
        
        if saved_dog:
            return {
                "status": "success",
                "dog_id": saved_dog.id,
                "dog_uuid": saved_dog.uuid,
                "registered_name": saved_dog.registered_name,
                "json_path": json_path
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to save dog to database")
            
    except Exception as e:
        logger.error(f"Error in fetch_single_huskypedigree_dog: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    