# src/wheat_app/core/logging.py
import logging
import sys

import structlog

from wheat_app.config import Env, get_settings


def setup_logging() -> None:
    """在 create_app() 中调用一次。开发用彩色输出，生产用 JSON。"""
    settings = get_settings()
    is_dev = settings.env in (Env.DEV, Env.TEST)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
        force=True,
    )

    # structlog 的 processor 管道：从原始 event 到最终输出，依次经过这些处理器
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,  # 合并中间件 bind 的 request_id 等
        structlog.stdlib.add_logger_name,  # 记录 logger 名字
        structlog.stdlib.add_log_level,  # 记录 level
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,  # 异常信息格式化
        structlog.processors.UnicodeDecoder(),
    ]

    if is_dev:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()  # 生产：JSON 输出

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),  # 最终交给标准库 handler
        cache_logger_on_first_use=True,
    )
