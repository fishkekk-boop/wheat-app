from functools import lru_cache

import uvicorn
from fastapi import FastAPI

from wheat_app.config import Settings
from wheat_app.features.auth.router import router as auth_router


@lru_cache
def get_settings() -> Settings:
    return Settings()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title=settings.app_name)

    app.include_router(auth_router)

    return app


def run() -> None:
    """开发环境启动入口。"""
    uvicorn.run(
        "wheat_app.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
