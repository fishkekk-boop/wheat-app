import structlog
from sqlalchemy.exc import IntegrityError

logger = structlog.get_logger(__name__)


def get_constraint_name(exc: IntegrityError) -> str | None:
    """从 IntegrityError 中提取约束名，asyncpg 路径"""
    name = _try_extract_constraint_name(exc)
    if name is None:
        logger.warning(
            "constraint_name_extraction_failed",
            exc_type=type(exc.orig).__name__,
            # 不记完整 str(exc.orig)，可能有敏感数据
        )
    return name


def _try_extract_constraint_name(exc: IntegrityError) -> str | None:
    """从 IntegrityError 中提取约束名，asyncpg"""
    cause = getattr(exc.orig, "__cause__", None)
    if cause and hasattr(cause, "constraint_name"):
        return cause.constraint_name
    return None
