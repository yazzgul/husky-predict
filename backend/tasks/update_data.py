import asyncio
from httpx import AsyncClient
from parsers import breedarchive, breedbase, huskypedigre
from core.database import get_async_session
from utils.cache import cache
from .celery import celery_app
import requests
import logging
from celery.schedules import crontab
from opentelemetry import trace

API_URL = "http://localhost:8000"

tracer = trace.get_tracer(__name__)

async def update_all_sources():
    async with AsyncClient() as session:
        await asyncio.gather(
            update_breedarchive(session),
            update_breedbase(session),
            update_huskypedigre(session)
        )
    await cache.clear_pattern("dogs:*")

async def update_breedarchive(session):
    data = await breedarchive.fetch_breedarchive_data(session)

async def update_breedbase(session):
    data = await breedbase.fetch_breedbase_data(session)

async def update_huskypedigre(session):
    data = await huskypedigre.fetch_huskypedigre_data(session)

@celery_app.task
def parse_breedarchive_recent_dogs():
    with tracer.start_as_current_span("celery_parse_breedarchive_recent_dogs"):
        try:
            resp = requests.get(f"{API_URL}/api/breedarchive/dog/parseRecentPage")
            resp.raise_for_status()
            logging.info(f"Breedarchive recent parse: {resp.json()}")
        except Exception as e:
            logging.error(f"Error in parse_breedarchive_recent_dogs: {e}")

@celery_app.task
def full_scrape_all_sites():
    with tracer.start_as_current_span("celery_full_scrape_all_sites"):
        try:
            # breedarchive
            count = 0
            for page in range(0, 100_000, 100):
                resp = requests.get(f"{API_URL}/api/breedarchive/dog/parseList", params={"page": page, "per_page": 100, "max_count": 100_000})
                resp.raise_for_status()
                data = resp.json()
                count += data.get("processed_dogs_count", 0)
                if count >= 100_000:
                    break

            # breedbase.ru
            count = 0
            for page in range(0, 50_000, 100):
                resp = requests.get(f"{API_URL}/api/breedbase/parseList", params={"page": page, "per_page": 100, "max_count": 50_000})
                resp.raise_for_status()
                data = resp.json()
                count += data.get("processed_dogs_count", 0)
                if count >= 50_000:
                    break

            # husky.pedigre.net
            count = 0
            for page in range(1, 2600, 100):
                resp = requests.get(f"{API_URL}/api/huskypedigree/parseList", params={"page": page, "per_page": 100, "max_count": 2600})
                resp.raise_for_status()
                data = resp.json()
                count += data.get("processed_dogs_count", 0)
                if count >= 2600:
                    break

            logging.info("Full scrape finished")
        except Exception as e:
            logging.error(f"Error in full_scrape_all_sites: {e}")

celery_app.conf.beat_schedule = {
    'parse-breedarchive-recent-dogs-daily': {
        'task': 'tasks.update_data.parse_breedarchive_recent_dogs',
        'schedule': crontab(hour=3, minute=0),  # каждый день в 3:00
    },
    'full-scrape-all-sites-weekly': {
        'task': 'tasks.update_data.full_scrape_all_sites',
        'schedule': crontab(hour=4, minute=0, day_of_week='sunday'),  # каждое воскресенье в 4:00
    },
}