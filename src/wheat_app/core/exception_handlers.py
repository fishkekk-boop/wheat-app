import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from wheat_app.core.exceptions import AppError, DomainError, InfrastructureError

logger = structlog.get_logger(__name__)


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
            "infra_error",
            method=request.method,
            path=request.url.path,
            error=str(exc),
        )
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error_code": "HTTP_ERROR", "message": exc.detail},
            headers=exc.headers,
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.exception(
            "unclassified_app_error",
            method=request.method,
            path=request.url.path,
            error=str(exc),
        )
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        # 只返回"哪个字段、什么错误"，不回显原始输入（防密码泄露）
        errors = [
            {
                "field": ".".join(str(loc) for loc in e["loc"] if loc != "body"),
                "message": e["msg"],
            }
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "VALIDATION_ERROR",
                "message": "请求参数校验失败",
                "errors": errors,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc):
        logger.exception(
            "unhandled_exception",
            method=request.method,
            path=request.url.path,
            error=str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={"error_code": "INTERNAL_ERROR", "message": "服务内部错误"},
        )
