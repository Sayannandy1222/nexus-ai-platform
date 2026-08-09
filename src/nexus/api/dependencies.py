from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from nexus.cache.services.rate_limiter import RateLimiter
from nexus.security.auth import require_api_key


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter = getattr(request.app.state, "rate_limiter", None)

    if not isinstance(limiter, RateLimiter):
        raise RuntimeError("rate limiter is not initialized")

    return limiter


async def enforce_rate_limit(
    request: Request,
    caller_id: str = Depends(require_api_key),
) -> None:
    """
    Enforce the distributed API rate limit.

    The caller identity is derived from the authenticated API key.
    The raw API key is never used as a Redis/Valkey key.
    """

    limiter = get_rate_limiter(request)

    result = await limiter.check(caller_id)

    if result.allowed:
        return

    headers = {
        "Retry-After": str(result.retry_after_seconds),
        "X-RateLimit-Limit-Minute": str(result.minute_limit),
        "X-RateLimit-Remaining-Minute": str(
            max(
                0,
                result.minute_limit - result.minute_count,
            ),
        ),
        "X-RateLimit-Limit-Hour": str(result.hour_limit),
        "X-RateLimit-Remaining-Hour": str(
            max(
                0,
                result.hour_limit - result.hour_count,
            ),
        ),
    }

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="rate limit exceeded",
        headers=headers,
    )
