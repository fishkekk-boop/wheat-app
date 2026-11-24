from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from wheat_app.config import Settings

POSTGRES_NAMING_CONVENTION = {
    # 统一约束命名
    "ix": "%(column_0_label)s_idx",  # 普通索引
    "uq": "%(table_name)s_%(column_0_name)s_key",  # 唯一约束
    "ck": "%(table_name)s_%(constraint_name)s_check",  # 检查约束
    "fk": "%(table_name)s_%(column_0_name)s_fkey",  # 外键约束
    "pk": "%(table_name)s_pkey",  # 主键约束
}


def create_engine_and_session_factory(settings: Settings):
    """创建异步会话工厂"""
    engine = create_async_engine(
        settings.database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # 使用前检查连接有效性
        pool_recycle=1800,  # 定期回收连接，防止被数据库断开
        echo=settings.debug,
    )
    # 异步会话工厂
    # expire_on_commit=False ：提交后不会过期属性，避免异步下意外触发懒加载 IO
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_factory


metadata = MetaData(naming_convention=POSTGRES_NAMING_CONVENTION)


class Base(AsyncAttrs, DeclarativeBase):
    """所有 ORM 模型的基类。
    AsyncAttrs 提供 awaitable_attrs，用于异步下显式触发懒加载。
    """

    metadata = metadata


class TimestampMixin:
    """统一提供 created_at / updated_at，避免每个模型重复定义。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
