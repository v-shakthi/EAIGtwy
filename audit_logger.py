"""
middleware/audit_logger.py
==========================
Structured audit logging for every gateway request.

Output:
  - Local JSONL file (human-readable, grep-friendly)
  - Optional webhook to SIEM (Splunk HEC, Elastic, Datadog Logs)

Design principle: NEVER log raw prompt or completion content.
Only log metadata: who, when, which provider, how many tokens, cost, PII summary.
"""

import json
import httpx
import asyncio
from pathlib import Path
from datetime import datetime
from config import settings
from models import AuditEntry


class AuditLogger:
    def __init__(self):
        self._log_path = Path(settings.audit_log_file)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._siem_url = settings.siem_webhook_url

    def log(self, entry: AuditEntry):
        """
        Write audit entry to local JSONL and optionally ship to SIEM.
        Non-blocking: SIEM failure does NOT fail the request.
        """
        line = entry.model_dump_json()

        # 1. Append to local JSONL file
        with open(self._log_path, "a") as f:
            f.write(line + "\n")

        # 2. Fire-and-forget to SIEM webhook
        if self._siem_url:
            asyncio.create_task(self._ship_to_siem(entry))

    async def _ship_to_siem(self, entry: AuditEntry):
        """POST audit entry to SIEM webhook. Silently fails — never blocks the gateway."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(
                    self._siem_url,
                    json={"event": entry.model_dump(), "sourcetype": "ai_gateway"},
                    headers={"Content-Type": "application/json"},
                )
        except Exception:
            pass  # SIEM unavailability must never impact request latency

    def recent_entries(self, limit: int = 100) -> list[dict]:
        """Read last N entries from the audit log. Used by the dashboard."""
        if not self._log_path.exists():
            return []
        lines = self._log_path.read_text().strip().split("\n")
        lines = [l for l in lines if l.strip()]
        recent = lines[-limit:]
        entries = []
        for line in recent:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(entries))  # Most recent first


# Singleton
audit_logger = AuditLogger()
