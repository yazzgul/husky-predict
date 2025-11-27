from datetime import datetime
import logging
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
import os

from models.dog import Dog, DogListResponse, DogRead
from models.merge_log import MergeLog
from services.dog_service import DogService
from core.database import get_async_session
import json

logger = logging.getLogger(__name__)

router = APIRouter()

class DogNotesUpdateRequest(BaseModel):
    notes: Optional[str] = None
    data_correctness_notes: Optional[str] = None

@router.get("/{dog_id}", response_model=DogRead, tags=["dogs"])
async def get_dog(
    dog_id: int,
    session: AsyncSession = Depends(get_async_session)
):
    try:
        result = await session.execute(
            select(Dog)
            .where(Dog.id == dog_id)
            .options(
                selectinload(Dog.titles),
                selectinload(Dog.owners),
                selectinload(Dog.breeders),
                selectinload(Dog.dam),
                selectinload(Dog.sire),
                selectinload(Dog.litters_as_dam),
                selectinload(Dog.litters_as_sire),
                selectinload(Dog.litters_as_mating_partner),
                selectinload(Dog.birth_litter),
                selectinload(Dog.siblings),
                selectinload(Dog.medical_records),
                selectinload(Dog.merge_logs),
            )
        )
        dog = result.scalars().first()
        if not dog:
            raise HTTPException(status_code=404, detail="Dog not found")
        return dog
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Эндпоинт для получения списка собак с фильтрами
@router.get("/", response_model=DogListResponse, tags=["dogs"])
async def get_dogs(
    # Пагинация
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),

    # Основные фильтры
    search: Optional[str] = Query(None, description="Search in registered_name, registration_number, call_name"),

    # Дополнительные фильтры
    sex: Optional[int] = Query(None),
    color: Optional[str] = Query(None),
    min_year: Optional[int] = Query(None),
    max_year: Optional[int] = Query(None),

    land_of_birth: Optional[str] = Query(None),
    land_of_standing: Optional[str] = Query(None),
    owner_name: Optional[str] = Query(None),
    breeder_name: Optional[str] = Query(None),

    neutered: Optional[bool] = Query(None),
    frozen_semen: Optional[bool] = Query(None),
    artificial_insemination: Optional[bool] = Query(None),
    has_photo: Optional[bool] = Query(None),
    has_conflicts: Optional[bool] = Query(None),

    date_of_birth_start: Optional[datetime] = Query(None),
    date_of_birth_end: Optional[datetime] = Query(None),
    date_of_death_start: Optional[datetime] = Query(None),
    date_of_death_end: Optional[datetime] = Query(None),
    modified_at_start: Optional[datetime] = Query(None),
    modified_at_end: Optional[datetime] = Query(None),

    # Сортировка
    sort_by: Optional[str] = Query('registered_name', enum=[
        'registered_name', 'call_name', 'year_of_birth', 'date_of_birth',
        'land_of_birth', 'land_of_standing', 'modified_at'
    ]),
    sort_order: Optional[str] = Query('asc', enum=['asc', 'desc']),

    session: AsyncSession = Depends(get_async_session)
):
    try:
        return await DogService(session).get_dogs_paginated(
            page=page,
            per_page=per_page,

            search=search,
            color=color,
            land_of_birth=land_of_birth,
            land_of_standing=land_of_standing,
            owner_name=owner_name,
            breeder_name=breeder_name,

            sex=sex,
            neutered=neutered,
            frozen_semen=frozen_semen,
            artificial_insemination=artificial_insemination,
            has_photo=has_photo,
            has_conflicts=has_conflicts,

            min_year=min_year,
            max_year=max_year,
            date_of_birth_start=date_of_birth_start,
            date_of_birth_end=date_of_birth_end,
            date_of_death_start=date_of_death_start,
            date_of_death_end=date_of_death_end,
            modified_at_start=modified_at_start,
            modified_at_end=modified_at_end,

            sort_by=sort_by,
            sort_order=sort_order
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{dog_id}/calculate-coi", tags=["dogs"])
async def calculate_coi(
    dog_id: int,
    max_generations: int = Query(10, ge=1, le=20, description="Maximum number of generations to analyze"),
    session: AsyncSession = Depends(get_async_session)
):
    try:
        dog_service = DogService(session)
        result = await dog_service.calculate_coi(dog_id, max_generations)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating COI for dog {dog_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error calculating COI: {str(e)}")

@router.get("/{dog_id}/coi", tags=["dogs"])
async def get_coi(
    dog_id: int,
    session: AsyncSession = Depends(get_async_session)
):
    try:
        result = await session.execute(
            select(Dog).where(Dog.id == dog_id)
        )
        dog = result.scalars().first()

        if not dog:
            raise HTTPException(status_code=404, detail="Dog not found")

        # Если COI существует, обновляем coi_updated_on
        if dog.coi is not None:
            dog.coi_updated_on = datetime.utcnow()
            await session.commit()
            await session.refresh(dog)

        return {
            "dog_id": dog_id,
            "dog_name": dog.registered_name,
            "coi": dog.coi,
            "coi_percentage": dog.coi * 100 if dog.coi else None,
            "coi_updated_on": dog.coi_updated_on,
            "has_coi": dog.coi is not None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting COI for dog {dog_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting COI: {str(e)}")

@router.post("/batch-calculate-coi", tags=["dogs"])
async def batch_calculate_coi(
    dog_ids: list[int],
    max_generations: int = Query(10, ge=1, le=20, description="Maximum number of generations to analyze"),
    session: AsyncSession = Depends(get_async_session)
):
    try:
        if not dog_ids:
            raise HTTPException(status_code=400, detail="No dog IDs provided")

        if len(dog_ids) > 100:
            raise HTTPException(status_code=400, detail="Maximum 100 dogs can be processed at once")

        dog_service = DogService(session)
        results = []

        for dog_id in dog_ids:
            try:
                result = await dog_service.calculate_coi(dog_id, max_generations)
                results.append({
                    "dog_id": dog_id,
                    "success": True,
                    "result": result
                })
            except Exception as e:
                results.append({
                    "dog_id": dog_id,
                    "success": False,
                    "error": str(e)
                })

        return {
            "total_dogs": len(dog_ids),
            "successful_calculations": len([r for r in results if r["success"]]),
            "failed_calculations": len([r for r in results if not r["success"]]),
            "results": results
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch COI calculation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error in batch COI calculation: {str(e)}")

# Роут для разрешения конфликтов по dog_id
@router.post("/{dog_id}/resolve_conflicts", tags=["dogs"])
async def resolve_conflicts(
    dog_id: int,
    resolved_fields: dict = Body(..., description="Поля Dog, в которых был разрешен конфликт вручную пользователем"),
    session: AsyncSession = Depends(get_async_session)
):
    try:
        # Получаем текущую запись Dog
        result = await session.execute(select(Dog).where(Dog.id == dog_id))
        dog = result.scalars().first()
        if not dog:
            raise HTTPException(status_code=404, detail="Dog not found")

        # Сохраняем старые значения и conflicts
        old_values = {field: getattr(dog, field) for field in resolved_fields.keys()}
        old_conflicts = dog.conflicts.copy() if dog.conflicts else None

        # Обновляем поля
        for field, value in resolved_fields.items():
            setattr(dog, field, value)

        # Сбрасываем флаги конфликтов
        dog.has_conflicts = False
        dog.conflicts = None

        # Сохраняем новые значения
        new_values = {field: getattr(dog, field) for field in resolved_fields.keys()}

        # Создаем запись в MergeLog
        merge_log = MergeLog(
            dog_id=dog.id,
            resolved_fields=resolved_fields,
            old_values=old_values,
            new_values=new_values,
            conflicts=old_conflicts,
            resolved_date=datetime.utcnow(),
            resolved_by_user_id=None
        )
        session.add(merge_log)

        await session.commit()
        await session.refresh(dog)
        return {"status": "success", "dog_id": dog.id, "merge_log_id": merge_log.id}
    except Exception as e:
        await session.rollback()
        logger.error(f"Error resolving conflicts for dog {dog_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error resolving conflicts: {str(e)}")

# Роут для отката изменений по merge_log (undo)
@router.post("/{dog_id}/undo_merge", tags=["dogs"])
async def undo_merge(
    dog_id: int,
    merge_log_id: int = Body(..., description="ID записи merge_log для отката"),
    session: AsyncSession = Depends(get_async_session)
):
    try:
        # Получаем merge_log
        result = await session.execute(select(MergeLog).where(MergeLog.id == merge_log_id, MergeLog.dog_id == dog_id))
        merge_log = result.scalars().first()
        if not merge_log:
            raise HTTPException(status_code=404, detail="MergeLog not found for this dog")

        # Получаем собаку
        result = await session.execute(select(Dog).where(Dog.id == dog_id))
        dog = result.scalars().first()
        if not dog:
            raise HTTPException(status_code=404, detail="Dog not found")

        # Откатываем old_values
        for field, value in (merge_log.old_values or {}).items():
            setattr(dog, field, value)

        # Восстанавливаем флаги конфликтов
        dog.has_conflicts = True if merge_log.conflicts else False
        dog.conflicts = merge_log.conflicts
        await session.delete(merge_log)
        await session.commit()
        await session.refresh(dog)

        return {
            "status": "success",
            "dog_id": dog.id,
            "restored_fields": merge_log.old_values,
            "has_conflicts": dog.has_conflicts,
            "conflicts": dog.conflicts
        }
    except Exception as e:
        await session.rollback()
        logger.error(f"Error undoing merge for dog {dog_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error undoing merge: {str(e)}")

@router.patch("/{dog_id}/notes", response_model=DogRead, tags=["dogs"])
async def update_dog_notes(
    dog_id: int,
    req: DogNotesUpdateRequest,
    session: AsyncSession = Depends(get_async_session)
):
    try:
        dog_service = DogService(session)
        dog = await dog_service.update_notes(
            dog_id,
            notes=req.notes,
            data_correctness_notes=req.data_correctness_notes
        )
        return dog
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating notes for dog {dog_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating notes: {str(e)}")

@router.get("/export/{dog_id}", tags=["dogs"])
async def export_dog_pedigree(
    dog_id: int,
    session: AsyncSession = Depends(get_async_session)
):
    try:
        dog_service = DogService(session)
        pdf_path, filename = await dog_service.export_dog_pedigree(dog_id)

        def file_iterator():
            with open(pdf_path, 'rb') as f:
                yield from f
            os.remove(pdf_path)

        return StreamingResponse(file_iterator(), media_type='application/pdf', headers={
            'Content-Disposition': f'attachment; filename="{filename}"'
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting pedigree for dog {dog_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error exporting pedigree: {str(e)}")