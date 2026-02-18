"""
config.py — Centralised configuration for the Enterprise AI Gateway.
All settings are loaded from environment variables / .env file.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # --- App ---
    app_name: str = "Enterprise AI Gateway"
    app_version: str = "1.0.0"
    debug: bool = False

    # --- Auth ---
    secret_key: str = Field(default="change-me-in-production-use-256-bit-random-string")
    api_key_header: str = "X-API-Key"

    # --- LLM Provider API Keys ---
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_version: str = "2024-02-01"
    azure_openai_deployment: str = "gpt-4o"
    google_api_key: Optional[str] = None

    # --- Provider Priority (fallback order) ---
    provider_priority: list[str] = ["anthropic", "openai", "azure_openai", "gemini"]

    # --- Redis (rate limiting & budget tracking) ---
    redis_url: str = "redis://localhost:6379"
    use_redis: bool = False  # Falls back to in-memory if False (for POC)

    # --- PII ---
    pii_redaction_enabled: bool = True
    pii_entities: list[str] = [
        "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD",
        "US_SSN", "IP_ADDRESS", "LOCATION", "DATE_TIME",
    ]

    # --- Audit ---
    audit_log_file: str = "audit_logs/gateway_audit.jsonl"
    siem_webhook_url: Optional[str] = None  # e.g. Splunk HEC or Elastic

    # --- Budget (USD) ---
    default_team_daily_budget_usd: float = 10.0
    default_team_monthly_budget_usd: float = 200.0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
