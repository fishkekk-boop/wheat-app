# src/wheat_app/features/auth/ dependencies.py
"""Auth：依赖"""

from wheat_app.features.auth.repository import AuthRepository, InMemoryAuthRepository
from wheat_app.features.auth.service import AuthService

# 数据存储方式，当前为内存，后续追加数据库
_auth_repo: AuthRepository = InMemoryAuthRepository()


def get_auth_service() -> AuthService:
    return AuthService(_auth_repo)
