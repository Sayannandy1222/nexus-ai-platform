from __future__ import annotations

from prometheus_client import Counter, Histogram

LLM_REQUESTS_TOTAL = Counter(
    "nexus_llm_requests_total",
    "Total number of LLM provider requests.",
    labelnames=("provider", "status"),
)

LLM_REQUEST_DURATION_SECONDS = Histogram(
    "nexus_llm_request_duration_seconds",
    "LLM provider request duration in seconds.",
    labelnames=("provider",),
    buckets=(
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
        60.0,
    ),
)

LLM_ERRORS_TOTAL = Counter(
    "nexus_llm_errors_total",
    "Total number of LLM provider errors.",
    labelnames=("provider", "error_type"),
)

LLM_RETRIES_TOTAL = Counter(
    "nexus_llm_retries_total",
    "Total number of LLM provider retries.",
    labelnames=("provider", "error_type"),
)

LLM_FALLBACKS_TOTAL = Counter(
    "nexus_llm_fallbacks_total",
    "Total number of LLM provider fallbacks.",
    labelnames=("from_provider", "to_provider"),
)
