"""Central Prometheus metric registry.

Every metric used anywhere in the platform is declared here. Declaring them
in one place lets a unit test enumerate the surface and fail if a metric is
silently dropped — which would otherwise be invisible.

Labels are always bounded enums (route templates, status codes, agent names,
decisions). Investigation/workflow IDs MUST NOT become labels — they would
explode cardinality and risk leaking content via metric names. Use the
``hash_bucket`` helper to bucket an ID into an 8-char SHA-256 prefix when a
per-investigation gauge is genuinely needed.
"""
from __future__ import annotations

import hashlib
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.metrics import MetricWrapperBase

# Single registry shared by every callsite. Tests can import this and assert
# membership of metric names.
REGISTRY: Final[CollectorRegistry] = CollectorRegistry()

# Metric name → wrapper, used by tests and the no-prompt-leakage check.
_REGISTERED: dict[str, MetricWrapperBase] = {}


def _register(metric: MetricWrapperBase) -> MetricWrapperBase:
    name = metric._name  # noqa: SLF001 - prometheus_client public name attr
    if name in _REGISTERED:
        raise RuntimeError(f"metric {name!r} already registered")
    _REGISTERED[name] = metric
    return metric


def registered_metric_names() -> list[str]:
    """Names of every metric declared in this module, sorted."""
    return sorted(_REGISTERED.keys())


