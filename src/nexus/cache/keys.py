from __future__ import annotations

import hashlib

KEY_NAMESPACE = "nexus"
KEY_VERSION = "v1"


def _prefix() -> str:
    return f"{KEY_NAMESPACE}:{KEY_VERSION}"


def document_key(document_hash: str) -> str:
    return f"{_prefix()}:rag:doc:{document_hash}"


def semantic_cache_key(cache_hash: str) -> str:
    return f"{_prefix()}:semantic_cache:{cache_hash}"


def rate_limit_minute_key(user_id: str, bucket: int) -> str:
    return f"{_prefix()}:rate_limit:{user_id}:minute:{bucket}"


def rate_limit_hour_key(user_id: str, bucket: int) -> str:
    return f"{_prefix()}:rate_limit:{user_id}:hour:{bucket}"


def session_memory_key(session_id: str) -> str:
    return f"{_prefix()}:langchain:memory:session:{session_id}"


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
