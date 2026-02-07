
import asyncio
from celery import Celery
from tasks.update_data import update_all_sources
from opentelemetry.instrumentation.celery import CeleryInstrumentor

celery_app = Celery(
    "pedigree",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1"
)

CeleryInstrumentor().instrument()

celery_app.conf.timezone = "Europe/Moscow"
celery_app.conf.beat_schedule = {}  # будет заполнено ниже


@celery_app.task
def run_data_update():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(update_all_sources())

# Добавление для Зоопортал
# @celery_app.task
# def parse_zooportal_recent_dogs():
#     with tracer.start_as_current_span("celery_parse_zooportal_recent_dogs"):
#         try:
#             resp = requests.get(f"{API_URL}/api/zooportal/parse-page/1")
#             resp.raise_for_status()
#             logging.info(f"Zooportal recent parse: {resp.json()}")
#         except Exception as e:
#             logging.error(f"Error in parse_zooportal_recent_dogs: {e}")
#
# # В beat_schedule добавить:
# 'parse-zooportal-recent-dogs-weekly': {
#     'task': 'tasks.update_data.parse_zooportal_recent_dogs',
#     'schedule': crontab(hour=2, minute=0, day_of_week='monday'),
# },