from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import init_db
from app.api.v1.api import api_router
from app.api.v1.auth_google import router as auth_google_router
from app.services.scheduler import start_scheduler, shutdown_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Lifespan - 앱 시작/종료 시 실행
    """
    # Startup
    start_scheduler(interval_minutes=5)
    yield
    # Shutdown
    shutdown_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="TONO Operation Backend",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # DB 초기화
    init_db()

    # v1 REST API
    app.include_router(api_router, prefix="/api/v1")

    # 기타 API
    app.include_router(auth_google_router)
    
    return app

app = create_app()
