from nexus.cache.keys import (
    document_key,
    hash_text,
    rate_limit_hour_key,
    rate_limit_minute_key,
    semantic_cache_key,
    session_memory_key,
)


def test_document_key() -> None:
    assert document_key("abc123") == "nexus:v1:rag:doc:abc123"


def test_semantic_cache_key() -> None:
    assert semantic_cache_key("abc123") == "nexus:v1:semantic_cache:abc123"


def test_rate_limit_keys() -> None:
    assert rate_limit_minute_key("user-1", 100) == ("nexus:v1:rate_limit:user-1:minute:100")
    assert rate_limit_hour_key("user-1", 10) == ("nexus:v1:rate_limit:user-1:hour:10")


def test_session_memory_key() -> None:
    assert session_memory_key("session-1") == ("nexus:v1:langchain:memory:session:session-1")


def test_hash_text_is_deterministic() -> None:
    assert hash_text("hello") == hash_text("hello")
    assert hash_text("hello") != hash_text("world")
