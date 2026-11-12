import uvicorn
from fastapi import FastAPI

from wheat_app.config import Env, Settings, get_settings
from wheat_app.core.exception_handlers import register_exception_handlers
from wheat_app.features.auth.repository import InMemoryAuthRepository
from wheat_app.features.auth.router import router as auth_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug)
    # 无法依赖注入时需要引用配置，如：中间件、全局异常处理器...
    app.state.settings = settings
    # 每个 app 独立一个 repo（内存版专用），防止测试数据污染
    app.state.auth_repo = InMemoryAuthRepository()
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
