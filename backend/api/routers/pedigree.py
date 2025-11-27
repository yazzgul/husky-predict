from datetime import datetime
import logging
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from models.dog import Dog
from core.database import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/{dog_id}", tags=["dog-pedigree"])
async def get_pedigree(
    dog_id: int, 
    generations: int = Query(5, ge=1, le=8, description="Количество поколений для отображения"),
    session: AsyncSession = Depends(get_async_session)
):

    try:
        async def get_ancestors(dog: Dog, depth: int):
            if depth == 0 or not dog:
                return None

            dam, sire = None, None
            if dog.dam_id:
                dam = await session.get(Dog, dog.dam_id)
            if dog.sire_id:
                sire = await session.get(Dog, dog.sire_id)
            
            dam_data = await get_ancestors(dam, depth-1) if dam else None
            sire_data = await get_ancestors(sire, depth-1) if sire else None
            
            return {
                **dog.model_dump(),
                "dam": dam_data,
                "sire": sire_data
            }
        
        result = await session.execute(select(Dog).where(Dog.id == dog_id))
        dog = result.scalars().first()
        
        if not dog:
            raise HTTPException(status_code=404, detail="Dog not found")
        
        return await get_ancestors(dog, generations)
    except Exception as e:
        logger.error(f"Error getting pedigree for dog {dog_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/uuid/{uuid}", tags=["dog-pedigree"])
async def get_pedigree_by_uuid(
    uuid: str,
    generations: int = Query(5, ge=1, le=8, description="Количество поколений для отображения"),
    session: AsyncSession = Depends(get_async_session)
):

    try:
        async def get_ancestors(dog: Dog, depth: int):
            if depth == 0 or not dog:
                return None

            dam, sire = None, None
            if dog.dam_id:
                dam = await session.get(Dog, dog.dam_id)
            if dog.sire_id:
                sire = await session.get(Dog, dog.sire_id)
            
            dam_data = await get_ancestors(dam, depth-1) if dam else None
            sire_data = await get_ancestors(sire, depth-1) if sire else None
            
            return {
                **dog.model_dump(),
                "dam": dam_data,
                "sire": sire_data
            }
        
        result = await session.execute(select(Dog).where(Dog.uuid == uuid))
        dog = result.scalars().first()
        
        if not dog:
            raise HTTPException(status_code=404, detail="Dog not found")
        
        return await get_ancestors(dog, generations)
    except Exception as e:
        logger.error(f"Error getting pedigree for dog with UUID {uuid}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/detailed/{dog_id}", tags=["dog-pedigree"])
async def get_detailed_pedigree(
    dog_id: int,
    generations: int = Query(5, ge=1, le=8, description="Количество поколений для отображения"),
    session: AsyncSession = Depends(get_async_session)
):
    try:
        async def get_ancestors_with_details(dog: Dog, depth: int):
            if depth == 0 or not dog:
                return None

            dam, sire = None, None
            if dog.dam_id:
                dam_result = await session.execute(
                    select(Dog)
                    .where(Dog.id == dog.dam_id)
                    .options(
                        selectinload(Dog.titles),
                        selectinload(Dog.owners),
                        selectinload(Dog.breeders),
                        selectinload(Dog.litters_as_dam),
                        selectinload(Dog.litters_as_sire),
                        selectinload(Dog.birth_litter),
                        selectinload(Dog.siblings),
                    )
                )
                dam = dam_result.scalars().first()
                
            if dog.sire_id:
                sire_result = await session.execute(
                    select(Dog)
                    .where(Dog.id == dog.sire_id)
                    .options(
                        selectinload(Dog.titles),
                        selectinload(Dog.owners),
                        selectinload(Dog.breeders),
                        selectinload(Dog.litters_as_dam),
                        selectinload(Dog.litters_as_sire),
                        selectinload(Dog.birth_litter),
                        selectinload(Dog.siblings),
                    )
                )
                sire = sire_result.scalars().first()
            
            dam_data = await get_ancestors_with_details(dam, depth-1) if dam else None
            sire_data = await get_ancestors_with_details(sire, depth-1) if sire else None
            
            return {
                **dog.model_dump(),
                "dam": dam_data,
                "sire": sire_data
            }
        
        result = await session.execute(
            select(Dog)
            .where(Dog.id == dog_id)
            .options(
                selectinload(Dog.titles),
                selectinload(Dog.owners),
                selectinload(Dog.breeders),
                selectinload(Dog.litters_as_dam),
                selectinload(Dog.litters_as_sire),
                selectinload(Dog.litters_as_mating_partner),
                selectinload(Dog.birth_litter),
                selectinload(Dog.siblings),
            )
        )
        dog = result.scalars().first()
        
        if not dog:
            raise HTTPException(status_code=404, detail="Dog not found")
        
        return await get_ancestors_with_details(dog, generations)
    except Exception as e:
        logger.error(f"Error getting detailed pedigree for dog {dog_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ancestors/{dog_id}", tags=["dog-pedigree"])
async def get_ancestors(
    dog_id: int,
    generations: int = Query(5, ge=1, le=8, description="Количество поколений для отображения"),
    session: AsyncSession = Depends(get_async_session)
):
    try:
        ancestors = []
        
        async def collect_ancestors(dog: Dog, depth: int, position: str = ""):
            if depth == 0 or not dog:
                return
            
            ancestors.append({
                "id": dog.id,
                "uuid": dog.uuid,
                "registered_name": dog.registered_name,
                "call_name": dog.call_name,
                "sex": dog.sex,
                "date_of_birth": dog.date_of_birth,
                "generation": 5 - depth,
                "position": position,
                "source": dog.source
            })
            
            if dog.dam_id:
                dam = await session.get(Dog, dog.dam_id)
                if dam:
                    await collect_ancestors(dam, depth-1, f"{position}.dam" if position else "dam")
                    
            if dog.sire_id:
                sire = await session.get(Dog, dog.sire_id)
                if sire:
                    await collect_ancestors(sire, depth-1, f"{position}.sire" if position else "sire")
        
        result = await session.execute(select(Dog).where(Dog.id == dog_id))
        dog = result.scalars().first()
        
        if not dog:
            raise HTTPException(status_code=404, detail="Dog not found")
        
        await collect_ancestors(dog, generations)
        
        return {
            "dog_id": dog_id,
            "generations": generations,
            "ancestors": ancestors,
            "total_ancestors": len(ancestors)
        }
    except Exception as e:
        logger.error(f"Error getting ancestors for dog {dog_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
