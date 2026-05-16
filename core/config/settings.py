"""Centralized application configuration.

Each backend has its own ``BaseSettings`` subclass with an ``env_prefix`` so env
vars stay flat (``POSTGRES_HOST``, ``NEO4J_URI``) instead of nested-delimiter
notation. The top-level :class:`Settings` composes them via ``Field`` defaults.
``get_settings()`` is cached so callers in hot paths don't re-parse the env.

SecretStr is used for every password — call ``.get_secret_value()`` only at the
boundary where the secret is consumed (DSN construction).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "testing", "production"]


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="POSTGRES_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    host: str = "localhost"
    port: int = 5432
    db: str = "platform"
    user: str = "platform"
    password: SecretStr = SecretStr("platform")
    pool_size: int = 10
    max_overflow: int = 20
    echo: bool = False

    @property
    def dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.db}"
        )

    @property
    def sync_dsn(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.db}"
        )


class Neo4jSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NEO4J_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: SecretStr = SecretStr("platform_neo4j")
    database: str = "neo4j"
    max_connection_pool_size: int = 50


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: SecretStr | None = None
    max_connections: int = 50

    @property
    def url(self) -> str:
        auth = f":{self.password.get_secret_value()}@" if self.password is not None else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class LoggingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    level: str = "INFO"
    json: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Environment = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=list)

    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
