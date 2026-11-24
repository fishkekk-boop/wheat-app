# src/wheat_app/core/dependencies.py
"""全局依赖：get_db、分页"""

from collections.abc import AsyncGenerator

import structlog
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

# TODO：暂时还没想到怎么打 logger
logger = structlog.get_logger(__name__)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
