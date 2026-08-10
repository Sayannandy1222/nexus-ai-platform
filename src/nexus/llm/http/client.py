from __future__ import annotations

from typing import Any

import httpx


class HTTPClientPool:
    """
    Shared HTTP connection pool for LLM providers.

    The pool is created once during application startup and reused
    across provider requests.

    This provides:
    - HTTP connection reuse
    - Keep-alive connections
    - Bounded connection concurrency
    - Centralized HTTP client lifecycle
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be positive",
            )

        if max_connections <= 0:
            raise ValueError(
                "max_connections must be positive",
            )

        if max_keepalive_connections <= 0:
            raise ValueError(
                "max_keepalive_connections must be positive",
            )

        if max_keepalive_connections > max_connections:
            raise ValueError(
                "max_keepalive_connections must not exceed max_connections",
            )

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive_connections,
            ),
        )

        self._started = False

    @property
    def client(self) -> httpx.AsyncClient:
        """
        Return the underlying shared HTTP client.
        """

        if not self._started:
            raise RuntimeError(
                "HTTP client pool has not been started",
            )

        return self._client

    @property
    def is_started(self) -> bool:
        """
        Return whether the HTTP client pool has been started.
        """

        return self._started

    async def start(self) -> None:
        """
        Start the HTTP client pool.
        """

        if self._started:
            return

        self._started = True

    async def close(self) -> None:
        """
        Close the HTTP client pool.
        """

        if not self._started:
            await self._client.aclose()
            return

        await self._client.aclose()
        self._started = False

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> httpx.Response:
        """
        Execute an asynchronous POST request using the shared client.
        """

        return await self.client.post(
            url,
            headers=headers,
            params=params,
            json=json,
        )
