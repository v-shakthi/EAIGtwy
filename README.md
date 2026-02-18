# 🛡️ Enterprise AI Gateway

> A production-grade **multi-provider LLM gateway** with PII redaction, per-team budget controls, automatic fallback routing, structured audit logging, and a real-time monitoring dashboard — built for enterprise AI governance.

This project demonstrates how enterprises can safely adopt AI across teams while maintaining control over **data privacy**, **cost**, **reliability**, and **compliance**.

---

## 🏗️ Architecture

```
                         ┌─────────────────────────────────────────┐
                         │           Enterprise Network            │
                         │                                         │
Client / App  ──────────►│  ┌─────────────────────────────────┐   │
  X-API-Key              │  │       FastAPI Gateway            │   │
                         │  │                                  │   │
                         │  │  1. Auth (API Key → Team ID)     │   │
                         │  │  2. PII Redactor (Presidio)      │   │
                         │  │  3. Budget Pre-Check             │   │
                         │  │  4. Provider Router              │   │
                         │  │     ├─ Anthropic (Claude)        │   │
                         │  │     ├─ OpenAI (GPT-4o)           │   │◄── PII stays
                         │  │     ├─ Azure OpenAI              │   │    inside
                         │  │     └─ Google (Gemini)           │   │
                         │  │  5. Circuit Breaker + Fallback   │   │
                         │  │  6. Cost Recording               │   │
                         │  │  7. Audit Log → SIEM             │   │
                         │  └─────────────────────────────────┘   │
                         │           │                             │
                         │    ┌──────▼───────┐                     │
                         │    │  Streamlit   │                     │
                         │    │  Dashboard   │                     │
                         │    └──────────────┘                     │
                         └─────────────────────────────────────────┘
```

---

## ✨ Features

| Feature | Details |
|---|---|
| **Multi-Provider** | Anthropic, OpenAI, Azure OpenAI, Google Gemini behind one unified API |
| **PII Redaction** | Microsoft Presidio scans all prompts for emails, phone numbers, SSNs, credit cards, IPs — before they leave the network |
| **Budget Controls** | Per-team daily & monthly USD limits with pre-request cost checks |
| **Automatic Fallback** | If provider A fails → auto-routes to provider B with configurable priority |
| **Circuit Breaker** | Unhealthy providers are skipped after N failures and retried after cooldown |
| **Audit Logging** | Every request logged to JSONL + optional SIEM webhook (Splunk/Elastic). Prompt content never stored |
| **Dashboard** | Real-time Streamlit UI showing provider health, budget usage, cost trends, PII stats |
| **OpenAPI Docs** | Auto-generated Swagger UI at `/docs` |

---

## 🚀 Quick Start

### 1. Install

```bash
git clone https://github.com/your-username/enterprise-ai-gateway
cd enterprise-ai-gateway

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Install Presidio language model (for PII detection)
python -m spacy download en_core_web_lg
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — add at least one provider API key
```

### 3. Start the gateway

```bash
python main.py
# Gateway running at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### 4. Start the dashboard

```bash
streamlit run dashboard/app.py
# Dashboard at http://localhost:8501
```

### 5. Send a request

```bash
curl -X POST http://localhost:8000/v1/complete \
  -H "X-API-Key: sk-gateway-default-001" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Summarise our Q3 results."}],
    "provider": "anthropic",
    "team_id": "finance-team",
    "max_tokens": 256
  }'
```

### 6. Run tests (no API keys needed)

```bash
pytest tests/ -v
```

---

## 📁 Project Structure

```
enterprise-ai-gateway/
│
├── main.py                        # Server entrypoint (uvicorn)
├── config.py                      # Pydantic settings (env-driven)
├── models.py                      # Request/response/audit schemas
├── requirements.txt
├── .env.example
│
├── gateway/
│   ├── app.py                     # FastAPI app + all routes
│   └── auth.py                    # API key auth middleware
│
├── middleware/
│   ├── pii_redactor.py            # Presidio-based PII scrubbing
│   ├── budget_manager.py          # Per-team cost tracking (Redis-ready)
│   └── audit_logger.py            # JSONL audit log + SIEM webhook
│
├── providers/
│   ├── adapters.py                # Unified adapter for all 4 providers
│   └── router.py                  # Fallback routing + circuit breaker
│
├── dashboard/
│   └── app.py                     # Streamlit monitoring dashboard
│
└── tests/
    └── test_gateway.py            # Unit tests (no live API needed)
