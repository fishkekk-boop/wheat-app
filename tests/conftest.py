# tests/conftest.py
"""共享 fixture。

关键点：
1. **测试连独立库** `wheat_test`：在 import 应用之前改 DATABASE_URL，
   否则会污染开发库（`wheat`）。
2. **每个测试前清表**：SQL 版的写操作是真的提交到库的，
   不清理就会出现"上一个测试注册的 alice 让下一个测试拿到 409"。
3. 应用在 lifespan 里创建 engine / session_factory，
   所以必须用 `with TestClient(app)` 触发启动/关闭钩子。
"""

import asyncio
import os
from collections.abc import Iterator

# ⚠️ 必须在 import wheat_app 之前设置：get_settings() 读环境变量优先于 .env
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://wheat:wheat_dev_pwd@127.0.0.1:5432/wheat_test"
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from wheat_app.config import get_settings
from wheat_app.core.database import Base, create_engine_and_session_factory
from wheat_app.main import create_app


def _run(coro):
    """在同步测试里跑一段 async 代码（TestClient 自己用另一个线程的 loop，互不干扰）。"""
    return asyncio.run(coro)


async def _with_session(fn):
    engine, factory = create_engine_and_session_factory(get_settings())
    try:
        async with factory() as session:
            result = await fn(session)
            await session.commit()
            return result
    finally:
        await engine.dispose()


class Db:
    """给测试用的同步数据库小工具。"""

    def truncate_all(self) -> None:
        async def go(session):
            await session.execute(
                text("TRUNCATE auth_identities, users RESTART IDENTITY CASCADE")
            )

        _run(_with_session(go))

    def disable_user(self, account: str) -> None:
        async def go(session):
            await session.execute(
                text(
                    "UPDATE users SET status = 'disabled' "
                    "WHERE id = (SELECT user_id FROM auth_identities WHERE identifier = :a)"
                ),
                {"a": account},
            )

        _run(_with_session(go))

    def get_identity(self, account: str):
        async def go(session):
            row = await session.execute(
                text(
                    "SELECT user_id, last_used_at FROM auth_identities "
                    "WHERE identifier = :a"
                ),
                {"a": account},
            )
            return row.first()

        return _run(_with_session(go))

    def get_user_audit(self, account: str):
        """回读用户表里的审计字段（last_login_at 等）。"""
        async def go(session):
            row = await session.execute(
                text(
                    "SELECT u.last_login_at, u.status FROM users u "
                    "JOIN auth_identities i ON i.user_id = u.id "
                    "WHERE i.identifier = :a"
                ),
                {"a": account},
            )
            return row.first()

        return _run(_with_session(go))

    def add_identity(self, user_id, provider: str, identifier: str) -> None:
        """直接插一条登录方式（测试准备用，绕过 service）。"""
        async def go(session):
            await session.execute(
                text(
                    "INSERT INTO auth_identities (id, user_id, provider, identifier, is_verified) "
                    "VALUES (gen_random_uuid(), :u, :p, :i, true)"
                ),
                {"u": user_id, "p": provider, "i": identifier},
            )

        _run(_with_session(go))

    def set_role(self, account: str, role: str) -> None:
        """测试准备用：直接改用户角色（绕过业务接口）。"""
        async def go(session):
            await session.execute(
                text(
                    "UPDATE users SET role = :r "
                    "WHERE id = (SELECT user_id FROM auth_identities WHERE identifier = :a)"
                ),
                {"r": role, "a": account},
            )

        _run(_with_session(go))

    def get_user_status(self, account: str):
        async def go(session):
            row = await session.execute(
                text(
                    "SELECT u.status, u.role FROM users u "
                    "WHERE u.id = (SELECT user_id FROM auth_identities WHERE identifier = :a)"
                ),
                {"a": account},
            )
            return row.first()

        return _run(_with_session(go))

    def count_identities(self, account: str) -> int:
        async def go(session):
            row = await session.execute(
                text(
                    "SELECT count(*) FROM auth_identities i "
                    "JOIN users u ON u.id = i.user_id WHERE u.nickname IS NOT NULL "
                    "AND i.user_id = (SELECT user_id FROM auth_identities WHERE identifier = :a LIMIT 1)"
                ),
                {"a": account},
            )
            return row.scalar()

        return _run(_with_session(go))

    def delete_user(self, account: str) -> None:
        async def go(session):
            await session.execute(
                text(
                    "DELETE FROM users "
                    "WHERE id = (SELECT user_id FROM auth_identities WHERE identifier = :a)"
                ),
                {"a": account},
            )

        _run(_with_session(go))


@pytest.fixture
async def factory():
    """给仓库/服务层测试用的 session 工厂（用完释放）。"""
    engine, session_factory = create_engine_and_session_factory(get_settings())
    try:
        yield session_factory
    finally:
        await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _db_schema():
    """整个测试会话开始前，按 ORM 元数据重建表结构。"""

    async def prepare():
        engine, _ = create_engine_and_session_factory(get_settings())
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    _run(prepare())
    yield


@pytest.fixture(autouse=True)
def _clean_db(_db_schema) -> None:
    """每个测试前清空业务表（SQL 版的写入是真提交的，必须隔离）。"""
    Db().truncate_all()


@pytest.fixture
def db(_db_schema) -> Db:
    return Db()


@pytest.fixture
def client(_db_schema) -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def account() -> dict[str, str]:
    """一组合法的账号密码（8 位以上）。"""
    return {"account": "alice", "password": "pass12345"}
