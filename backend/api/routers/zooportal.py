"""
Роутер FastAPI для работы с Zooportal

Эндпоинты:
- /zooportal/dog/{dog_id} - Полная обработка собаки с Zooportal с интеграцией BreedArchive
- /zooportal/search/page/{page_num} - Обработка страницы поиска на Zooportal
- /zooportal/parse/search/{page_num} - Только парсинг списка собак (без сохранения)
- /zooportal/parse/dog/{dog_id} - Только парсинг собаки (без сохранения)
- /zooportal/health - Проверка здоровья парсера
- /zooportal/search/pages/range" - Обработка диапазона страниц поиска с сохранением

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


@router.post("/dog/{dog_id}", response_model=Dog, summary="Полная обработка собаки с Zooportal")
async def fetch_zooportal_dog_complete(
        dog_id: str = Path(..., description="ID собаки на Zooportal"),
        generations: int = Query(3, ge=3, le=3, description="Глубина родословной"),
        session: AsyncSession = Depends(get_async_session)
):
    """
    Полная обработка собаки с Zooportal с интеграцией BreedArchive

    Реализовано для глубины 3
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


@router.post("/search/page/{page_num}", summary="Обработка страницы поиска с сохранением")
async def process_and_save_zooportal_page(
        page_num: int = Path(..., ge=1, description="Номер страницы поиска"),
        max_dogs: int = Query(11, ge=1, le=11, description="Максимальное количество собак для обработки"),
        delay_between_dogs: float = Query(1.5, ge=0.5, le=10.0,
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

from fastapi import Query, HTTPException
import asyncio

@router.post("/search/pages/range", summary="Обработка диапазона страниц поиска с сохранением")
async def process_and_save_zooportal_range(
    start_page: int = Query(..., ge=1, description="Начальная страница"),
    end_page: int = Query(..., ge=1, description="Конечная страница (включительно)"),
    max_dogs: int = Query(11, ge=1, le=11),
    delay_between_dogs: float = Query(1.5, ge=0.5, le=10.0),
    delay_between_pages: float = Query(0.0, ge=0.0, le=20.0, description="Задержка между страницами"),
):
    """
    Обрабатывает диапазон страниц поиска на Zooportal с сохранением данных в БД.

    Функция последовательно проходит по страницам поиска Zooportal
    от start_page до end_page (включительно) и для каждой страницы:

    1. Парсит список собак со страницы поиска
    2. Ограничивает количество собак параметром max_dogs
    3. Для каждой собаки запускает полную обработку и сохранение в БД
    4. Делает паузы между обработкой собак и страниц, чтобы не перегружать сайт

    Параметры:
    - start_page (int):
        Номер страницы, с которой начинается обработка.
        Страницы нумеруются с 1.

    - end_page (int):
        Номер последней страницы, которую нужно обработать.
        Страница включается в обработку.

    - max_dogs (int, по умолчанию 10):
        Максимальное количество собак, обрабатываемых на одной странице.
        Используется для ограничения нагрузки и удобства тестирования.

    - delay_between_dogs (float, по умолчанию 2.0):
        Задержка в секундах между обработкой отдельных собак.
        Помогает избежать блокировок и ошибок при парсинге.

    - delay_between_pages (float, по умолчанию 0.0):
        Задержка в секундах между обработкой страниц поиска.
        Полезно при обработке большого количества страниц.

    """

    if end_page < start_page:
        raise HTTPException(status_code=400, detail="end_page must be >= start_page")

    pages = []
    total_processed = 0
    total_failed = 0

    for page_num in range(start_page, end_page + 1):
        result = await process_zooportal_search_page_and_save(page_num, max_dogs, delay_between_dogs)
        pages.append(result)

        total_processed += int(result.get("processed", 0))
        total_failed += int(result.get("failed", 0))

        if delay_between_pages > 0 and page_num != end_page:
            await asyncio.sleep(delay_between_pages)

    return {
        "status": "success",
        "start_page": start_page,
        "end_page": end_page,
        "total_processed": total_processed,
        "total_failed": total_failed,
        "pages": pages,
    }


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