from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from nexus.core.config import Settings


def configure_tracing(settings: Settings) -> None:
    """
    Configure OpenTelemetry tracing once for the process.

    Tracing is disabled when OTEL_ENABLED is false.

    When an OTLP endpoint is configured, spans are exported through
    the OTLP HTTP exporter. Without an endpoint, tracing remains
    configured but spans are not exported.
    """

    if not settings.otel_enabled:
        return

    current_provider = trace.get_tracer_provider()

    if not isinstance(current_provider, trace.ProxyTracerProvider):
        return

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "deployment.environment.name": settings.environment,
        },
    )

    provider = TracerProvider(resource=resource)

    if settings.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
        )

        provider.add_span_processor(
            BatchSpanProcessor(exporter),
        )

    trace.set_tracer_provider(provider)
