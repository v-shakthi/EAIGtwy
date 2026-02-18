"""
tests/test_gateway.py
=====================
Unit and integration tests for the Enterprise AI Gateway.
All tests run without live LLM API keys — providers are mocked.

Run: pytest tests/ -v
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from gateway.app import app
    return TestClient(app)


VALID_API_KEY = "sk-gateway-default-001"
AUTH_HEADERS = {"X-API-Key": VALID_API_KEY}


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAuth:
    def test_missing_api_key_returns_401(self, client):
        resp = client.post("/v1/complete", json={
            "messages": [{"role": "user", "content": "Hello"}]
        })
        assert resp.status_code == 401

    def test_invalid_api_key_returns_403(self, client):
        resp = client.post(
            "/v1/complete",
            headers={"X-API-Key": "sk-invalid-key"},
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        assert resp.status_code == 403

    def test_valid_api_key_passes_auth(self, client):
        # Will fail at provider level (not auth level) without real keys
        resp = client.post(
            "/v1/complete",
            headers=AUTH_HEADERS,
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        # 503 (no providers) is fine — it means auth passed
        assert resp.status_code in (200, 503)


# ---------------------------------------------------------------------------
# PII Redaction tests
# ---------------------------------------------------------------------------

class TestPIIRedactor:
    def test_email_redacted(self):
        from middleware.pii_redactor import pii_redactor
        result = pii_redactor.redact("Please email john.doe@company.com about the issue.")
        assert "john.doe@company.com" not in result.redacted_text
        assert result.redaction_count >= 1

    def test_phone_redacted(self):
        from middleware.pii_redactor import pii_redactor
        result = pii_redactor.redact("Call me at 555-867-5309 for details.")
        assert "555-867-5309" not in result.redacted_text

    def test_credit_card_redacted(self):
        from middleware.pii_redactor import pii_redactor
        result = pii_redactor.redact("My card number is 4532-1234-5678-9012.")
        assert "4532-1234-5678-9012" not in result.redacted_text

    def test_ssn_redacted(self):
        from middleware.pii_redactor import pii_redactor
        result = pii_redactor.redact("SSN: 123-45-6789")
        assert "123-45-6789" not in result.redacted_text

    def test_ip_address_redacted(self):
        from middleware.pii_redactor import pii_redactor
        result = pii_redactor.redact("Server IP is 192.168.1.100")
        assert "192.168.1.100" not in result.redacted_text

    def test_clean_text_unchanged_entity_count(self):
        from middleware.pii_redactor import pii_redactor
        result = pii_redactor.redact("The weather is nice today.")
        assert result.redaction_count == 0

    def test_multiple_entities_in_one_message(self):
        from middleware.pii_redactor import pii_redactor
        text = "Contact jane@corp.com or call 555-123-4567. Server: 10.0.0.1"
        result = pii_redactor.redact(text)
        assert "jane@corp.com" not in result.redacted_text
        assert result.redaction_count >= 2


# ---------------------------------------------------------------------------
# Budget Manager tests
# ---------------------------------------------------------------------------

class TestBudgetManager:
    def test_default_budget_created(self):
        from middleware.budget_manager import budget_manager
        b = budget_manager.get_budget("test-team-new")
        assert b.daily_limit_usd > 0
        assert b.monthly_limit_usd > 0
        assert b.daily_used_usd == 0.0

    def test_budget_check_allows_under_limit(self):
        from middleware.budget_manager import budget_manager
        budget_manager.set_team_budget("test-team-a", daily_usd=10.0, monthly_usd=100.0)
        allowed, reason = budget_manager.check_budget("test-team-a", estimated_cost=0.01)
        assert allowed is True
        assert reason == ""

    def test_budget_check_blocks_over_daily_limit(self):
        from middleware.budget_manager import budget_manager
        budget_manager.set_team_budget("test-team-b", daily_usd=0.001, monthly_usd=100.0)
        allowed, reason = budget_manager.check_budget("test-team-b", estimated_cost=1.0)
        assert allowed is False
        assert "Daily budget exceeded" in reason

    def test_record_usage_increments_cost(self):
        from middleware.budget_manager import budget_manager
        budget_manager.set_team_budget("test-team-c", daily_usd=50.0, monthly_usd=500.0)
        budget_manager.record_usage("test-team-c", 0.05)
        b = budget_manager.get_budget("test-team-c")
        assert b.daily_used_usd >= 0.05

    def test_cost_estimation(self):
        from middleware.budget_manager import estimate_cost
        cost = estimate_cost("anthropic", "claude-sonnet-4-6", prompt_tokens=1000, completion_tokens=500)
        assert cost > 0
        assert cost < 1.0  # Sanity check — should be fractions of a cent


# ---------------------------------------------------------------------------
# Cost estimation tests
# ---------------------------------------------------------------------------

class TestCostEstimation:
    def test_all_providers_return_positive_cost(self):
        from middleware.budget_manager import estimate_cost
        providers = ["anthropic", "openai", "azure_openai", "gemini"]
        for provider in providers:
            cost = estimate_cost(provider, "default", 500, 500)
            assert cost > 0, f"Expected positive cost for {provider}"

    def test_more_tokens_costs_more(self):
        from middleware.budget_manager import estimate_cost
        cheap = estimate_cost("openai", "gpt-4o", 100, 100)
        expensive = estimate_cost("openai", "gpt-4o", 1000, 1000)
        assert expensive > cheap


# ---------------------------------------------------------------------------
# Circuit Breaker tests
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    def test_circuit_opens_after_threshold(self):
        from providers.router import ProviderCircuitBreaker
        from models import Provider
        cb = ProviderCircuitBreaker()
        for _ in range(cb.FAILURE_THRESHOLD):
            cb.record_failure(Provider.OPENAI)
        assert cb.is_open(Provider.OPENAI) is True

    def test_success_resets_circuit(self):
        from providers.router import ProviderCircuitBreaker
        from models import Provider
        cb = ProviderCircuitBreaker()
        for _ in range(2):
            cb.record_failure(Provider.OPENAI)
        cb.record_success(Provider.OPENAI)
        assert cb.is_open(Provider.OPENAI) is False


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "providers_available" in data

    def test_provider_status_endpoint(self, client):
        resp = client.get("/v1/providers/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "providers" in data
        assert "anthropic" in data["providers"]
        assert "openai" in data["providers"]


# ---------------------------------------------------------------------------
# Audit logger tests
# ---------------------------------------------------------------------------

class TestAuditLogger:
    def test_log_entry_written_to_file(self, tmp_path):
        import os
        from middleware.audit_logger import AuditLogger
        from models import AuditEntry

        os.environ["AUDIT_LOG_FILE"] = str(tmp_path / "test_audit.jsonl")

        logger = AuditLogger()
        logger._log_path = tmp_path / "test_audit.jsonl"

        entry = AuditEntry(
            request_id="req-test-001",
            team_id="test-team",
            provider_requested="anthropic",
            provider_used="anthropic",
            model_used="claude-sonnet-4-6",
            prompt_tokens=100,
            completion_tokens=50,
            estimated_cost_usd=0.001,
            pii_entities_redacted=[],
            pii_redaction_count=0,
            latency_ms=450.0,
            fallback_triggered=False,
            fallback_reason=None,
            status="success",
        )
        logger.log(entry)

        content = logger._log_path.read_text()
        assert "req-test-001" in content
        parsed = json.loads(content.strip())
        assert parsed["team_id"] == "test-team"

    def test_recent_entries_returns_list(self):
        from middleware.audit_logger import audit_logger
        entries = audit_logger.recent_entries(limit=10)
        assert isinstance(entries, list)
