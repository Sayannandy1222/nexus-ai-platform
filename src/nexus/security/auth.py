from __future__ import annotations

import hashlib
import secrets

from fastapi import Header, HTTPException, status

from nexus.core.config import get_settings


async def require_api_key(
    x_api_key: str | None = Header(default=None),
) -> str:
    """
    Authenticate requests using the configured NEXUS API key.

    Returns a non-secret caller identifier derived from the API key.
    The raw API key is never returned, logged, or stored in Redis.
    """

    settings = get_settings()

    if not settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured",
        )

    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not secrets.compare_digest(
        x_api_key,
        settings.api_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return hashlib.sha256(
        x_api_key.encode("utf-8"),
    ).hexdigest()
