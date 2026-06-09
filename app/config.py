"""应用配置管理 — 从 .env 文件和环境变量读取配置。

使用 pydantic-settings 提供类型安全的配置访问。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置，所有值从 .env 文件或环境变量加载。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 阿里云 OSS 配置 ---
    oss_endpoint: str = ""
    oss_access_key: str = ""
    oss_secret: str = ""
    oss_bucket: str = ""
    oss_signed_url_expires: int = 3600  # V4.0 P7-1: 1h 覆盖浏览器缓存窗口

    # --- 数据库配置 ---
    database_url: str = "sqlite:///album.db"

    # --- JWT 配置 ---
    jwt_secret: str = "change_me_in_production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24


settings = Settings()
