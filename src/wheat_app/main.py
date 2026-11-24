# src/wheat_app/main.py
"""应用工厂与启动入口。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI

from wheat_app.config import Env, Settings, get_settings
from wheat_app.core.database import create_engine_and_session_factory
from wheat_app.core.exception_handlers import register_exception_handlers
from wheat_app.core.logging import setup_logging
from wheat_app.core.middleware import RequestContextMiddleware
from wheat_app.features.auth.router import router as auth_router

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """启动时创建进程级资源，关闭时释放。"""
    engine, session_factory = create_engine_and_session_factory(app.state.settings)
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory
    logger.info(
        "app_started", env=app.state.settings.env.value, port=app.state.settings.port
    )

    yield

    await app.state.db_engine.dispose()
    logger.info("app_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """应用工厂：测试可传入自定义 Settings，生产/开发使用 ``get_settings()``。"""
    settings = settings or get_settings()
    setup_logging()

    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    app.state.settings = settings

    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(auth_router)

    @app.get("/", include_in_schema=False)
    async def health() -> dict[str, str]:
        """健康检查。"""
        return {"status": "ok"}

    return app


def run() -> None:
    """开发环境启动入口（``uv run wheat-app``）。"""
    settings = get_settings()
    if settings.env is Env.PROD:
        raise SystemExit(
            "生产请用: uvicorn wheat_app.main:create_app --factory "
            "--host 0.0.0.0 --port 8000 --workers 4"
        )

    uvicorn.run(
        "wheat_app.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        workers=settings.workers if not settings.debug else 1,
        reload=settings.debug,
    )
