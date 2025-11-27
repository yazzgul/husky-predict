from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict
import logging

from core.database import get_async_session
from models.dog import Dog
from models.medicalRecord import MedicalRecord, MedicalRecordCreate, MedicalRecordRead
from parsers.ofa_parser import (
    search_and_parse_dog_medical_records,
    process_dog_medical_records,
    batch_process_medical_records
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["OFA Medical Records"])

@router.get("/search", response_model=Dict)
async def search_dog_medical_records(
    registration_number: Optional[str] = Query(None, description="Dog registration number"),
    dog_name: Optional[str] = Query(None, description="Dog registered name"),
    ofa_number: Optional[str] = Query(None, description="OFA number"),
    session: AsyncSession = Depends(get_async_session)
):
    if not any([registration_number, dog_name, ofa_number]):
        raise HTTPException(
            status_code=400,
            detail="At least one search parameter must be provided: registration_number, dog_name, or ofa_number"
        )

    try:
        result = await search_and_parse_dog_medical_records(
            registration_number=registration_number,
            dog_name=dog_name,
            ofa_number=ofa_number
        )

        if not result:
            return {
                "success": False,
                "message": "No medical records found",
                "search_criteria": {
                    "registration_number": registration_number,
                    "dog_name": dog_name,
                    "ofa_number": ofa_number
                }
            }

        return {
            "success": True,
            "message": f"Found {len(result['medical_records'])} medical records",
            "appnum": result['appnum'],
            "dog_info": result['dog_info'],
            "medical_records": result['medical_records']
        }

    except Exception as e:
        logger.error(f"Error searching OFA records: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error searching OFA records: {str(e)}")

@router.post("/process/{dog_id}", response_model=Dict)
async def process_dog_medical_records_endpoint(
    dog_id: int,
    registration_number: Optional[str] = Query(None, description="Dog registration number"),
    dog_name: Optional[str] = Query(None, description="Dog registered name"),
    ofa_number: Optional[str] = Query(None, description="OFA number"),
    session: AsyncSession = Depends(get_async_session)
):
    dog_result = await session.execute(select(Dog).where(Dog.id == dog_id))
    dog = dog_result.scalars().first()

    if not dog:
        raise HTTPException(status_code=404, detail=f"Dog with ID {dog_id} not found")

    if not any([registration_number, dog_name, ofa_number]):
        registration_number = dog.registration_number
        dog_name = dog.registered_name

    if not any([registration_number, dog_name, ofa_number]):
        raise HTTPException(
            status_code=400,
            detail="No search criteria provided and dog has no registration number or name"
        )

    try:
        result = await process_dog_medical_records(
            dog_id=dog_id,
            registration_number=registration_number,
            dog_name=dog_name,
            ofa_number=ofa_number
        )

        return result

    except Exception as e:
        logger.error(f"Error processing medical records for dog {dog_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing medical records: {str(e)}")

@router.post("/batch-process", response_model=List[Dict])
async def batch_process_medical_records_endpoint(
    dogs_data: List[Dict],
    session: AsyncSession = Depends(get_async_session)
):
    if not dogs_data:
        raise HTTPException(status_code=400, detail="No dogs data provided")

    try:
        results = await batch_process_medical_records(dogs_data)
        return results

    except Exception as e:
        logger.error(f"Error in batch processing: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error in batch processing: {str(e)}")

@router.get("/records/{dog_id}", response_model=List[MedicalRecordRead])
async def get_dog_medical_records(
    dog_id: int,
    session: AsyncSession = Depends(get_async_session)
):
    dog_result = await session.execute(select(Dog).where(Dog.id == dog_id))
    dog = dog_result.scalars().first()

    if not dog:
        raise HTTPException(status_code=404, detail=f"Dog with ID {dog_id} not found")

    records_result = await session.execute(
        select(MedicalRecord).where(MedicalRecord.dog_id == dog_id)
    )
    records = records_result.scalars().all()

    return records

@router.get("/records", response_model=List[MedicalRecordRead])
async def get_all_medical_records(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    session: AsyncSession = Depends(get_async_session)
):
    records_result = await session.execute(
        select(MedicalRecord)
        .limit(limit)
        .offset(offset)
    )
    records = records_result.scalars().all()

    return records

@router.delete("/records/{record_id}")
async def delete_medical_record(
    record_id: int,
    session: AsyncSession = Depends(get_async_session)
):
    record_result = await session.execute(
        select(MedicalRecord).where(MedicalRecord.id == record_id)
    )
    record = record_result.scalars().first()

    if not record:
        raise HTTPException(status_code=404, detail=f"Medical record with ID {record_id} not found")

    try:
        await session.delete(record)
        await session.commit()

        return {
            "success": True,
            "message": f"Medical record {record_id} deleted successfully"
        }

    except Exception as e:
        logger.error(f"Error deleting medical record {record_id}: {str(e)}")
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting medical record: {str(e)}")

@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "OFA Medical Records Parser",
        "version": "1.0.0"
    }