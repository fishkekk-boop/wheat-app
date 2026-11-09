# src/wheat_app/config.py
"""全局配置"""

import os
from enum import StrEnum
from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


_env_file = f".env.{os.getenv('APP_ENV', 'dev')}"


class Settings(BaseSettings):
    # 定义配置字段，带类型注解，可给默认值
    app_name: str = "Wheat-APP"
    database_url: str = "sqlite:///./wheat.db"
    secret_key: SecretStr
    debug: bool = False
    env: Env = Field(default=Env.DEV, validation_alias=AliasChoices("APP_ENV", "ENV"))
    host: str = "127.0.0.1"
    port: int = 8000
    workers: int = 1

    # 配置如何从环境中读取
    model_config = SettingsConfigDict(
        env_file=(".env", _env_file),
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略未定义的环境变量
    )

    @field_validator("env", mode="before")
    @classmethod
    def _normalize_env(cls, v: object) -> object:
        """允许 APP_ENV / ENV 以任意大小写传入，统一转小写再校验枚举。"""
        if isinstance(v, str):
            return v.lower()
        return v

    @model_validator(mode="after")
    def _check_prod(self) -> "Settings":
        if self.env is Env.PROD:
            if self.debug:
                raise ValueError("生产环境不能开 debug")
            if len(self.secret_key.get_secret_value()) < 32:
                raise ValueError("生产环境 secret_key 至少 32 位")
        return self


@lru_cache
def get_settings() -> Settings:
    """
    首次调用 get_settings 之后，每次调用都是缓存
    要测试修改配置需要清除缓存：get_settings.cache_clear()
    """
    return Settings()  # type: ignore[call-arg]
