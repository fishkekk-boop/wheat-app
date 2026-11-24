# src/wheat_app/core/db_errors.py
"""从 SQLAlchemy 数据库异常中提取诊断信息。

仅支持 asyncpg（项目当前唯一的 Postgres 驱动）。若将来切换到
psycopg，约束名在 ``exc.orig.diag.constraint_name``，需要在此处补分支。
"""

import structlog
from sqlalchemy.exc import IntegrityError

logger = structlog.get_logger(__name__)


def get_constraint_name(exc: IntegrityError) -> str | None:
    """返回触发 ``IntegrityError`` 的约束名；提取失败返回 ``None``。

    asyncpg 会把真正的驱动异常挂在 ``exc.orig.__cause__`` 上，
    约束名在 ``constraint_name`` 属性里（``exc.orig`` 本身没有）。
    """
    name = _extract_constraint_name(exc)
    if name is None:
        logger.warning(
            "constraint_name_extraction_failed",
            exc_type=type(exc.orig).__name__,
            # 不记录完整 str(exc.orig)：可能包含 SQL / 数据片段
        )
    return name


def _extract_constraint_name(exc: IntegrityError) -> str | None:
    origin = getattr(exc.orig, "__cause__", None)
    return getattr(origin, "constraint_name", None)
