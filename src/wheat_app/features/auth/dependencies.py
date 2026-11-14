# src/wheat_app/features/auth/ dependencies.py
"""Auth：依赖"""

from typing import Annotated

from fastapi import Depends, Request

from wheat_app.features.auth.repository import AuthRepository
from wheat_app.features.auth.service import AuthService


def get_auth_repo(request: Request) -> AuthRepository:
    """从 app.state 取 repo，而非模块级单例。

    每个 create_app() 拥有独立存储：
    - 测试：每个 fixture 一份空 repo，测试间不串数据
    - 生产：单进程一份，随 app 生命周期创建/释放

    repo 由 lifespan 在启动时写入 app.state。
    """
    return request.app.state.auth_repo


def get_auth_service(
    repo: Annotated[AuthRepository, Depends(get_auth_repo)],
) -> AuthService:
    return AuthService(repo)
