from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class CacheMetrics:
    hits: float
    misses: float


@dataclass(frozen=True)
class BenchmarkResult:
    total_requests: int
    successful_requests: int
    failed_requests: int
    error_rate_percent: float

    cache_hits: int
    cache_misses: int
    cache_hit_rate_percent: float

    p50_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float

    throughput_rps: float
    duration_seconds: float


async def read_cache_metrics(
    client: httpx.AsyncClient,
    metrics_url: str,
) -> CacheMetrics:
    response = await client.get(metrics_url)
    response.raise_for_status()

    hits = 0.0
    misses = 0.0

    for line in response.text.splitlines():
        line = line.strip()

        if line.startswith("nexus_semantic_cache_hits_total ") and not line.startswith("#"):
            hits = float(
                line.split(" ", 1)[1],
            )

        elif line.startswith("nexus_semantic_cache_misses_total ") and not line.startswith("#"):
            misses = float(
                line.split(" ", 1)[1],
            )

    return CacheMetrics(
        hits=hits,
        misses=misses,
    )


async def send_request(
    client: httpx.AsyncClient,
    url: str,
    api_key: str,
    prompt: str,
) -> tuple[float, bool]:
    started = time.perf_counter()

    try:
        response = await client.post(
            url,
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "prompt": prompt,
            },
        )

        elapsed_ms = (time.perf_counter() - started) * 1000

        return elapsed_ms, response.is_success

    except httpx.HTTPError:
        elapsed_ms = (time.perf_counter() - started) * 1000

        return elapsed_ms, False


def percentile(
    values: list[float],
    percentage: float,
) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)

    index = (len(ordered) - 1) * percentage / 100

    lower = int(index)
    upper = min(
        lower + 1,
        len(ordered) - 1,
    )

    if lower == upper:
        return ordered[lower]

    weight = index - lower

    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def build_result(
    latencies: list[float],
    successes: list[bool],
    cache_hits: int,
    cache_misses: int,
    duration_seconds: float,
) -> BenchmarkResult:
    total_requests = len(successes)

    successful_requests = sum(successes)

    failed_requests = total_requests - successful_requests

    error_rate_percent = failed_requests / total_requests * 100 if total_requests else 0.0

    total_cache_operations = cache_hits + cache_misses

    cache_hit_rate_percent = (
        cache_hits / total_cache_operations * 100 if total_cache_operations else 0.0
    )

    return BenchmarkResult(
        total_requests=total_requests,
        successful_requests=successful_requests,
        failed_requests=failed_requests,
        error_rate_percent=error_rate_percent,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        cache_hit_rate_percent=cache_hit_rate_percent,
        p50_ms=percentile(
            latencies,
            50,
        ),
        p95_ms=percentile(
            latencies,
            95,
        ),
        p99_ms=percentile(
            latencies,
            99,
        ),
        min_ms=(min(latencies) if latencies else 0.0),
        max_ms=(max(latencies) if latencies else 0.0),
        throughput_rps=(total_requests / duration_seconds if duration_seconds > 0 else 0.0),
        duration_seconds=duration_seconds,
    )


async def run_benchmark(
    url: str,
    metrics_url: str,
    api_key: str,
    requests: int,
    concurrency: int,
    prompt: str,
) -> BenchmarkResult:
    semaphore = asyncio.Semaphore(
        concurrency,
    )

    timeout = httpx.Timeout(
        connect=5.0,
        read=60.0,
        write=10.0,
        pool=10.0,
    )

    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )

    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
    ) as client:
        metrics_before = await read_cache_metrics(
            client,
            metrics_url,
        )

        async def bounded_request() -> tuple[
            float,
            bool,
        ]:
            async with semaphore:
                return await send_request(
                    client=client,
                    url=url,
                    api_key=api_key,
                    prompt=prompt,
                )

        started = time.perf_counter()

        results = await asyncio.gather(
            *(bounded_request() for _ in range(requests)),
        )

        duration_seconds = time.perf_counter() - started

        metrics_after = await read_cache_metrics(
            client,
            metrics_url,
        )

    cache_hits = max(
        0,
        int(
            metrics_after.hits - metrics_before.hits,
        ),
    )

    cache_misses = max(
        0,
        int(
            metrics_after.misses - metrics_before.misses,
        ),
    )

    latencies = [result[0] for result in results]

    successes = [result[1] for result in results]

    return build_result(
        latencies=latencies,
        successes=successes,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        duration_seconds=duration_seconds,
    )


