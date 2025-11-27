
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