```

---

## 🔑 Built-in API Keys (POC)

| API Key | Team |
|---|---|
| `sk-gateway-finance-001` | finance-team |
| `sk-gateway-engineering-001` | engineering-team |
| `sk-gateway-marketing-001` | marketing-team |
| `sk-gateway-default-001` | default |

---

## 📡 API Reference

### `POST /v1/complete` — Send a completion

```json
{
  "messages": [{"role": "user", "content": "Your prompt here"}],
  "provider": "anthropic",      // optional — gateway auto-selects if omitted
  "model": "claude-opus-4-6",   // optional — uses provider default if omitted
  "max_tokens": 1024,
  "temperature": 0.7,
  "team_id": "finance-team"     // overridden by auth — here for documentation
}
```

**Response includes:**
- `provider_used` + `model_used` — what actually served the request
- `pii_summary` — what was redacted before the prompt left your network
- `usage` — token counts + estimated cost
- `fallback_triggered` — whether a provider failure caused rerouting
- `latency_ms` — end-to-end gateway latency

### `GET /v1/providers/status` — Provider health & circuit breaker state

### `GET /v1/budget/{team_id}` — Team budget status

### `GET /v1/audit/recent?limit=50` — Recent audit log entries

### `GET /health` — Gateway health check

---

## 🏢 Enterprise Integration Points

| Component | POC Implementation | Production Replacement |
|---|---|---|
| Auth | Hardcoded API keys | OAuth2 / Azure AD / Okta OIDC |
| Budget store | In-memory dict | Redis / PostgreSQL |
| Audit log | Local JSONL file | Splunk HEC / Elastic / Datadog Logs |
| PII engine | Presidio (in-process) | Presidio server (airgapped) |
| Secret management | `.env` file | HashiCorp Vault / AWS Secrets Manager |
| Rate limiting | SlowAPI (single node) | Redis-backed rate limiter |

---

## 🎛️ Configuration

Key settings in `.env`:

```bash
# Provider priority for fallback (left = highest priority)
PROVIDER_PRIORITY=anthropic,openai,azure_openai,gemini

# PII settings
PII_REDACTION_ENABLED=true

# Budget defaults per team (override per team via API)
DEFAULT_TEAM_DAILY_BUDGET_USD=10.0
DEFAULT_TEAM_MONTHLY_BUDGET_USD=200.0

# SIEM webhook (optional)
SIEM_WEBHOOK_URL=https://your-splunk.corp.com/services/collector/event
```

---

## 🧠 Enterprise Patterns Demonstrated

- **Policy enforcement point (PEP)**: Gateway intercepts all LLM traffic before it leaves the enterprise
- **Data residency**: PII never leaves the network — redacted in-process before provider call
- **FinOps integration**: Cost is estimated pre-request and recorded post-request per team
- **Resilience patterns**: Circuit breaker + fallback routing = no single point of provider failure
- **Compliance by design**: Structured audit trail with metadata-only logging (no prompt content)
- **Zero-trust API**: Every request authenticated and attributed to a team

---

## 🗺️ Roadmap

- [ ] Add **streaming** support (`text/event-stream` responses)
- [ ] **Redis** integration for multi-replica budget tracking
- [ ] **Prompt injection detection** middleware layer
- [ ] **Rate limiting** per team (requests/minute)
- [ ] **Model routing by capability** (e.g., route code tasks to specific models)
- [ ] **OpenAI-compatible** `/v1/chat/completions` endpoint for drop-in replacement
- [ ] **Kubernetes Helm chart** for production deployment

---

*Built as a portfolio project demonstrating enterprise AI governance and adoption patterns.*
