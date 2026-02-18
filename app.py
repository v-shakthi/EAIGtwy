"""
dashboard/app.py
================
Streamlit dashboard for the Enterprise AI Gateway.

Shows real-time:
- Provider health & circuit breaker status
- Team budget consumption
- Request volume and cost trends
- PII detection summary
- Recent audit log entries

Run: streamlit run dashboard/app.py
"""

import time
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GATEWAY_URL = "http://localhost:8000"
# Use a valid gateway key from gateway/auth.py
API_KEY = "sk-gateway-default-001"
HEADERS = {"X-API-Key": API_KEY}
REFRESH_INTERVAL = 10  # seconds

st.set_page_config(
    page_title="Enterprise AI Gateway",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Data fetchers (cached with short TTL)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=REFRESH_INTERVAL)
def fetch_provider_status():
    try:
        r = requests.get(f"{GATEWAY_URL}/v1/providers/status", timeout=3)
        return r.json() if r.ok else {}
    except Exception:
        return {}


@st.cache_data(ttl=REFRESH_INTERVAL)
def fetch_budgets():
    try:
        r = requests.get(f"{GATEWAY_URL}/v1/budget", headers=HEADERS, timeout=3)
        return r.json().get("teams", []) if r.ok else []
    except Exception:
        return []


@st.cache_data(ttl=REFRESH_INTERVAL)
def fetch_audit_logs(limit=200):
    try:
        r = requests.get(
            f"{GATEWAY_URL}/v1/audit/recent",
            headers=HEADERS,
            params={"limit": limit},
            timeout=3,
        )
        return r.json().get("entries", []) if r.ok else []
    except Exception:
        return []


