import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from wheat_app.core.exceptions import AppError, DomainError, InfrastructureError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """在 app 上注册全局异常处理器。必须在 app 创建之后调用。"""

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(InfrastructureError)
    async def infra_error_handler(
        request: Request,
        exc: InfrastructureError,
    ) -> JSONResponse:
        logger.exception(
            "基础设施异常: %s %s -> %s",
            request.method,
            request.url.path,
            exc,
        )
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.exception(
            "未分类应用异常: %s %s -> %s",
            request.method,
            request.url.path,
            exc,
        )
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc):
        logger.exception(
            "未捕获异常: %s %s -> %s",
            request.method,
            request.url.path,
            exc,
        )
        return JSONResponse(
            status_code=500,
            content={"error_code": "INTERNAL_ERROR", "message": "服务内部错误"},
        )
