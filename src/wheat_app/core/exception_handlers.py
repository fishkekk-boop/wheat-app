"""全局异常处理器：把所有异常统一成 ``{error_code, message}`` 的响应体。

分派顺序（Starlette 按"最具体类型优先"匹配）：

    HTTPException        → FastAPI/Starlette 自己抛的（OAuth2 未带 token、404、405）
    DomainError          → 业务规则（4xx），不打堆栈
    InfrastructureError  → 技术故障（5xx），打堆栈
    AppError             → 未分类的业务/基础异常兜底
    RequestValidationError → 422，只回字段与原因，不回显原始输入
    Exception            → 兜底 500，绝不外泄堆栈
"""

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from wheat_app.core.exceptions import AppError, DomainError, InfrastructureError

logger = structlog.get_logger(__name__)

# FastAPI 内建异常没有 error_code，按状态码映射
_HTTP_STATUS_TO_CODE = {
    400: "BAD_REQUEST",
    401: "AUTHENTICATION_FAILED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "ALREADY_EXISTS",
    429: "RATE_LIMITED",
}


def register_exception_handlers(app: FastAPI) -> None:
    """在 app 上注册全局异常处理器。必须在 app 创建之后调用。"""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        _request: Request, exc: HTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": _HTTP_STATUS_TO_CODE.get(
                    exc.status_code, f"HTTP_{exc.status_code}"
                ),
                "message": exc.detail if isinstance(exc.detail, str) else "请求失败",
            },
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
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
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
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
