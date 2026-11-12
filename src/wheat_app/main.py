from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI

from wheat_app.config import Env, Settings, get_settings
from wheat_app.core.exception_handlers import register_exception_handlers
from wheat_app.core.logging import setup_logging
from wheat_app.core.middleware import RequestContextMiddleware
from wheat_app.features.auth.repository import InMemoryAuthRepository
from wheat_app.features.auth.router import router as auth_router

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时创建资源，关闭时释放。"""
    settings = app.state.settings

    # 启动：创建进程级资源
    app.state.auth_repo = InMemoryAuthRepository()
    # 未来：app.state.db_engine = create_async_engine(settings.database_url)
    logger.info("app_started", env=settings.env.value, port=settings.port)
    yield

    # 关闭：释放资源
    # 未来：await app.state.db_engine.dispose()
    logger.info("app_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else get_settings()
    setup_logging()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )

    # 无法依赖注入时需要引用配置，如：中间件、全局异常处理器...
    app.state.settings = settings

    # 聚合请求日志
    app.add_middleware(RequestContextMiddleware)

    # 注册全局异常处理器
    register_exception_handlers(app)

    app.include_router(auth_router)

    return app


def run() -> None:
    """开发环境启动入口。"""
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
