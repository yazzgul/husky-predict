from .config import settings

# Конфигурация
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0"
]

BREEDARCHIVE_API = "https://siberianhusky.breedarchive.com"
BREEDARCHIVE_DOG_PATH = "/animal/view"

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