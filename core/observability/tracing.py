"""OpenTelemetry scaffold.

Phase 1 installs an in-process ``TracerProvider`` without any exporter. Calling
code can already start emitting spans via :func:`get_tracer`; a later phase
plugs in OTLP/Jaeger by adding a ``BatchSpanProcessor`` in :func:`init_tracing`
without touching any instrumentation sites.
"""
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider


def init_tracing(service_name: str = "platform-api") -> None:
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    # Phase 2+: provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(...)))
    trace.set_tracer_provider(provider)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
