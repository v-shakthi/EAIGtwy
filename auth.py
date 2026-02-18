"""
gateway/auth.py
===============
Simple API key authentication for the gateway.
In production: replace with OAuth2 / OIDC integration (Okta, Azure AD, etc.)
"""

import secrets
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from config import settings

api_key_header = APIKeyHeader(name=settings.api_key_header, auto_error=False)

# Hardcoded team API keys for POC
# In production: store hashed keys in a database (Postgres, Vault)
TEAM_API_KEYS: dict[str, str] = {
    "sk-gateway-finance-001":     "finance-team",
    "sk-gateway-engineering-001": "engineering-team",
    "sk-gateway-marketing-001":   "marketing-team",
    "sk-gateway-default-001":     "default",
}


async def require_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    FastAPI dependency. Returns team_id if key is valid, raises 401 otherwise.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Include X-API-Key header.",
        )
    team_id = TEAM_API_KEYS.get(api_key)
    if not team_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )
    return team_id


def generate_api_key() -> str:
    """Utility to generate a new gateway API key."""
    return f"sk-gateway-{secrets.token_urlsafe(24)}"
