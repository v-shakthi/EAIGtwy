"""
models.py — Pydantic schemas for all Gateway request/response contracts.
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from enum import Enum


class Provider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    GEMINI = "gemini"


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


# ---------------------------------------------------------------------------
# Inbound request
# ---------------------------------------------------------------------------

class CompletionRequest(BaseModel):
    messages: list[Message]
    model: Optional[str] = None               # e.g. "claude-opus-4-6", "gpt-4o"
    provider: Optional[Provider] = None       # If None, gateway auto-selects
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    team_id: str = Field(default="default", description="Team identifier for budget tracking")
    stream: bool = False

    model_config = {"json_schema_extra": {
        "example": {
            "messages": [{"role": "user", "content": "Summarise our Q3 earnings report."}],
            "provider": "anthropic",
            "team_id": "finance-team",
            "max_tokens": 512,
        }
    }}


# ---------------------------------------------------------------------------
# Outbound response
# ---------------------------------------------------------------------------

class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class PIIRedactionSummary(BaseModel):
    redacted: bool
    entities_found: list[str]
    redaction_count: int


class CompletionResponse(BaseModel):
    id: str
    provider_used: Provider
    model_used: str
    content: str
    usage: TokenUsage
    pii_summary: PIIRedactionSummary
    latency_ms: float
    fallback_triggered: bool = False
    fallback_reason: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ---------------------------------------------------------------------------
# Team Budget
# ---------------------------------------------------------------------------

class TeamBudget(BaseModel):
    team_id: str
    daily_limit_usd: float
    monthly_limit_usd: float
    daily_used_usd: float = 0.0
    monthly_used_usd: float = 0.0
    daily_remaining_usd: float = 0.0
    monthly_remaining_usd: float = 0.0
    request_count_today: int = 0
    request_count_month: int = 0
    last_updated: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ---------------------------------------------------------------------------
# Audit log entry
# ---------------------------------------------------------------------------

class AuditEntry(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    request_id: str
    team_id: str
    provider_requested: Optional[str]
    provider_used: str
    model_used: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    pii_entities_redacted: list[str]
    pii_redaction_count: int
    latency_ms: float
    fallback_triggered: bool
    fallback_reason: Optional[str]
    status: Literal["success", "error", "budget_exceeded"]
    error_message: Optional[str] = None
    # Note: Never log actual prompt/completion content for privacy
