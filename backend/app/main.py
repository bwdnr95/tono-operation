from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import init_db
from app.api.v1.api import api_router
from app.api.v1.auth_google import router as auth_google_router
from app.api.v1.webhooks import router as webhook_router
from app.api.v1 import properties
from app.api.v1 import ota_listings



def create_app() -> FastAPI:
    app = FastAPI(
        title="TONO Operation Backend",
        version="0.1.0",
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
    app.include_router(webhook_router)

    # Property 관련 API
    app.include_router(properties.router)

        # OTA 리스팅 매핑 관련 API
    app.include_router(ota_listings.router)

    return app

app = create_app()
