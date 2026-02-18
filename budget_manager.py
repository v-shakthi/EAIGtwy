"""
middleware/budget_manager.py
============================
Per-team token budget and cost tracking.

Architecture:
- Uses Redis for production (shared state across gateway replicas)
- Falls back to in-memory dict for POC (single-instance)
- Cost estimates based on public provider pricing (update as pricing changes)

In production: integrate with your FinOps platform (CloudHealth, Apptio, etc.)
"""

import json
from datetime import datetime, date
from threading import Lock
from config import settings
from models import TeamBudget


# ---------------------------------------------------------------------------
# Cost lookup table (USD per 1K tokens — update to reflect current pricing)
# ---------------------------------------------------------------------------

COST_PER_1K_TOKENS: dict[str, dict[str, float]] = {
    "anthropic": {
        "claude-opus-4-6":    {"input": 0.015,  "output": 0.075},
        "claude-sonnet-4-6":  {"input": 0.003,  "output": 0.015},
        "claude-haiku-4-5":   {"input": 0.00025,"output": 0.00125},
        "default":            {"input": 0.003,  "output": 0.015},
    },
    "openai": {
        "gpt-4o":             {"input": 0.005,  "output": 0.015},
        "gpt-4o-mini":        {"input": 0.00015,"output": 0.0006},
        "gpt-4-turbo":        {"input": 0.010,  "output": 0.030},
        "default":            {"input": 0.005,  "output": 0.015},
    },
    "azure_openai": {
        "gpt-4o":             {"input": 0.005,  "output": 0.015},
        "default":            {"input": 0.005,  "output": 0.015},
    },
    "gemini": {
        "gemini-1.5-pro":     {"input": 0.00125,"output": 0.005},
        "gemini-1.5-flash":   {"input": 0.000075,"output": 0.0003},
        "default":            {"input": 0.00125,"output": 0.005},
    },
}


def estimate_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Estimate USD cost for a completion call."""
    provider_costs = COST_PER_1K_TOKENS.get(provider, {})
    model_costs = provider_costs.get(model, provider_costs.get("default", {"input": 0.005, "output": 0.015}))
    return (prompt_tokens / 1000 * model_costs["input"]) + (completion_tokens / 1000 * model_costs["output"])


# ---------------------------------------------------------------------------
# In-memory budget store (Redis-compatible interface)
# ---------------------------------------------------------------------------

class InMemoryBudgetStore:
    """Thread-safe in-memory store. Replace with Redis for multi-replica deployments."""

    def __init__(self):
        self._lock = Lock()
        self._budgets: dict[str, dict] = {}
        self._daily_usage: dict[str, dict] = {}   # team_id -> {date -> cost}
        self._monthly_usage: dict[str, dict] = {} # team_id -> {month -> cost}

    def get_budget(self, team_id: str) -> TeamBudget:
        with self._lock:
            today = date.today().isoformat()
            month = date.today().strftime("%Y-%m")

            cfg = self._budgets.get(team_id, {
                "daily_limit_usd": settings.default_team_daily_budget_usd,
                "monthly_limit_usd": settings.default_team_monthly_budget_usd,
            })

            daily_used = self._daily_usage.get(team_id, {}).get(today, 0.0)
            monthly_used = self._monthly_usage.get(team_id, {}).get(month, 0.0)
            daily_requests = int(self._daily_usage.get(team_id, {}).get(f"{today}_count", 0))

            return TeamBudget(
                team_id=team_id,
                daily_limit_usd=cfg["daily_limit_usd"],
                monthly_limit_usd=cfg["monthly_limit_usd"],
                daily_used_usd=round(daily_used, 6),
                monthly_used_usd=round(monthly_used, 6),
                daily_remaining_usd=round(max(0, cfg["daily_limit_usd"] - daily_used), 6),
                monthly_remaining_usd=round(max(0, cfg["monthly_limit_usd"] - monthly_used), 6),
                request_count_today=daily_requests,
            )

    def check_budget(self, team_id: str, estimated_cost: float) -> tuple[bool, str]:
        """Returns (allowed, reason). Call BEFORE making the LLM request."""
        budget = self.get_budget(team_id)
        if estimated_cost > budget.daily_remaining_usd:
            return False, (
                f"Daily budget exceeded for team '{team_id}'. "
                f"Used: ${budget.daily_used_usd:.4f} / ${budget.daily_limit_usd:.2f}. "
                f"Resets at midnight UTC."
            )
        if estimated_cost > budget.monthly_remaining_usd:
            return False, (
                f"Monthly budget exceeded for team '{team_id}'. "
                f"Used: ${budget.monthly_used_usd:.4f} / ${budget.monthly_limit_usd:.2f}."
            )
        return True, ""

    def record_usage(self, team_id: str, actual_cost: float):
        """Call AFTER a successful LLM response to record actual cost."""
        with self._lock:
            today = date.today().isoformat()
            month = date.today().strftime("%Y-%m")

            if team_id not in self._daily_usage:
                self._daily_usage[team_id] = {}
            if team_id not in self._monthly_usage:
                self._monthly_usage[team_id] = {}

            self._daily_usage[team_id][today] = self._daily_usage[team_id].get(today, 0.0) + actual_cost
            self._daily_usage[team_id][f"{today}_count"] = self._daily_usage[team_id].get(f"{today}_count", 0) + 1
            self._monthly_usage[team_id][month] = self._monthly_usage[team_id].get(month, 0.0) + actual_cost

    def set_team_budget(self, team_id: str, daily_usd: float, monthly_usd: float):
        with self._lock:
            self._budgets[team_id] = {
                "daily_limit_usd": daily_usd,
                "monthly_limit_usd": monthly_usd,
            }

    def all_teams(self) -> list[TeamBudget]:
        with self._lock:
            all_ids = set(self._budgets.keys()) | set(self._daily_usage.keys())
            return [self.get_budget(tid) for tid in all_ids]


# Singleton
budget_manager = InMemoryBudgetStore()
