from prometheus_client import Counter, Histogram

CACHE_OPERATIONS_TOTAL = Counter(
    "nexus_cache_operations_total",
    "Total number of cache operations.",
    labelnames=("operation", "status"),
)

CACHE_OPERATION_DURATION_SECONDS = Histogram(
    "nexus_cache_operation_duration_seconds",
    "Cache operation duration in seconds.",
    labelnames=("operation",),
    buckets=(
        0.001,
        0.0025,
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
    ),
)

SEMANTIC_CACHE_HITS_TOTAL = Counter(
    "nexus_semantic_cache_hits_total",
    "Total number of semantic cache hits.",
)

SEMANTIC_CACHE_MISSES_TOTAL = Counter(
    "nexus_semantic_cache_misses_total",
    "Total number of semantic cache misses.",
)
