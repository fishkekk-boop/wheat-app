# src/wheat_app/core/middleware.py
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = structlog.get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """为每个请求生成/透传 request_id，绑定到 structlog contextvars。"""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex

        # 必须在 try 之前清空，防止上一个请求的 context 泄漏到当前请求
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "request_completed",
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            response.headers["X-Request-ID"] = request_id  # 回传给客户端，方便排查
            return response
        finally:
            # 即使 call_next 抛异常，也必须清理，否则下一个请求会继承错误的 request_id[reference:5]
            structlog.contextvars.clear_contextvars()
