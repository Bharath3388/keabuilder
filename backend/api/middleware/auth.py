"""API key authentication middleware."""

import secrets
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from config import get_settings

settings = get_settings()

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    """Dependency that enforces API key authentication.

    In development mode without a configured key, authentication is skipped.
    In production, a valid API key is always required.
    """
    if not settings.app_secret_key:
        # Should never happen after config validation, but guard anyway
        raise HTTPException(status_code=500, detail="Server misconfigured")

    # In development with no explicit key set, allow unauthenticated access
    if not settings.is_production and not settings.api_key_list:
        return "dev-user"

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide X-API-Key header.",
        )

    # Constant-time comparison to prevent timing attacks
    valid_keys = settings.api_key_list
    if not valid_keys:
        # Single key mode: compare against app_secret_key
        valid_keys = [settings.app_secret_key]

    for valid_key in valid_keys:
        if secrets.compare_digest(api_key, valid_key):
            return api_key

    raise HTTPException(status_code=403, detail="Invalid API key")
