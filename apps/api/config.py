"""Конфигурация приложения, читаемая из переменных окружения через pydantic-settings.

Все секреты обязательны и валидируются на старте: некорректные значения
приводят к падению процесса до инициализации FastAPI (NFR-SEC-06: запрет на
коммит секретов; NFR-SEC-02: bcrypt cost factor ≥ 12).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production"]


class Settings(BaseSettings):
    """Срез переменных окружения, нужных Phase 1 (api + auth + db)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---------------------------------------------------------
    environment: Environment = "development"
    log_level: str = "INFO"
    timezone: str = "Asia/Novosibirsk"

    # --- PostgreSQL ----------------------------------------------------------
    postgres_user: str = "custdev"
    postgres_password: str = Field(min_length=1)
    postgres_db: str = "custdevai"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    database_url: PostgresDsn | None = None

    # --- Redis ---------------------------------------------------------------
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_url: RedisDsn | None = None

    # --- API -----------------------------------------------------------------
    api_port: int = 8000

    # --- JWT / bcrypt --------------------------------------------------------
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_ttl_minutes: int = Field(default=15, gt=0)
    jwt_refresh_token_ttl_days: int = Field(default=7, gt=0)
    bcrypt_cost_factor: int = Field(default=12, ge=12, le=16)

    # --- Pseudonymization (FR-DB-03) ----------------------------------------
    pseudonym_master_salt: str = Field(min_length=32)

    # --- Telegram bot (FR-BOT-*) -------------------------------------------
    telegram_bot_token: str = ""
    telegram_webhook_url: str = ""
    telegram_webhook_secret: str = ""
    telegram_notify_bot_token: str = ""

    # --- Pagination (NFR-PRF-03) --------------------------------------------
    default_page_size: int = Field(default=50, gt=0)
    max_page_size: int = Field(default=100, gt=0)

    # --- Brute-force protection (FR-AUTH-08) --------------------------------
    bruteforce_max_attempts: int = 5
    bruteforce_window_seconds: int = 600
    bruteforce_lock_seconds: int = 900

    @field_validator("jwt_algorithm")
    @classmethod
    def _check_algo(cls, v: str) -> str:
        allowed = {"HS256", "HS384", "HS512"}
        if v not in allowed:
            raise ValueError(f"jwt_algorithm must be one of {allowed}")
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_database_url(self) -> str:
        """Async URL для SQLAlchemy. Если DATABASE_URL не задан — собираем сами."""
        if self.database_url is not None:
            return str(self.database_url)
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_redis_url(self) -> str:
        if self.redis_url is not None:
            return str(self.redis_url)
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton-фабрика. В тестах подменяется через dependency_overrides."""
    return Settings()  # type: ignore[call-arg]
