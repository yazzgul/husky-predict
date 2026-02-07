from .config import settings

# Конфигурация
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0"
]

BREEDARCHIVE_API = "https://siberianhusky.breedarchive.com"
BREEDARCHIVE_DOG_PATH = "/animal/view"
# Добавим конфигурацию для авторизации BreedArchive
BREEDARCHIVE_SEARCH_URL = "https://siberianhusky.breedarchive.com/ng_animal/data"

BREEDBASE_API = "https://breedbase.ru"
BREEDBASE_DOG_PATH = "/rodoslovnye/husky"

HUSKY_PEDIGREE_NET_API = "https://husky.pedigre.net/en"
HUSKY_PEDIGREE_NET_DOG_PATH = "/details.php?id="
HUSKY_PEDIGREE_NET_DOG_LIST_PATH = "/lista.php"

HEADERS = {
    "oam_remote_user": settings.BREEDARCHIVE_USER,
    "accept": "application/json",
    "x-requested-with": "XMLHttpRequest"
}
DELAY_RANGE = (1, 3)  # Случайная задержка между запросами в секундах
MAX_RETRIES = 3


# В parsersConfig.py заменим ZOOPORTAL_COOKIES на ZOOPORTAL_COOKIES_STRING
ZOOPORTAL_BASE_URL = "https://zooportal.pro"
ZOOPORTAL_DOG_PATH = "/pedigree/view"
ZOOPORTAL_SEARCH_PATH = "/pedigree/"

# Куки для авторизации (необходимо будет настроить через settings)
# ZOOPORTAL_COOKIES = {
#     "PHPSESSID": settings.ZOOPORTAL_PHPSESSID if hasattr(settings, 'ZOOPORTAL_PHPSESSID') else "",
#     "BITRIX_SM_LOGIN": settings.ZOOPORTAL_LOGIN if hasattr(settings, 'ZOOPORTAL_LOGIN') else "",
#     "BITRIX_SM_SALE_UID": settings.ZOOPORTAL_SALE_UID if hasattr(settings, 'ZOOPORTAL_SALE_UID') else "",
# }
ZOOPORTAL_COOKIES = {
    "PHPSESSID": settings.ZOOPORTAL_PHPSESSID if hasattr(settings, "ZOOPORTAL_PHPSESSID") else "",

    "BITRIX_SM_LOGIN": settings.ZOOPORTAL_LOGIN if hasattr(settings, "ZOOPORTAL_LOGIN") else "",
    "BITRIX_SM_UIDL": settings.ZOOPORTAL_BITRIX_SM_UIDL if hasattr(settings, "ZOOPORTAL_BITRIX_SM_UIDL") else "",
    "BITRIX_SM_UIDH": settings.ZOOPORTAL_BITRIX_SM_UIDH if hasattr(settings, "ZOOPORTAL_BITRIX_SM_UIDH") else "",

    "BITRIX_SM_GUEST_ID": settings.ZOOPORTAL_BITRIX_SM_GUEST_ID if hasattr(settings, "ZOOPORTAL_BITRIX_SM_GUEST_ID") else "",
    "BITRIX_SM_SALE_UID": settings.ZOOPORTAL_SALE_UID if hasattr(settings, "ZOOPORTAL_SALE_UID") else "",
}

# Куки для авторизации BreedArchive
BREEDARCHIVE_COOKIES = {
    "__eoiID": settings.BREEDARCHIVE_EOIID if hasattr(settings, 'BREEDARCHIVE_EOIID') else "",
    "__gadsID": settings.BREEDARCHIVE_GADSID if hasattr(settings, 'BREEDARCHIVE_GADSID') else "",
    "__gpiUID": settings.BREEDARCHIVE_GPUID if hasattr(settings, 'BREEDARCHIVE_GPUID') else "",
    "_ga": settings.BREEDARCHIVE_GA if hasattr(settings, 'BREEDARCHIVE_GA') else "",
    "_gid": settings.BREEDARCHIVE_GID if hasattr(settings, 'BREEDARCHIVE_GID') else "",
    "cookieSettings": settings.BREEDARCHIVE_COOKIE_SETTINGS if hasattr(settings, 'BREEDARCHIVE_COOKIE_SETTINGS') else "",
    "session_tba_v3": settings.BREEDARCHIVE_SESSION_TBA_V3 if hasattr(settings, 'BREEDARCHIVE_SESSION_TBA_V3') else "",
}

# Количество собак на странице поиска
ZOOPORTAL_PAGE_SIZE = 11

CACHE_CONFIG = {
    'breedarchive_search_ttl': 300,  # 5 минут
    'breedarchive_processed_ttl': 600,  # 10 минут
    'max_cache_size': 10000,  # Максимальное количество записей
}