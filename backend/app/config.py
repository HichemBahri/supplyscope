"""Application settings, loaded from environment / .env (pydantic-settings).

Two database identities by design (see ADR-006 and db/init/01-schemas.sql):
  * the application identity (POSTGRES_USER): full rights, used by the app
    layer for its own data (schema `app`) and by trusted internal queries;
  * the agent identity (AGENT_DB_USER): SELECT-only on schema `erp` — every
    piece of LLM-generated SQL executes under this role, so even a
    hallucinated `DROP TABLE` is refused by PostgreSQL itself.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- security hardening (Phase 10) ---
    email_verification_enabled: bool = False   # on in docker (MailHog wired)
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    mail_from: str = "no-reply@supplyscope.local"
    verification_ttl_minutes: int = 15
    max_failed_logins: int = 5
    lockout_minutes: int = 15

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- LLM ---------------------------------------------------------------
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    llm_model_fast: str = "claude-haiku-4-5"
    llm_model_smart: str = "claude-sonnet-4-6"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # --- PostgreSQL --------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "supplyscope"
    postgres_user: str = "supplyscope"
    postgres_password: str = ""
    agent_db_user: str = "agent_reader"
    agent_db_password: str = "agent_reader_dev_only"   # dev default; override in prod

    # --- Auth --------------------------------------------------------------
    jwt_secret: str = "dev_only_change_me"
    jwt_expiry_hours: int = 24

    # --- Agent guardrails --------------------------------------------------
    agent_sql_timeout_ms: int = 8000
    agent_max_rows: int = 500

    @property
    def app_dsn(self) -> str:
        return (f"postgresql://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}")

    @property
    def agent_dsn(self) -> str:
        return (f"postgresql://{self.agent_db_user}:{self.agent_db_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
