# src/wheat_app/core/dependencies.py
"""跨 feature 的全局依赖。"""

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """产出请求级数据库会话。

    约定：会话内所有语句成功则提交，任一语句抛出异常则整体回滚。
    因此 repository 层只 ``add`` / ``flush``，不 commit / rollback。
    """
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
