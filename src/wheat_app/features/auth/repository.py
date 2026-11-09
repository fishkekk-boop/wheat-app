# src/wheat_app/features/auth/repository.py
"""Auth：数据存储"""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from wheat_app.features.auth.models import AuthIdentity, AuthProvider, User


class AuthRepository(Protocol):
    def get_user_by_id(self, user_id: UUID) -> User | None: ...
    def get_identity(
        self, provider: AuthProvider, identifier: str
    ) -> AuthIdentity | None: ...
    def create_user(self, user: User) -> User: ...
    def create_identity(self, identity: AuthIdentity) -> AuthIdentity: ...
    def touch_last_login(self, identity_id: UUID, at: datetime) -> None: ...
