# src/wheat_app/core/database.py
"""数据库基础设施：engine / 会话工厂 / ORM 基类 / 命名约定。"""

from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from wheat_app.config import Settings

# 统一的约束/索引命名规则，避免各表自己取名导致不一致。
# 迁移文件里的约束名就是靠这套规则生成的。
NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}

SessionFactory = async_sessionmaker[AsyncSession]


def create_engine_and_session_factory(
    settings: Settings,
) -> tuple[AsyncEngine, SessionFactory]:
    """创建异步 engine 与会话工厂。

    ``expire_on_commit=False``：提交后不把实例属性标记为过期，
    避免在异步上下文里触发意外的懒加载 IO。
    """
    engine = create_async_engine(
        settings.database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,   # 借出连接前先探活，避免拿到被服务端断开的连接
        pool_recycle=1800,    # 定期回收，防止连接长时间空闲被 DB 回收
        echo=settings.debug,
    )
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_factory


metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""

    metadata = metadata


class TimestampMixin:
    """统一提供 ``created_at`` / ``updated_at`` 审计时间戳。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
