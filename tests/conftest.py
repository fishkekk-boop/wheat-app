# tests/conftest.py
"""共享 fixture：带 lifespan 的 TestClient。

注意：应用在 lifespan 里创建 app.state.auth_repo，
所以必须用 `with TestClient(app)` 才能触发启动/关闭钩子。
"""

import pytest
from fastapi.testclient import TestClient

from wheat_app.main import create_app


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def account() -> dict[str, str]:
    """一组合法的账号密码（8 位以上）。"""
    return {"account": "alice", "password": "pass12345"}