def hash_bucket(value: str, width: int = 8) -> str:
    """Stable 8-char bucket for high-cardinality IDs.

    Use this BEFORE assigning a per-investigation value to a metric label so
    we never put raw UUIDs in label space (cardinality + privacy).
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:width]


# ---------------------------------------------------------------------------
# WP1 — HTTP layer
# ---------------------------------------------------------------------------

HTTP_REQUESTS_TOTAL: Counter = _register(  # type: ignore[assignment]
    Counter(
        "http_requests_total",
        "Total HTTP requests handled by the API.",
        labelnames=("method", "route", "status"),
        registry=REGISTRY,
    )
)

HTTP_REQUEST_DURATION_SECONDS: Histogram = _register(  # type: ignore[assignment]
    Histogram(
        "http_request_duration_seconds",
        "HTTP request handling latency.",
        labelnames=("method", "route"),
        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        registry=REGISTRY,
    )
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# WP2 — Domain metrics
# ---------------------------------------------------------------------------

# Graph
GRAPH_TRAVERSAL_DURATION_SECONDS: Histogram = _register(  # type: ignore[assignment]
    Histogram(
        "ai_security_graph_traversal_duration_seconds",
        "Time spent traversing the graph by operation type.",
        labelnames=("operation", "depth_bucket"),
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
        registry=REGISTRY,
    )
)

GRAPH_WRITES_TOTAL: Counter = _register(  # type: ignore[assignment]
    Counter(
        "ai_security_graph_writes_total",
        "Graph mutations attempted, by node/edge label and operation.",
        labelnames=("label", "op"),
        registry=REGISTRY,
    )
)

GRAPH_RELATIONSHIPS: Gauge = _register(  # type: ignore[assignment]
    Gauge(
        "ai_security_graph_relationships",
        "Sampled relationship count per node label.",
        labelnames=("node_label",),
        registry=REGISTRY,
    )
)

# Enrichment
ENRICHMENT_TOTAL: Counter = _register(  # type: ignore[assignment]
    Counter(
        "ai_security_enrichment_total",
        "Enrichment provider calls, by source and outcome.",
        labelnames=("source", "status"),
        registry=REGISTRY,
    )
)

# Firewall
FIREWALL_DECISIONS_TOTAL: Counter = _register(  # type: ignore[assignment]
    Counter(
        "ai_security_firewall_decisions_total",
        "AI Firewall decisions, by terminal action and risk bucket.",
        labelnames=("decision", "risk_bucket"),
        registry=REGISTRY,
    )
)

FIREWALL_PIPELINE_DURATION_SECONDS: Histogram = _register(  # type: ignore[assignment]
    Histogram(
        "ai_security_firewall_pipeline_duration_seconds",
        "Latency of each Firewall analysis stage.",
        labelnames=("stage",),
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
        registry=REGISTRY,
    )
)

# Workflows
WORKFLOW_DURATION_SECONDS: Histogram = _register(  # type: ignore[assignment]
    Histogram(
        "ai_security_workflow_duration_seconds",
        "End-to-end workflow execution time, by workflow and terminal state.",
        labelnames=("workflow_name", "terminal_state"),
        buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
        registry=REGISTRY,
    )
)

WORKFLOW_ACTIVE: Gauge = _register(  # type: ignore[assignment]
    Gauge(
        "ai_security_workflow_active",
        "Number of in-flight workflow runs (BackgroundTaskRunner._tasks).",
        registry=REGISTRY,
    )
)

# Agents
AGENT_RUN_DURATION_SECONDS: Histogram = _register(  # type: ignore[assignment]
    Histogram(
        "ai_security_agent_run_duration_seconds",
        "Per-agent execution time, by agent and outcome.",
        labelnames=("agent_name", "outcome"),
        buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
        registry=REGISTRY,
    )
)

AGENT_RETRIES_TOTAL: Counter = _register(  # type: ignore[assignment]
    Counter(
        "ai_security_agent_retries_total",
        "Agent retries fired, by agent and reason class.",
        labelnames=("agent_name", "reason"),
        registry=REGISTRY,
    )
)

CIRCUIT_BREAKER_STATE: Gauge = _register(  # type: ignore[assignment]
    Gauge(
        "ai_security_circuit_breaker_state",
        "Circuit breaker state: 0=closed, 1=half_open, 2=open.",
        labelnames=("agent_name",),
        registry=REGISTRY,
    )
)

# LLM
LLM_TOKENS_USED_TOTAL: Counter = _register(  # type: ignore[assignment]
    Counter(
        "ai_security_llm_tokens_used_total",
        "Tokens consumed against the per-investigation budget.",
        labelnames=("model", "phase"),
        registry=REGISTRY,
    )
)

# DLQ
DLQ_DEPTH: Gauge = _register(  # type: ignore[assignment]
    Gauge(
        "ai_security_dlq_depth",
        "Current depth (entry count) of each dead-letter queue.",
        labelnames=("queue_name",),
        registry=REGISTRY,
    )
)

# Memory
MEMORY_TOKENS_IN_USE: Gauge = _register(  # type: ignore[assignment]
    Gauge(
        "ai_security_memory_tokens_in_use",
        "Tokens currently held in investigation-scoped memory.",
        labelnames=("investigation_id_bucket",),
        registry=REGISTRY,
    )
)

# Retention (WP6 — declared here so WP2 owns metric surface)
RETENTION_JOB_RUNS_TOTAL: Counter = _register(  # type: ignore[assignment]
    Counter(
        "ai_security_retention_job_runs_total",
        "Retention/cleanup job invocations, by job and outcome.",
        labelnames=("job", "outcome"),
        registry=REGISTRY,
    )
)

# Auth (WP3) — bounded ``reason`` label: missing|malformed|invalid_signature|
# expired|wrong_issuer|wrong_audience|unknown_kid.
AUTH_DENIALS_TOTAL: Counter = _register(  # type: ignore[assignment]
    Counter(
        "auth_denials_total",
        "Bearer-token authentication failures, by structured reason.",
        labelnames=("reason",),
        registry=REGISTRY,
    )
)

# RBAC (WP4) — bounded ``role`` and ``permission`` labels (closed sets in
# core.security.rbac). High cardinality is impossible because both are enums.
PERMISSION_DENIALS_TOTAL: Counter = _register(  # type: ignore[assignment]
    Counter(
        "permission_denials_total",
        "RBAC denials, by caller role and required permission.",
        labelnames=("role", "permission"),
        registry=REGISTRY,
    )
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@contextmanager
def time_histogram(histogram: Histogram, **labels: str) -> Iterator[None]:
    """Time the wrapped block and observe the duration on ``histogram``."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        if labels:
            histogram.labels(**labels).observe(elapsed)
        else:
            histogram.observe(elapsed)


def depth_bucket(depth: int) -> str:
    """Coarse bucket label for a traversal depth."""
    if depth <= 1:
        return "1"
    if depth <= 2:
        return "2"
    if depth <= 4:
        return "3-4"
    if depth <= 8:
        return "5-8"
    return "9+"


def risk_bucket(risk: float) -> str:
    """Bucket a 0..1 firewall risk score into a label-safe band."""
    if risk < 0.20:
        return "low"
    if risk < 0.40:
        return "guarded"
    if risk < 0.65:
        return "elevated"
    if risk < 0.85:
        return "high"
    return "critical"


def render_latest() -> bytes:
    """Render the registry in Prometheus text-exposition format."""
    return generate_latest(REGISTRY)