def print_result(
    result: BenchmarkResult,
) -> None:
    print()
    print("=" * 60)
    print("NEXUS PERFORMANCE BENCHMARK")
    print("=" * 60)

    print()
    print("Requests")
    print("-" * 60)

    print(f"Total requests:       {result.total_requests}")

    print(f"Successful requests:  {result.successful_requests}")

    print(f"Failed requests:      {result.failed_requests}")

    print(f"Error rate:           {result.error_rate_percent:.2f}%")

    print()
    print("Semantic Cache")
    print("-" * 60)

    print(f"Cache hits:           {result.cache_hits}")

    print(f"Cache misses:         {result.cache_misses}")

    print(f"Cache hit rate:       {result.cache_hit_rate_percent:.2f}%")

    print()
    print("Latency")
    print("-" * 60)

    print(f"P50:                  {result.p50_ms:.2f} ms")

    print(f"P95:                  {result.p95_ms:.2f} ms")

    print(f"P99:                  {result.p99_ms:.2f} ms")

    print(f"Min:                  {result.min_ms:.2f} ms")

    print(f"Max:                  {result.max_ms:.2f} ms")

    print()
    print("Throughput")
    print("-" * 60)

    print(f"Duration:             {result.duration_seconds:.2f} s")

    print(f"Throughput:           {result.throughput_rps:.2f} req/s")

    print("=" * 60)
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Benchmark the NEXUS generate API."),
    )

    parser.add_argument(
        "--url",
        default=("http://localhost:8000/v1/generate"),
    )

    parser.add_argument(
        "--metrics-url",
        default=("http://localhost:8000/v1/metrics"),
    )

    parser.add_argument(
        "--api-key",
        required=True,
    )

    parser.add_argument(
        "--requests",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--prompt",
        default=("Explain what an LLM gateway is in one paragraph."),
    )

    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    if args.requests <= 0:
        raise ValueError(
            "--requests must be positive",
        )

    if args.concurrency <= 0:
        raise ValueError(
            "--concurrency must be positive",
        )

    result = await run_benchmark(
        url=args.url,
        metrics_url=args.metrics_url,
        api_key=args.api_key,
        requests=args.requests,
        concurrency=args.concurrency,
        prompt=args.prompt,
    )

    print_result(result)

    print(
        json.dumps(
            {
                "total_requests": (result.total_requests),
                "successful_requests": (result.successful_requests),
                "failed_requests": (result.failed_requests),
                "error_rate_percent": round(
                    result.error_rate_percent,
                    4,
                ),
                "cache_hits": (result.cache_hits),
                "cache_misses": (result.cache_misses),
                "cache_hit_rate_percent": (
                    round(
                        result.cache_hit_rate_percent,
                        4,
                    )
                ),
                "p50_ms": round(
                    result.p50_ms,
                    2,
                ),
                "p95_ms": round(
                    result.p95_ms,
                    2,
                ),
                "p99_ms": round(
                    result.p99_ms,
                    2,
                ),
                "min_ms": round(
                    result.min_ms,
                    2,
                ),
                "max_ms": round(
                    result.max_ms,
                    2,
                ),
                "throughput_rps": round(
                    result.throughput_rps,
                    2,
                ),
                "duration_seconds": round(
                    result.duration_seconds,
                    2,
                ),
            },
            indent=2,
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())
