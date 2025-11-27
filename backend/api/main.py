# import sys
# from pathlib import Path
#
# from sqlmodel import SQLModel, text
#
# root_path = Path(__file__).parent.parent
# sys.path.append(str(root_path))
#
# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
#
# from core.config import settings
# from core.database import engine
# from api.routers import dogs_router, breedbase_router, breedarchive_router, huskypedigree_router, pedigree_router, ofa_router
#
# import logging
# from logging.handlers import RotatingFileHandler
#
# from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
# from opentelemetry.instrumentation.requests import RequestsInstrumentor
# from opentelemetry.sdk.resources import SERVICE_NAME, Resource
# from opentelemetry.sdk.trace import TracerProvider
# from opentelemetry.sdk.trace.export import BatchSpanProcessor
# from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
# from opentelemetry import trace
#
# app = FastAPI(title=settings.PROJECT_NAME)
#
# # Настройка CORS
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=settings.BACKEND_CORS_ORIGINS,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
#
# # Конфигурация логирования
# def setup_logging():
#     log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
#     formatter = logging.Formatter(log_format)
#
#     # Файловый обработчик
#     file_handler = RotatingFileHandler(
#         'app.log',
#         maxBytes=1024*1024*5,  # 5 MB
#         backupCount=3,
#         encoding='utf-8'
#     )
#     file_handler.setFormatter(formatter)
#     file_handler.setLevel(logging.INFO)
#
#     # Настройка корневого логгера
#     root_logger = logging.getLogger()
#     root_logger.addHandler(file_handler)
#     root_logger.setLevel(logging.DEBUG)
#
#     # Настройка логгеров Uvicorn и FastAPI
#     uvicorn_access = logging.getLogger("uvicorn.access")
#     uvicorn_access.handlers = [file_handler]
#     uvicorn_access.propagate = False
#
#     uvicorn_error = logging.getLogger("uvicorn.error")
#     uvicorn_error.handlers = [file_handler]
#     uvicorn_error.propagate = False
#
# # Глобальная переменная для управления сессией (варьируйте под свою архитектуру)
# # session: AsyncSession | None = None
#
# # async def graceful_shutdown():
# #     global session
# #     if session:
# #         with suppress(Exception):  # Игнорируем ошибки, если сессия уже закрыта
# #             await session.commit()
# #             await session.close()
# #         print("Session committed and closed!")
#
# # def handle_signal(signum, frame):
# #     print(f"Received signal {signum}, shutting down...")
# #     loop = asyncio.get_event_loop()
# #     loop.create_task(graceful_shutdown())
#
# # # В месте инициализации приложения (например, в main())
# # def setup_graceful_shutdown():
# #     loop = asyncio.get_event_loop()
# #     for sig in (signal.SIGINT, signal.SIGTERM):
# #         loop.add_signal_handler(sig, handle_signal, sig, None)
#
# @app.on_event("startup")
# async def startup():
#     async with engine.begin() as conn:
#
#         # await conn.execute(text("SET session_replication_role = replica;"))
#         # await conn.run_sync(SQLModel.metadata.drop_all)
#         # await conn.execute(text("SET session_replication_role = DEFAULT;"))
#         # await conn.run_sync(SQLModel.metadata.create_all)
#
#         # Создание таблиц при необходимости
#         # await conn.run_sync(SQLModel.metadata.create_all) # Не нужно т.к. добавлены миграции
#         setup_logging()
#
#     resource = Resource(attributes={
#         SERVICE_NAME: "husky-pedigree-backend"
#     })
#     provider = TracerProvider(resource=resource)
#     trace.set_tracer_provider(provider)
#     otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces", insecure=True)
#     span_processor = BatchSpanProcessor(otlp_exporter)
#     provider.add_span_processor(span_processor)
#
# @app.on_event("shutdown")
# def shutdown_event():
#     logger = logging.getLogger(__name__)
#     logger.info("Application shutdown")
#
# # Добавьте этот endpoint
# @app.get("/")
# async def root():
#     return {
#         "message": "Pedigree API is running!",
#         "version": "1.0.0",
#         "docs": "/docs"
#     }
#
# @app.get("/api/health")
# async def health_check():
#     return {"status": "healthy", "service": "pedigree-backend"}
#
# # Подключение роутеров
# app.include_router(dogs_router, prefix="/api/v1/dogs")
# app.include_router(pedigree_router, prefix="/api/v1/pedigree", tags=["dog-pedigree"])
# app.include_router(breedarchive_router, prefix="/api/v1/breedarchive", tags=["breedarchive"])
# app.include_router(breedbase_router, prefix="/api/v1/breedbase", tags=["breedbase"])
# app.include_router(huskypedigree_router, prefix="/api/v1/huskypedigree", tags=["huskypedigree"])
# app.include_router(ofa_router, prefix="/api/v1/ofa")
#
# FastAPIInstrumentor.instrument_app(app)
# RequestsInstrumentor().instrument()
#
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
import sys
from pathlib import Path

from sqlmodel import SQLModel, text

root_path = Path(__file__).parent.parent
sys.path.append(str(root_path))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.database import engine
from api.routers import dogs_router, breedbase_router, breedarchive_router, huskypedigree_router, pedigree_router, \
    ofa_router

import logging
from logging.handlers import RotatingFileHandler

# OpenTelemetry - ОНО ТОРМОЗИТ (?)
# from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
# from opentelemetry.instrumentation.requests import RequestsInstrumentor
# from opentelemetry.sdk.resources import SERVICE_NAME, Resource
# from opentelemetry.sdk.trace import TracerProvider
# from opentelemetry.sdk.trace.export import BatchSpanProcessor
# from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
# from opentelemetry import trace

app = FastAPI(title=settings.PROJECT_NAME)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Упрощенное логирование
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


@app.on_event("startup")
async def startup():
    # Простая логика из startup
    print("Starting Pedigree Backend...")
    setup_logging()

    # Простая проверка БД
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            print("Database connection successful")
    except Exception as e:
        print(f"Database connection failed: {e}")


@app.on_event("shutdown")
def shutdown_event():
    print("Application shutdown")


# Endpoints
@app.get("/")
async def root():
    return {
        "message": "Pedigree API is running!",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "pedigree-backend"}


# Подключение роутеров
app.include_router(dogs_router, prefix="/api/v1/dogs")
app.include_router(pedigree_router, prefix="/api/v1/pedigree", tags=["dog-pedigree"])
app.include_router(breedarchive_router, prefix="/api/v1/breedarchive", tags=["breedarchive"])
app.include_router(breedbase_router, prefix="/api/v1/breedbase", tags=["breedbase"])
app.include_router(huskypedigree_router, prefix="/api/v1/huskypedigree", tags=["huskypedigree"])
app.include_router(ofa_router, prefix="/api/v1/ofa")

# instrumentation - ОНО ТОРМОЗИТ (?)
# FastAPIInstrumentor.instrument_app(app)
# RequestsInstrumentor().instrument()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")