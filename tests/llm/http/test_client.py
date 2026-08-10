from __future__ import annotations

import httpx
import pytest

from nexus.llm.http.client import HTTPClientPool


def test_pool_rejects_invalid_timeout() -> None:
    with pytest.raises(
        ValueError,
        match="timeout_seconds must be positive",
    ):
        HTTPClientPool(timeout_seconds=0)


def test_pool_rejects_invalid_max_connections() -> None:
    with pytest.raises(
        ValueError,
        match="max_connections must be positive",
    ):
        HTTPClientPool(max_connections=0)


def test_pool_rejects_invalid_keepalive_connections() -> None:
    with pytest.raises(
        ValueError,
        match="max_keepalive_connections must be positive",
    ):
        HTTPClientPool(max_keepalive_connections=0)


def test_pool_rejects_keepalive_greater_than_max_connections() -> None:
    with pytest.raises(
        ValueError,
        match="max_keepalive_connections must not exceed max_connections",
    ):
        HTTPClientPool(
            max_connections=10,
            max_keepalive_connections=20,
        )


@pytest.mark.asyncio
async def test_pool_is_not_started_initially() -> None:
    pool = HTTPClientPool()

    try:
        assert not pool.is_started

        with pytest.raises(
            RuntimeError,
            match="has not been started",
        ):
            _ = pool.client

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_pool_starts_successfully() -> None:
    pool = HTTPClientPool()

    try:
        await pool.start()

        assert pool.is_started
        assert isinstance(pool.client, httpx.AsyncClient)

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_pool_start_is_idempotent() -> None:
    pool = HTTPClientPool()

    try:
        await pool.start()
        client = pool.client

        await pool.start()

        assert pool.is_started
        assert pool.client is client

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_pool_close_is_idempotent() -> None:
    pool = HTTPClientPool()

    await pool.start()
    await pool.close()

    assert not pool.is_started

    await pool.close()

    assert not pool.is_started


@pytest.mark.asyncio
async def test_pool_exposes_same_client_instance() -> None:
    pool = HTTPClientPool()

    try:
        await pool.start()

        first = pool.client
        second = pool.client

        assert first is second

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_pool_post_uses_shared_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = HTTPClientPool()

    response = httpx.Response(
        200,
        json={"ok": True},
        request=httpx.Request(
            "POST",
            "https://example.com/test",
        ),
    )

    calls = 0

    async def fake_post(
        self: httpx.AsyncClient,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        nonlocal calls

        calls += 1

        assert url == "https://example.com/test"
        assert kwargs["json"] == {"hello": "world"}

        return response

    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        fake_post,
    )

    try:
        await pool.start()

        result = await pool.post(
            "https://example.com/test",
            json={"hello": "world"},
        )

        assert result.status_code == 200
        assert calls == 1

    finally:
        await pool.close()