@st.cache_data(ttl=REFRESH_INTERVAL)
def fetch_health():
    try:
        r = requests.get(f"{GATEWAY_URL}/health", timeout=2)
        return r.json() if r.ok else {"status": "unreachable"}
    except Exception:
        return {"status": "unreachable"}


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/shield.png", width=64)
    st.title("Enterprise AI Gateway")
    st.caption("Governance & Observability Dashboard")
    st.divider()

    health = fetch_health()
    if health.get("status") == "healthy":
        st.success("✅ Gateway Online")
    else:
        st.error("🔴 Gateway Unreachable")
        st.info("Start the gateway:\n```\npython main.py\n```")

    st.divider()
    st.caption(f"Auto-refresh every {REFRESH_INTERVAL}s")
    if st.button("🔄 Refresh Now"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.markdown("**Quick Test**")
    test_prompt = st.text_area("Send a test prompt:", height=80,
                               placeholder="Summarise the Q3 earnings report for ACME Corp...")
    test_provider = st.selectbox("Provider", ["anthropic", "openai", "azure_openai", "gemini"])
    if st.button("▶ Send"):
        try:
            resp = requests.post(
                f"{GATEWAY_URL}/v1/complete",
                headers=HEADERS,
                json={
                    "messages": [{"role": "user", "content": test_prompt}],
                    "provider": test_provider,
                    "max_tokens": 256,
                },
                timeout=30,
            )
            if resp.ok:
                data = resp.json()
                st.success(f"✅ {data['provider_used']} / {data['model_used']}")
                st.write(data["content"])
                if data["pii_summary"]["redacted"]:
                    st.warning(f"⚠️ PII redacted: {data['pii_summary']['entities_found']}")
            else:
                st.error(f"Error {resp.status_code}: {resp.text}")
        except Exception as e:
            st.error(f"Could not connect to gateway: {e}")


# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------

st.title("🛡️ Enterprise AI Gateway — Control Centre")
st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')} · Auto-refreshes every {REFRESH_INTERVAL}s")

# ---------------------------------------------------------------------------
# Row 1: KPI cards from audit logs
# ---------------------------------------------------------------------------

logs = fetch_audit_logs(200)
df = pd.DataFrame(logs) if logs else pd.DataFrame()

col1, col2, col3, col4, col5 = st.columns(5)

if not df.empty:
    total_requests = len(df)
    total_cost = df["estimated_cost_usd"].sum() if "estimated_cost_usd" in df else 0
    fallback_pct = (df["fallback_triggered"].sum() / len(df) * 100) if "fallback_triggered" in df else 0
    pii_requests = (df["pii_redaction_count"] > 0).sum() if "pii_redaction_count" in df else 0
    avg_latency = df["latency_ms"].mean() if "latency_ms" in df else 0

    col1.metric("Total Requests", f"{total_requests:,}")
    col2.metric("Total Cost", f"${total_cost:.4f}")
    col3.metric("Fallback Rate", f"{fallback_pct:.1f}%")
    col4.metric("PII Detections", f"{pii_requests:,}")
    col5.metric("Avg Latency", f"{avg_latency:.0f}ms")
else:
    col1.metric("Total Requests", "—")
    col2.metric("Total Cost", "—")
    col3.metric("Fallback Rate", "—")
    col4.metric("PII Detections", "—")
    col5.metric("Avg Latency", "—")

st.divider()

# ---------------------------------------------------------------------------
# Row 2: Provider Status & Budget
# ---------------------------------------------------------------------------

left, right = st.columns([1, 1])

with left:
    st.subheader("🔌 Provider Health")
    provider_data = fetch_provider_status()
    providers = provider_data.get("providers", {})

    if providers:
        for name, info in providers.items():
            configured = info.get("configured", False)
            cb = info.get("circuit_breaker", {})
            cb_open = cb.get("open", False)

            if configured and not cb_open:
                status_icon, status_color = "✅", "normal"
            elif configured and cb_open:
                status_icon, status_color = "⚡", "inverse"
            else:
                status_icon, status_color = "⚫", "off"

            col_a, col_b, col_c = st.columns([2, 2, 1])
            col_a.write(f"{status_icon} **{name}**")
            col_b.caption(info.get("default_model", ""))
            col_c.caption("OPEN" if cb_open else ("OK" if configured else "N/A"))
    else:
        st.info("Gateway not reachable. Start it to see provider status.")

with right:
    st.subheader("💰 Team Budget Usage")
    budgets = fetch_budgets()

    if budgets:
        for b in budgets:
            daily_pct = (b["daily_used_usd"] / b["daily_limit_usd"] * 100) if b["daily_limit_usd"] > 0 else 0
            color = "🔴" if daily_pct > 90 else ("🟡" if daily_pct > 70 else "🟢")
            st.write(f"{color} **{b['team_id']}** — ${b['daily_used_usd']:.4f} / ${b['daily_limit_usd']:.2f} today")
            st.progress(min(daily_pct / 100, 1.0))
    else:
        st.info("No budget data yet. Send some requests first.")

st.divider()

# ---------------------------------------------------------------------------
# Row 3: Charts
# ---------------------------------------------------------------------------

if not df.empty and "timestamp" in df.columns:
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")

    chart_left, chart_right = st.columns(2)

    with chart_left:
        st.subheader("📊 Requests by Provider")
        if "provider_used" in df.columns:
            provider_counts = df["provider_used"].value_counts().reset_index()
            provider_counts.columns = ["Provider", "Requests"]
            fig = px.pie(
                provider_counts, values="Requests", names="Provider",
                color_discrete_sequence=px.colors.qualitative.Set2,
                hole=0.4,
            )
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=280)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data yet.")

    with chart_right:
        st.subheader("💸 Cost Over Time")
        if "estimated_cost_usd" in df.columns:
            df["cumulative_cost"] = df["estimated_cost_usd"].cumsum()
            fig = px.line(
                df, x="timestamp", y="cumulative_cost",
                labels={"cumulative_cost": "Cumulative Cost (USD)", "timestamp": ""},
                color_discrete_sequence=["#00cc88"],
            )
            fig.update_layout(margin=dict(t=0, b=0), height=280)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data yet.")

    st.divider()

    # PII chart
    pii_left, pii_right = st.columns(2)

    with pii_left:
        st.subheader("🔒 PII Entity Breakdown")
        if "pii_entities_redacted" in df.columns:
            entity_lists = df["pii_entities_redacted"].dropna()
            all_entities = [e for sublist in entity_lists for e in (sublist if isinstance(sublist, list) else [])]
            if all_entities:
                entity_counts = pd.Series(all_entities).value_counts().reset_index()
                entity_counts.columns = ["Entity Type", "Count"]
                fig = px.bar(
                    entity_counts, x="Entity Type", y="Count",
                    color="Count",
                    color_continuous_scale="Reds",
                )
                fig.update_layout(margin=dict(t=0, b=0), height=280, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.success("✅ No PII detected in recent requests.")
        else:
            st.info("No PII data yet.")

    with pii_right:
        st.subheader("⚡ Latency Distribution (ms)")
        if "latency_ms" in df.columns:
            fig = px.histogram(
                df, x="latency_ms", nbins=30,
                color_discrete_sequence=["#6366f1"],
                labels={"latency_ms": "Latency (ms)"},
            )
            fig.update_layout(margin=dict(t=0, b=0), height=280)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No latency data yet.")

st.divider()

# ---------------------------------------------------------------------------
# Audit log table
# ---------------------------------------------------------------------------

st.subheader("📋 Recent Audit Log")
st.caption("Prompt content is never stored — only metadata is logged.")

if not df.empty:
    display_cols = [
        "timestamp", "request_id", "team_id", "provider_used", "model_used",
        "prompt_tokens", "completion_tokens", "estimated_cost_usd",
        "pii_redaction_count", "latency_ms", "fallback_triggered", "status"
    ]
    display_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(
        df[display_cols].head(50),
        use_container_width=True,
        column_config={
            "estimated_cost_usd": st.column_config.NumberColumn("Cost (USD)", format="$%.6f"),
            "latency_ms": st.column_config.NumberColumn("Latency (ms)", format="%.0f"),
            "fallback_triggered": st.column_config.CheckboxColumn("Fallback"),
            "timestamp": st.column_config.DatetimeColumn("Time"),
        },
    )
else:
    st.info("No audit entries yet. Send some requests through the gateway to see data here.")
