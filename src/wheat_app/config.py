from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 定义配置字段，带类型注解，可给默认值
    app_name: str = "My Enterprise App"
    database_url: str = "sqlite:///./test.db"
    secret_key: str = "change-me-in-production"
    debug: bool = False

    # 配置如何从环境中读取
    model_config = SettingsConfigDict(
        env_file=".env",  # 自动读取 .env 文件
        env_file_encoding="utf-8",
        case_sensitive=False,  # 环境变量名大小写不敏感
        extra="ignore",  # 忽略未定义的环境变量
    )
