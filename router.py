"""
providers/router.py
===================
Intelligent provider routing with automatic fallback.

Routing strategy:
1. If caller specifies a provider → try it first
2. If that fails (timeout, rate limit, API error) → try next available in priority order
3. If all providers fail → raise GatewayError with full failure trace

This implements the Circuit Breaker-lite pattern:
- Tracks consecutive failures per provider
- Skips providers with recent failures (cooldown period)
"""

import time
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from models import Message, Provider
from providers.adapters import PROVIDER_REGISTRY, AdapterResponse
from config import settings

logger = logging.getLogger(__name__)


class ProviderCircuitBreaker:
    """
    Lightweight circuit breaker per provider.
    After FAILURE_THRESHOLD consecutive failures, provider is skipped for COOLDOWN_SECONDS.
    """
    FAILURE_THRESHOLD = 3
    COOLDOWN_SECONDS = 60

    def __init__(self):
        self._failures: dict[Provider, int] = defaultdict(int)
        self._tripped_at: dict[Provider, datetime | None] = defaultdict(lambda: None)

    def record_success(self, provider: Provider):
        self._failures[provider] = 0
        self._tripped_at[provider] = None

    def record_failure(self, provider: Provider):
        self._failures[provider] += 1
        if self._failures[provider] >= self.FAILURE_THRESHOLD:
            self._tripped_at[provider] = datetime.utcnow()
            logger.warning(f"Circuit breaker OPEN for provider: {provider}")

    def is_open(self, provider: Provider) -> bool:
        """Returns True if the provider is in cooldown (should be skipped)."""
        tripped = self._tripped_at[provider]
        if tripped is None:
            return False
        if datetime.utcnow() - tripped > timedelta(seconds=self.COOLDOWN_SECONDS):
            # Cooldown elapsed — reset to half-open
            self._failures[provider] = 0
            self._tripped_at[provider] = None
            logger.info(f"Circuit breaker RESET for provider: {provider}")
            return False
        return True

    def status(self) -> dict:
        return {
            p.value: {
                "failures": self._failures[p],
                "tripped": self._tripped_at[p].isoformat() if self._tripped_at[p] else None,
                "open": self.is_open(p),
            }
            for p in Provider
        }


circuit_breaker = ProviderCircuitBreaker()


class GatewayError(Exception):
    def __init__(self, message: str, provider_errors: dict[str, str]):
        super().__init__(message)
        self.provider_errors = provider_errors


def route_request(
    messages: list[Message],
    preferred_provider: Provider | None,
    model: str | None,
    max_tokens: int,
    temperature: float,
) -> tuple[AdapterResponse, bool, str | None]:
    """
    Routes a completion request to the best available provider.

    Returns:
        (AdapterResponse, fallback_triggered, fallback_reason)
    """
    # Build the ordered list of providers to try
    priority_names = settings.provider_priority
    priority = [Provider(p) for p in priority_names if Provider(p) in PROVIDER_REGISTRY]

    if preferred_provider:
        # Move preferred to front, keep rest as fallback
        priority = [preferred_provider] + [p for p in priority if p != preferred_provider]

    provider_errors: dict[str, str] = {}
    fallback_triggered = False
    fallback_reason = None
    first_tried = None

    for provider in priority:
        adapter = PROVIDER_REGISTRY.get(provider)

        if not adapter:
            continue
        if not adapter.is_available():
            provider_errors[provider.value] = "Not configured (missing API key)"
            continue
        if circuit_breaker.is_open(provider):
            provider_errors[provider.value] = "Circuit breaker open (too many recent failures)"
            continue

        if first_tried is not None:
            # We're past the first provider — this is a fallback
            fallback_triggered = True
            fallback_reason = f"Fell back from {first_tried.value}: {provider_errors.get(first_tried.value, 'unknown error')}"
            logger.warning(f"Fallback triggered: {fallback_reason}. Trying {provider.value}.")

        if first_tried is None:
            first_tried = provider

        try:
            response = adapter.complete(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            circuit_breaker.record_success(provider)
            return response, fallback_triggered, fallback_reason

        except Exception as e:
            error_msg = str(e)
            provider_errors[provider.value] = error_msg
            circuit_breaker.record_failure(provider)
            logger.error(f"Provider {provider.value} failed: {error_msg}")

    raise GatewayError(
        f"All providers failed after trying: {list(provider_errors.keys())}",
        provider_errors=provider_errors,
    )
