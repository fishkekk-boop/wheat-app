# src/wheat_app/features/auth/service.py
"""Auth: 业务异常 + 业务逻辑"""

import secrets

from wheat_app.core.exceptions import ConflictError
from wheat_app.core.security import hash_secret
from wheat_app.features.auth.exceptions import IdentityAlreadyTaken
from wheat_app.features.auth.models import AuthProvider, User
from wheat_app.features.auth.repository import AuthRepository


class AuthService:
    _DEFAULT_NICKNAME_PREFIX = "麦田用户"

    def __init__(self, repo: AuthRepository) -> None:
        self.repo = repo

    def _generate_default_nickname(self) -> str:
        return f"{self._DEFAULT_NICKNAME_PREFIX}_{secrets.token_hex(3)}"

    async def register_with_password(
        self, *, account: str, password: str, nickname: str | None = None
    ) -> User:
        user = await self._create_account(
            provider=AuthProvider.PASSWORD,
            identifier=account,
            nickname=nickname or self._generate_default_nickname(),
            secret_hash=hash_secret(password),
            is_verified=True,
        )
        return user

    async def _create_account(
        self,
        *,
        provider: AuthProvider,
        identifier: str,
        nickname: str,
        secret_hash: str | None = None,
        is_verified: bool = False,
    ) -> User:
        try:
            return await self.repo.create_user_with_identity(
                provider=provider,
                identifier=identifier,
                nickname=nickname,
                secret_hash=secret_hash,
                is_verified=is_verified,
            )
        except ConflictError as e:
            raise IdentityAlreadyTaken() from e
