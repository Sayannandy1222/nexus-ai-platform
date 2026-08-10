from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

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

LLM_PROVIDER_REQUESTS = Gauge(
    "nexus_llm_provider_requests",
    "Current number of requests observed by the provider router.",
    labelnames=("provider",),
)

LLM_PROVIDER_SUCCESS_RATE = Gauge(
    "nexus_llm_provider_success_rate",
    "Current observed provider success rate.",
    labelnames=("provider",),
)

LLM_PROVIDER_ERROR_RATE = Gauge(
    "nexus_llm_provider_error_rate",
    "Current observed provider error rate.",
    labelnames=("provider",),
)

LLM_PROVIDER_AVERAGE_LATENCY_SECONDS = Gauge(
    "nexus_llm_provider_average_latency_seconds",
    "Current observed average successful provider latency.",
    labelnames=("provider",),
)

LLM_PROVIDER_CONSECUTIVE_FAILURES = Gauge(
    "nexus_llm_provider_consecutive_failures",
    "Current consecutive failure count for the provider.",
    labelnames=("provider",),
)

LLM_PROVIDER_HEALTHY = Gauge(
    "nexus_llm_provider_healthy",
    "Whether the provider is currently considered healthy.",
    labelnames=("provider",),
)

LLM_PROVIDER_SCORE = Gauge(
    "nexus_llm_provider_score",
    "Current routing score assigned to the provider.",
    labelnames=("provider",),
)

LLM_PROVIDER_SELECTED_TOTAL = Counter(
    "nexus_llm_provider_selected_total",
    "Total number of times a provider was selected as the first routing candidate.",
    labelnames=("provider",),
)
