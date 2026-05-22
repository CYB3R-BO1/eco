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

from pydantic import BaseModel, Field, SecretStr
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


class FirewallSettings(BaseSettings):
    """Knobs for the AI Firewall (Phase 4).

    Defaults are deliberately conservative: block at ≥0.85, sanitize at
    ≥0.65, review at ≥0.40, allow otherwise. ``detection_timeout_ms``
    bounds the entire pipeline (including the LLM-classifier slot, which is
    a stub in Phase 4 but kept inside the timeout for future-proofing).
    ``finding_weight_floor`` controls which fired rules become Findings in
    the graph — rules below the floor still fire and count toward the
    score, they just don't materialize as Finding nodes.
    """

    model_config = SettingsConfigDict(
        env_prefix="FIREWALL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    enabled: bool = True
    max_prompt_bytes: int = 32_000
    max_output_bytes: int = 64_000
    detection_timeout_ms: int = 2_000

    block_threshold: float = 0.85
    sanitize_threshold: float = 0.65
    review_threshold: float = 0.40

    finding_weight_floor: float = 0.50
    pii_masking_enabled: bool = True


class LLMSettings(BaseSettings):
    """LLM provider knobs (Phase 5).

    When ``api_key`` is empty the platform uses ``StubLLM`` — deterministic
    templated completions, zero network calls. Tests always run under this
    mode so CI never needs an API key. When a key is set, ``OpenAIClient``
    talks to any OpenAI-compatible endpoint (``base_url`` defaults to OpenAI;
    point at a self-hosted proxy by overriding it).

    The token budgets enforce ``PLAN.md`` §3.5: investigations cannot burn
    more than ``max_tokens_per_investigation`` tokens across all agent runs.
    """

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    provider: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    api_key: SecretStr = SecretStr("")
    model: str = "gpt-4o-mini"
    request_timeout_seconds: int = 60
    max_tokens_per_request: int = 4_096
    max_tokens_per_investigation: int = 50_000
    max_retries: int = 2

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key.get_secret_value().strip())


class OrchestrationSettings(BaseSettings):
    """Agent orchestration knobs (Phase 5).

    These bound runaway workflows (``PLAN.md`` §3.5) — every workflow has a
    hard wall-clock ceiling, every agent run a per-agent timeout, every
    investigation a bounded memory footprint. Circuit-breaker defaults trip
    after five consecutive failures within a one-minute window.
    """

    model_config = SettingsConfigDict(
        env_prefix="ORCHESTRATION_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    enabled: bool = True
    max_concurrent_workflows: int = 10
    workflow_timeout_seconds: int = 600
    agent_default_timeout_seconds: int = 120
    agent_max_retries: int = 3

    # Memory (PLAN §3 "Bounded AI Memory")
    max_memory_depth: int = 50
    max_tokens_per_memory: int = 2_048
    max_total_tokens: int = 16_384
    memory_ttl_seconds: int = 3_600
    relevance_threshold: float = 0.5

    # Circuit breaker
    circuit_open_after_failures: int = 5
    circuit_window_seconds: int = 60
    circuit_open_duration_seconds: int = 30

    # Reasoning prompt-safety dogfooding
    reasoning_prompt_safety_enabled: bool = True


class ObservabilitySettings(BaseSettings):
    """Telemetry knobs (Phase 6).

    ``otel_enabled`` and ``otlp_endpoint`` together gate the OpenTelemetry
    exporter — when ``otel_enabled`` is false the ``TracerProvider`` is still
    initialized (so ``get_tracer`` works), but no spans are exported. Setting
    ``otlp_endpoint`` to e.g. ``http://localhost:4317`` enables OTLP gRPC push.

    ``metrics_port`` exposes Prometheus on a SEPARATE listener (default bound
    to loopback). The public API on port 8000 never serves ``/metrics`` —
    that keeps the public surface auth-gated while the internal scrape stays
    unauthenticated, per Prometheus convention.
    """

    model_config = SettingsConfigDict(
        env_prefix="OBSERVABILITY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    otel_enabled: bool = False
    otlp_endpoint: str | None = None
    otel_insecure: bool = True

    metrics_enabled: bool = True
    metrics_port: int = 9090
    metrics_bind_host: str = "127.0.0.1"

    service_name: str = "platform-api"
    service_version: str = "0.1.0"

    slow_query_threshold_ms: int = 500


class JWTKey(BaseModel):
    """One signing key in the active keyset.

    The active ``kid`` is whichever entry appears first in
    ``SecuritySettings.jwt_keys``. Older ``kid`` entries remain present so
    in-flight tokens issued under them continue to validate until they
    expire (see ``POST /tokens/rotate-key``).
    """

    kid: str
    secret: SecretStr


class SecuritySettings(BaseSettings):
    """Auth / hardening knobs (Phase 6 WP3 + WP5).

    Auth is HS256 self-issued JWT — a closed-loop deployment with no
    external IdP. ``jwt_keys`` is an ordered list of ``{kid, secret}``; the
    first entry is the active signing key, later entries are
    validation-only (used during rotation). ``bootstrap_admin_secret``
    gates the admin-only ``POST /tokens/issue`` endpoint — set it once at
    deploy time and store it like any other production secret.

    Body- and rate-limit knobs are consumed by WP5 middleware. They live
    here so every operator-facing security setting is in one place.
    """

    model_config = SettingsConfigDict(
        env_prefix="SECURITY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    jwt_keys: list[JWTKey] = Field(
        default_factory=lambda: [JWTKey(kid="dev", secret=SecretStr("change-me-dev-only"))]
    )
    jwt_issuer: str = "ai-security-platform"
    jwt_audience: str = "ai-security-platform"
    jwt_algorithm: str = "HS256"
    jwt_default_ttl_seconds: int = 3_600

    bootstrap_admin_secret: SecretStr = SecretStr("")

    # WP5 — used by hardening middleware. Declared now so the config surface
    # is stable; middleware registration arrives in WP5.
    max_body_bytes: int = 1_048_576
    rate_limit_default: str = "120/minute"
    rate_limit_burst: str = "240/minute"


class RetentionSettings(BaseSettings):
    """Retention TTLs (Phase 6 WP6).

    Provenance-tiered TTLs match CLAUDE.md invariant #12. ``dry_run``
    defaults to True everywhere except production — easier to validate
    the SELECTs in staging without losing rows. ``archive_url`` is a
    file:// or s3:// URL; when set, the events-retention job writes a
    JSONL archive of fingerprint-only rows before deleting.
    """

    model_config = SettingsConfigDict(
        env_prefix="RETENTION_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    evidence_primary_days: int = 180
    evidence_derived_days: int = 90
    evidence_third_party_days: int = 60
    evidence_ai_generated_days: int = 30
    evidence_user_supplied_days: int = 30

    events_days: int = 180
    firewall_events_days: int = 90
    dlq_resolved_days: int = 30
    memory_audits_days: int = 30
    workflow_runs_days: int = 90

    dry_run: bool = True
    archive_url: str | None = None

    # Scheduler tick. Default to daily at 02:30 UTC — late enough that the
    # nightly DB maintenance window is over.
    evidence_cron_hour: int = 2
    evidence_cron_minute: int = 30
    secure_deletion_interval_seconds: int = 60


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
    firewall: FirewallSettings = Field(default_factory=FirewallSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    orchestration: OrchestrationSettings = Field(default_factory=OrchestrationSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    retention: RetentionSettings = Field(default_factory=RetentionSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
