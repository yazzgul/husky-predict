"""
Роутер FastAPI для работы с Zooportal

Эндпоинты:
- /zooportal/dog/{dog_id} - Полная обработка собаки с Zooportal с интеграцией BreedArchive
- /zooportal/search/{page_num} - Обработка страницы поиска на Zooportal
- /zooportal/parse/search/{page_num} - Только парсинг списка собак (без сохранения)
- /zooportal/parse/dog/{dog_id} - Только парсинг собаки (без сохранения)
- /zooportal/health - Проверка здоровья парсера
"""

from fastapi import APIRouter, Query, HTTPException, Depends, Path
from typing import Optional, List
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from models.dog import Dog
from core.database import get_async_session
from parsers.zooportal import (
    parse_zooportal_search_page,
    parse_zooportal_dog_page
)
from parsers.zooportal_integration import (
    process_zooportal_dog_with_ancestors,
    process_zooportal_search_page_and_save
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["zooportal"])


# @router.post("/dog/{dog_id}", response_model=Dog, summary="Полная обработка собаки с Zooportal")
# async def fetch_zooportal_dog_complete(
#         dog_id: str = Path(..., description="ID собаки на Zooportal"),
#         generations: int = Query(3, ge=1, le=8, description="Глубина родословной"),
#         session: AsyncSession = Depends(get_async_session)
# ):
#     """
#     Полная обработка собаки с Zooportal с интеграцией BreedArchive
#
#     Алгоритм:
#     1. Парсит данные с Zooportal
#     2. Ищет собаку в BreedArchive (только базовые данные)
#     3. Создает/обновляет запись в БД
#     4. Обрабатывает предков и устанавливает связи
#     5. Сохраняет заводчика и владельца
#     """
#     try:
#         dog = await process_zooportal_dog_with_ancestors(dog_id, generations, session)
#
#         if not dog:
#             raise HTTPException(status_code=404, detail=f"Dog {dog_id} not found or failed to process")
#
#         return dog
#
#     except Exception as e:
#         logger.error(f"Error processing dog {dog_id}: {str(e)}")
#         raise HTTPException(status_code=500, detail=str(e))
@router.post("/dog/{dog_id}", response_model=Dog, summary="Полная обработка собаки с Zooportal")
async def fetch_zooportal_dog_complete(
        dog_id: str = Path(..., description="ID собаки на Zooportal"),
        generations: int = Query(3, ge=1, le=8, description="Глубина родословной"),
        session: AsyncSession = Depends(get_async_session)
):
    """
    Полная обработка собаки с Zooportal с интеграцией BreedArchive
    """
    try:
        async with session.begin():
            dog = await process_zooportal_dog_with_ancestors(dog_id, generations, session)

            if not dog:
                # бросаем внутри транзакции → begin сделает rollback
                raise HTTPException(
                    status_code=404,
                    detail=f"Dog {dog_id} not found or failed to process"
                )

        # если дошли сюда — begin уже сделал commit
        return dog

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error processing dog {dog_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/search/{page_num}", summary="Обработка страницы поиска с сохранением")
async def process_and_save_zooportal_page(
        page_num: int = Path(..., ge=1, description="Номер страницы поиска"),
        max_dogs: int = Query(10, ge=1, le=50, description="Максимальное количество собак для обработки"),
        delay_between_dogs: float = Query(2.0, ge=0.5, le=10.0,
                                          description="Задержка между обработкой собак в секундах")
):
    """
    Обрабатывает страницу поиска на Zooportal с сохранением в БД

    Обрабатывает всех собак со страницы поиска:
    1. Парсит список собак
    2. Для каждой собаки запускает полную обработку
    3. Сохраняет результаты в БД
    """
    try:
        result = await process_zooportal_search_page_and_save(page_num, max_dogs, delay_between_dogs)
        return result

    except Exception as e:
        logger.error(f"Error processing page {page_num}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/parse/search/{page_num}", summary="Только парсинг списка собак")
async def search_zooportal_dogs(
        page_num: int = Path(..., ge=1, description="Номер страницы поиска")
):
    """
    Только парсит список собак без сохранения в БД

    Используется для тестирования и проверки работы парсера
    """
    try:
        dogs_list = await parse_zooportal_search_page(page_num)

        return {
            "page": page_num,
            "dogs_count": len(dogs_list),
            "dogs": dogs_list
        }

    except Exception as e:
        logger.error(f"Error searching page {page_num}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/parse/dog/{dog_id}", summary="Только парсинг собаки")
async def parse_zooportal_dog_only(
        dog_id: str = Path(..., description="ID собаки на Zooportal"),
        generations: int = Query(3, ge=1, le=8, description="Глубина родословной")
):
    """
    Только парсит собаку без сохранения в БД

    Возвращает сырые данные парсинга для отладки
    """
    try:
        parsed_data = await parse_zooportal_dog_page(dog_id, generations)
        return parsed_data

    except Exception as e:
        logger.error(f"Error parsing dog {dog_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", summary="Проверка здоровья парсера")
async def zooportal_health_check():
    """
    Проверка здоровья парсера Zooportal

    Тестовый запрос для проверки доступности Zooportal
    """
    try:
        dogs_list = await parse_zooportal_search_page(1)

        return {
            "status": "healthy",
            "service": "Zooportal Parser",
            "dogs_found": len(dogs_list) if dogs_list else 0,
            "message": "Parser is working correctly"
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "Zooportal Parser",
            "error": str(e)
        }