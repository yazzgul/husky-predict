"""
Простой in-memory кэш для парсеров
"""

import time
import asyncio
from typing import Dict, Any, Optional, Tuple
import hashlib

# Глобальные словари для кэша
_cache: Dict[str, Tuple[Any, float]] = {}
_cache_lock = asyncio.Lock()

# Кэш для браузерных сессий
_browser_cache = None
_browser_lock = asyncio.Lock()

# Кэш для данных собак (дополнительный, с флагом наличия подробных данных)
_dog_data_cache: Dict[str, Dict[str, Any]] = {}
_dog_cache_lock = asyncio.Lock()

# Кэш для поиска собак в БД
_dog_db_cache = {}
_dog_db_cache_expiry = {}


async def get_cached(key: str) -> Optional[Any]:
    """Получить значение из кэша"""
    async with _cache_lock:
        if key in _cache:
            value, expiry = _cache[key]
            if time.time() < expiry:
                return value
            else:
                del _cache[key]
        return None


async def set_cached(key: str, value: Any, ttl: int = 3600):
    """Сохранить значение в кэш"""
    async with _cache_lock:
        expiry = time.time() + ttl
        _cache[key] = (value, expiry)


async def delete_cached(key: str):
    """Удалить ключ из кэша"""
    async with _cache_lock:
        _cache.pop(key, None)


def generate_cache_key(func_name: str, *args, **kwargs) -> str:
    """Генерация ключа кэша на основе имени функции и аргументов"""
    key_parts = [func_name]

    for arg in args:
        key_parts.append(str(arg))

    for key, value in sorted(kwargs.items()):
        key_parts.append(f"{key}={value}")

    key_str = ":".join(key_parts)
    if len(key_str) > 200:
        return hashlib.md5(key_str.encode()).hexdigest()
    return key_str


# Декоратор для кэширования функций
def cached(ttl: int = 3600):
    """Декоратор для кэширования результатов функций"""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            cache_key = generate_cache_key(func.__name__, *args, **kwargs)
            cached_value = await get_cached(cache_key)

            if cached_value is not None:
                print(f"КЭШ ПОПАДАНИЕ: {func.__name__} с ключом {cache_key[:50]}...")
                return cached_value

            print(f"КЭШ ПРОМАХ: {func.__name__}, вычисляем...")
            result = await func(*args, **kwargs)
            await set_cached(cache_key, result, ttl)
            return result

        return wrapper

    return decorator


# Функции для кэша данных собак
async def get_dog_data_from_cache(dog_id: str, source: str = "zooportal") -> Optional[Dict[str, Any]]:
    """Получить данные собаки из специализированного кэша"""
    cache_key = f"dog_data:{source}:{dog_id}"
    async with _dog_cache_lock:
        if cache_key in _dog_data_cache:
            data = _dog_data_cache[cache_key]
            if time.time() < data.get('expiry', 0):
                data_from_cache = data.get('data')
                data_from_cache['_has_details'] = data.get('has_details', False)

                # return data.get('data')
                return data_from_cache
            else:
                del _dog_data_cache[cache_key]
        return None


async def save_dog_data_to_cache(dog_id: str, data: Dict[str, Any],
                                 source: str = "zooportal",
                                 has_details: bool = True,
                                 ttl: int = 7200):
    """Сохранить данные собаки в специализированный кэш"""
    cache_key = f"dog_data:{source}:{dog_id}"
    async with _dog_cache_lock:
        _dog_data_cache[cache_key] = {
            'data': data,
            'has_details': has_details,
            'expiry': time.time() + ttl,
            'timestamp': time.time()
        }


async def clear_dog_cache(dog_id: str = None, source: str = None):
    """Очистить кэш собаки"""
    async with _dog_cache_lock:
        if dog_id and source:
            key = f"dog_data:{source}:{dog_id}"
            _dog_data_cache.pop(key, None)
        elif dog_id:
            keys_to_delete = [k for k in _dog_data_cache.keys() if f":{dog_id}" in k]
            for key in keys_to_delete:
                del _dog_data_cache[key]
        else:
            _dog_data_cache.clear()


def get_cache_stats() -> Dict[str, Any]:
    """Получить статистику кэша"""
    total_items = len(_cache)
    dog_cache_items = len(_dog_data_cache)

    return {
        "cache_items": total_items,
        "dog_cache_items": dog_cache_items
    }


# Функции для кэша поиска в БД
def get_dog_db_cache(key: str) -> Optional[int]:
    """Получить ID собаки из кэша БД"""
    if key in _dog_db_cache:
        expiry = _dog_db_cache_expiry.get(key, 0)
        if time.time() < expiry:
            return _dog_db_cache[key]
        else:
            _dog_db_cache.pop(key, None)
            _dog_db_cache_expiry.pop(key, None)
    return None


def set_dog_db_cache(key: str, dog_id: int, ttl: int = 3600):
    """Сохранить ID собаки в кэш БД"""
    _dog_db_cache[key] = dog_id
    _dog_db_cache_expiry[key] = time.time() + ttl


def clear_dog_db_cache():
    """Очистить кэш БД"""
    _dog_db_cache.clear()
    _dog_db_cache_expiry.clear()