"""OpenTelemetry tracer provider + optional OTLP exporter.

The ``TracerProvider`` is always initialized so callers can issue spans
unconditionally via :func:`get_tracer`. Whether those spans are EXPORTED is
controlled by ``settings.observability.otlp_endpoint`` — set to e.g.
``http://localhost:4317`` to push to a local Jaeger/Tempo/Honeycomb collector,
leave unset and spans are discarded in-process.
"""
from __future__ import annotations

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import (
    SERVICE_NAME,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider

log = structlog.get_logger(__name__)


def init_tracing(
    service_name: str = "platform-api",
    *,
    otlp_endpoint: str | None = None,
    otel_insecure: bool = True,
    service_version: str | None = None,
) -> None:
    attrs: dict[str, str] = {SERVICE_NAME: service_name}
    if service_version:
        attrs[SERVICE_VERSION] = service_version
    resource = Resource.create(attrs)
    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError:
            log.warning(
                "tracing.otlp_exporter.skipped reason=package_missing",
                otlp_endpoint=otlp_endpoint,
            )
        else:
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=otel_insecure)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            log.info(
                "tracing.otlp_exporter.enabled",
                endpoint=otlp_endpoint,
                insecure=otel_insecure,
            )
    else:
        log.info("tracing.otlp_exporter.disabled reason=no_endpoint")

    trace.set_tracer_provider(provider)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
