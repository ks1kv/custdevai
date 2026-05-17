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

    # --- Reports + Web SPA (Phase 4, FR-RPT-08, FR-WEB-*) -------------------
    reports_storage_dir: str = "/var/lib/custdevai/reports"
    cookie_secure: bool | None = None  # None → derive from is_production
    cookie_samesite: str = "strict"  # "strict" | "lax" | "none"
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    spa_dist_dir: str = ""  # Phase 5: путь к собранному dist/; в dev пуст
    web_base_url: str = "http://localhost:5173"  # для построения URL отчётов в push

    # --- Pagination (NFR-PRF-03) --------------------------------------------
    default_page_size: int = Field(default=50, gt=0)
    max_page_size: int = Field(default=100, gt=0)

    # --- Brute-force protection (FR-AUTH-08) --------------------------------
    bruteforce_max_attempts: int = 5
    bruteforce_window_seconds: int = 600
    bruteforce_lock_seconds: int = 900

    # --- ML modules (FR-SENT-*, FR-TOP-*, NFR-COR-01, NFR-SEC-09) -----------
    # blanchefort/rubert-base-cased-sentiment — pre-fine-tuned 3-class
    # RuBERT-голова для русского sentiment (NEUTRAL/POSITIVE/NEGATIVE).
    # Дефолт `DeepPavlov/rubert-base-cased` без обучения classifier-head
    # давал случайные прогнозы — все ответы получали NEUTRAL/LOW_CONFIDENCE.
    # Для собственного fine-tune на RuSentNE-2023 (FR-SENT-07) задайте
    # SENTIMENT_MODEL_PATH с локальным каталогом весов.
    sentiment_model_name: str = "blanchefort/rubert-base-cased-sentiment"
    sentiment_confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    sentiment_random_seed: int = 42
    sentiment_batch_size: int = Field(default=16, ge=1, le=128)
    topic_embedder_name: str = "intfloat/multilingual-e5-base"
    topic_default_count: int = Field(default=10, ge=3, le=20)
    topic_min_count: int = Field(default=3, ge=2)
    topic_max_count: int = Field(default=20, le=50)
    topic_random_seed: int = 42
    ml_model_cache_dir: str = "/models"
    transformers_offline: bool = False
    # Сколько минут позволяем кампании быть в analysis_status=RUNNING до
    # того, как periodic-таска ml.sweep_stuck_running перепоставит её в
    # FAILED. Запас относительно NFR-PRF-04 (≤10 мин на 200 сессий).
    ml_stuck_running_minutes: int = Field(default=20, ge=5, le=240)
    # Минимальное число (русскоязычных) ответов для запуска BERTopic.
    # На корпусе меньше — UMAP падает на spectral_layout: «k >= N», т.е.
    # размерность многообразия больше числа точек. Тематическое
    # моделирование на 4-5 точках бессмысленно даже если бы работало,
    # поэтому ниже порога просто пропускаем topics (sentiment всё равно
    # сохраняется), отчёт получает раздел «темы недоступны».
    topic_min_corpus_size: int = Field(default=10, ge=2, le=200)

    # --- Celery (FR-API-04) -------------------------------------------------
    celery_broker_url: str = ""
    celery_result_backend: str = ""
    celery_task_always_eager: bool = False  # True в тестах

    # --- Phase 5: backups, sweepers, SMTP, deeplinks ------------------------
    # FR-DB-08 / NFR-REL-03: ежедневный pg_dump в этот каталог. В docker-compose
    # смонтирован как volume backups_storage. RPO ≤ 24 ч обеспечивается
    # ежесуточным расписанием Celery beat.
    backup_storage_dir: str = "/var/lib/custdevai/backups"
    backup_retention_count: int = Field(default=7, ge=1, le=90)
    # FR-BOT-05: sweeper переводит active → interrupted после неактивности.
    session_inactive_hours: int = Field(default=48, gt=0)
    # Путь к fine-tuned весам RuBERT (FR-SENT-07). None → pretrained baseline.
    sentiment_model_path: str | None = None
    # FR-AUTH-06: SMTP-доставка временного пароля.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True

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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_cookie_secure(self) -> bool:
        """В production cookie всегда Secure; в dev — по флагу или False."""
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.is_production


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton-фабрика. В тестах подменяется через dependency_overrides."""
    return Settings()  # type: ignore[call-arg]
