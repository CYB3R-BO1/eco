"""FastAPI lifespan — connect the data tier on startup, disconnect on shutdown.

Connection order is fastest-to-slowest (Postgres → Redis → Neo4j); shutdown is
the reverse. Failures during ``connect()`` propagate and prevent the app from
accepting traffic — that's deliberate: a half-up service that 500s every
request is worse than one that fails to start.

Phase 2 also constructs the IOC-pipeline services (EventEmitter,
EvidenceStore, EntityResolutionService, EnrichmentExecutor, LifecycleManager,
BackgroundTaskRunner, IngestionPipeline) and parks them on ``app.state`` so
the FastAPI ``Depends`` providers in ``apps/api/dependencies.py`` can resolve
them without reaching for module-level globals.

Phase 3 adds: SchemaValidator + RejectionStore + GraphCorrelator. The
rewritten GraphService composes Validator + RejectionStore + EventEmitter
+ Neo4jClient. The IngestionPipeline receives the GraphCorrelator so it
can run the CORRELATING phase between ENRICHING and COMPLETED.

Phase 4 adds: FirewallPolicy + PromptAnalysisPipeline + PolicyEngine +
OutputValidator + FirewallAuditStore + FirewallGraphCorrelator composed
into a single FirewallService. The service owns its own investigation
lifecycle (one investigation per /firewall/decision) and shares the
EventEmitter, EvidenceStore, LifecycleManager, and GraphService with the
Phase 1–3 plumbing.
"""
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI

from agents.enrichment.agent import EnrichmentAgent
from agents.ioc_correlation.agent import IOCCorrelationAgent
from agents.reasoning.agent import ReasoningAgent
from apps.api.metrics_app import create_metrics_app
from core.cache.redis import RedisClient
from core.config.settings import Settings, get_settings
from core.database.postgres import Database
from core.events.emitter import EventEmitter
from core.llm.budget import InvestigationTokenBudget
from core.llm.client import build_llm_client
from core.observability.instrumentation import (
    instrument_httpx,
    instrument_neo4j,
    instrument_redis,
    instrument_sqlalchemy,
)
from core.database.slow_query_log import install_slow_query_logger
from core.scheduler import build_scheduler
from core.scheduler.jobs import retention_dlq, retention_events, retention_evidence, secure_deletion
from evidence.store import EvidenceStore
from firewall.analysis.llm_classifier import NullClassifier, OpenAIClassifier
from firewall.audit.store import FirewallAuditStore
from firewall.correlation.correlator import FirewallGraphCorrelator
from firewall.output_validation.validator import OutputValidator
from firewall.pipeline import PromptAnalysisPipeline
from firewall.policy.engine import PolicyEngine
from firewall.policy.policy import FirewallPolicy
from firewall.rules.engine import RulesEngine
from firewall.service import FirewallService
from graph.correlation.correlator import GraphCorrelator
from graph.governance.rejection_store import RejectionStore
from graph.governance.validator import SchemaValidator
from graph.graph_service.service import GraphService
from graph.neo4j.driver import Neo4jClient
from investigation.background import BackgroundTaskRunner
from investigation.enrichment.executor import EnrichmentExecutor
from investigation.enrichment.providers import default_providers
from investigation.enrichment.registry import ProviderRegistry
from investigation.ingestion.pipeline import IngestionPipeline
from investigation.lifecycle.manager import LifecycleManager
from orchestration.dlq.store import DeadLetterStore
from orchestration.memory.audit import MemoryAuditLogger
from orchestration.retry.circuit_breaker import CircuitBreakerRegistry
from orchestration.runtime.checkpointer import (
    CheckpointerKind,
    build_checkpointer,
    setup_checkpointer,
)
from orchestration.service import OrchestrationService
from orchestration.workflows.firewall import (
    FirewallWorkflowDeps,
    build_firewall_graph,
)
from orchestration.workflows.investigation import (
    InvestigationWorkflowDeps,
    build_investigation_graph,
)
from resolution.service import EntityResolutionService

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = getattr(app.state, "settings", None) or get_settings()

    db = Database(settings.postgres)
    redis_client = RedisClient(settings.redis)
    neo4j_client = Neo4jClient(settings.neo4j)

    log.info("lifespan.startup.begin", environment=settings.environment)

    await db.connect()
    await redis_client.connect()
    await neo4j_client.connect()

    # Phase 6 WP10 — slow-query listener. Template + SHA-256 of params only;
    # never the bound values themselves (invariant #12).
    if db._engine is not None:  # connect() guarantees this; noqa: SLF001
        install_slow_query_logger(
            db._engine,  # noqa: SLF001 — engine is meant to be reachable here
            threshold_ms=settings.observability.slow_query_threshold_ms,
        )

    # Phase 6 — OpenTelemetry library instrumentation. Each call is a no-op
    # if the optional instrumentation package isn't installed. Only meaningful
    # when otel_enabled is true, since with no exporter the spans go nowhere.
    if settings.observability.otel_enabled:
        instrument_sqlalchemy(db.engine)
        instrument_redis()
        instrument_httpx()
        instrument_neo4j()

    # Phase 6 — Prometheus metrics server on a separate port. Runs as a
    # sibling asyncio task; cancelled cleanly on shutdown.
    metrics_task: asyncio.Task[None] | None = None
    metrics_server: uvicorn.Server | None = None
    if settings.observability.metrics_enabled:
        metrics_config = uvicorn.Config(
            app=create_metrics_app(),
            host=settings.observability.metrics_bind_host,
            port=settings.observability.metrics_port,
            log_level="warning",
            lifespan="off",
            access_log=False,
        )
        metrics_server = uvicorn.Server(metrics_config)
        metrics_server.config.setup_event_loop()
        metrics_task = asyncio.create_task(
            metrics_server.serve(), name="metrics-server"
        )
        log.info(
            "lifespan.metrics_server.started",
            host=settings.observability.metrics_bind_host,
            port=settings.observability.metrics_port,
        )

    # Phase 2 services
    event_emitter = EventEmitter()
    evidence_store = EvidenceStore()
    resolver = EntityResolutionService()
    registry = ProviderRegistry(default_providers())
    enrichment_executor = EnrichmentExecutor(
        registry=registry,
        database=db,
        redis=redis_client,
        evidence_store=evidence_store,
        event_emitter=event_emitter,
    )
    lifecycle_manager = LifecycleManager(event_emitter)
    background_runner = BackgroundTaskRunner(max_concurrent=10)

    # Phase 3 services — schema governance + graph gateway + correlator.
    schema_validator = SchemaValidator()
    rejection_store = RejectionStore(event_emitter)
    graph_service = GraphService(
        client=neo4j_client,
        validator=schema_validator,
        rejection_store=rejection_store,
        event_emitter=event_emitter,
    )
    graph_correlator = GraphCorrelator(
        database=db,
        graph_service=graph_service,
        event_emitter=event_emitter,
    )

    ingestion_pipeline = IngestionPipeline(
        database=db,
        evidence_store=evidence_store,
        event_emitter=event_emitter,
        resolver=resolver,
        enrichment_executor=enrichment_executor,
        lifecycle_manager=lifecycle_manager,
        background_runner=background_runner,
        graph_correlator=graph_correlator,
        graph_service=graph_service,
    )

    # Phase 5 — LLM client (real if LLM_API_KEY is set, stub otherwise).
    llm_client = build_llm_client(settings.llm)

    # Phase 4 services — AI firewall middleware.
    firewall_policy = FirewallPolicy(
        block_threshold=settings.firewall.block_threshold,
        sanitize_threshold=settings.firewall.sanitize_threshold,
        review_threshold=settings.firewall.review_threshold,
        finding_weight_floor=settings.firewall.finding_weight_floor,
        pii_masking_enabled=settings.firewall.pii_masking_enabled,
    )
    firewall_audit_store = FirewallAuditStore()
    # When the LLM has a real provider configured, upgrade the classifier
    # from Phase 4's NullClassifier to the OpenAI-backed implementation.
    llm_classifier = (
        OpenAIClassifier(llm=llm_client)
        if settings.llm.has_api_key
        else NullClassifier()
    )
    firewall_pipeline = PromptAnalysisPipeline(
        policy=firewall_policy,
        rules_engine=RulesEngine(),
        llm_classifier=llm_classifier,
        detection_timeout_ms=settings.firewall.detection_timeout_ms,
    )
    firewall_policy_engine = PolicyEngine(firewall_policy)
    firewall_output_validator = OutputValidator(firewall_policy)
    firewall_graph_correlator = FirewallGraphCorrelator(
        graph_service=graph_service,
        event_emitter=event_emitter,
        policy=firewall_policy,
    )
    firewall_service = FirewallService(
        settings=settings.firewall,
        database=db,
        evidence_store=evidence_store,
        event_emitter=event_emitter,
        lifecycle_manager=lifecycle_manager,
        audit_store=firewall_audit_store,
        graph_service=graph_service,
        graph_correlator=firewall_graph_correlator,
        pipeline=firewall_pipeline,
        policy_engine=firewall_policy_engine,
        output_validator=firewall_output_validator,
    )

    # Phase 5 — orchestration runtime. Wraps Phase 2/4 services in
    # LangGraph nodes; owns workflow-run lifecycle + bounded memory + DLQs.
    token_budget = InvestigationTokenBudget(
        redis_client,
        max_tokens_per_investigation=settings.llm.max_tokens_per_investigation,
    )
    circuit_breakers = CircuitBreakerRegistry(
        open_after_failures=settings.orchestration.circuit_open_after_failures,
        window_seconds=settings.orchestration.circuit_window_seconds,
        open_duration_seconds=settings.orchestration.circuit_open_duration_seconds,
    )
    memory_audit_logger = MemoryAuditLogger()
    dead_letter_store = DeadLetterStore()

    enrichment_agent = EnrichmentAgent(
        executor=enrichment_executor,
        resolver=resolver,
    )
    correlation_agent = IOCCorrelationAgent(
        correlator=graph_correlator,
        graph_service=graph_service,
    )
    reasoning_agent = ReasoningAgent(
        llm=llm_client,
        firewall=firewall_service,
        policy_engine=firewall_policy_engine,
        evidence_store=evidence_store,
        prompt_safety_enabled=settings.orchestration.reasoning_prompt_safety_enabled,
    )

    # Checkpointer — postgres-backed when the optional package is available,
    # in-memory fallback otherwise. setup() is idempotent and creates the
    # langgraph_checkpoints tables on first run (not in our Alembic).
    checkpointer_ctx = await build_checkpointer(
        settings.postgres,
        prefer=CheckpointerKind.POSTGRES,
    )
    # AsyncPostgresSaver.from_conn_string returns an async context manager;
    # MemorySaver does not. Enter the cm if applicable so the saver has a live
    # connection pool for the lifetime of the app.
    if hasattr(checkpointer_ctx, "__aenter__"):
        checkpointer = await checkpointer_ctx.__aenter__()
        app.state._checkpointer_ctx = checkpointer_ctx
    else:
        checkpointer = checkpointer_ctx
        app.state._checkpointer_ctx = None
    try:
        await setup_checkpointer(checkpointer)
    except Exception:
        log.exception("lifespan.checkpointer_setup_failed_continuing_without_durability")

    investigation_deps = InvestigationWorkflowDeps(
        settings=settings.orchestration,
        database=db,
        redis=redis_client,
        event_emitter=event_emitter,
        evidence_store=evidence_store,
        lifecycle_manager=lifecycle_manager,
        llm=llm_client,
        token_budget=token_budget,
        circuit_breakers=circuit_breakers,
        memory_audit=memory_audit_logger,
        ingestion_pipeline=ingestion_pipeline,
        enrichment_agent=enrichment_agent,
        correlation_agent=correlation_agent,
        reasoning_agent=reasoning_agent,
    )
    firewall_deps = FirewallWorkflowDeps(
        settings=settings.orchestration,
        database=db,
        redis=redis_client,
        event_emitter=event_emitter,
        evidence_store=evidence_store,
        lifecycle_manager=lifecycle_manager,
        llm=llm_client,
        token_budget=token_budget,
        circuit_breakers=circuit_breakers,
        memory_audit=memory_audit_logger,
        firewall_service=firewall_service,
        reasoning_agent=reasoning_agent,
    )
    workflow_graphs = {
        "investigation": build_investigation_graph(
            investigation_deps, checkpointer=checkpointer
        ),
        "firewall": build_firewall_graph(firewall_deps, checkpointer=checkpointer),
    }
    orchestration_service = OrchestrationService(
        database=db,
        event_emitter=event_emitter,
        graphs=workflow_graphs,
    )

    app.state.db = db
    app.state.redis = redis_client
    app.state.neo4j = neo4j_client
    app.state.graph_service = graph_service
    app.state.schema_validator = schema_validator
    app.state.rejection_store = rejection_store
    app.state.graph_correlator = graph_correlator
    app.state.event_emitter = event_emitter
    app.state.evidence_store = evidence_store
    app.state.resolver = resolver
    app.state.enrichment_executor = enrichment_executor
    app.state.lifecycle_manager = lifecycle_manager
    app.state.background_runner = background_runner
    app.state.ingestion_pipeline = ingestion_pipeline
    app.state.firewall_service = firewall_service
    app.state.firewall_policy = firewall_policy
    app.state.firewall_audit_store = firewall_audit_store
    app.state.llm_client = llm_client
    app.state.token_budget = token_budget
    app.state.circuit_breakers = circuit_breakers
    app.state.memory_audit_logger = memory_audit_logger
    app.state.dead_letter_store = dead_letter_store
    app.state.orchestration_service = orchestration_service
    app.state.checkpointer = checkpointer

    # Phase 6 WP6 — embedded scheduler. APScheduler is optional; if not
    # installed (e.g. minimal test image), the scheduler is None and no
    # retention jobs run. Per-job advisory locks guard against multi-worker
    # fan-out (see core.scheduler.locks).
    scheduler = build_scheduler()
    if scheduler is not None:
        scheduler.add_job(
            retention_evidence.run,
            "cron",
            hour=settings.retention.evidence_cron_hour,
            minute=settings.retention.evidence_cron_minute,
            args=[db, settings.retention],
            id=retention_evidence.JOB_NAME,
        )
        scheduler.add_job(
            retention_events.run,
            "cron",
            hour=settings.retention.evidence_cron_hour,
            minute=settings.retention.evidence_cron_minute + 5,
            args=[db, settings.retention],
            id=retention_events.JOB_NAME,
        )
        scheduler.add_job(
            retention_dlq.run,
            "cron",
            hour=settings.retention.evidence_cron_hour,
            minute=settings.retention.evidence_cron_minute + 10,
            args=[db, settings.retention],
            id=retention_dlq.JOB_NAME,
        )
        scheduler.add_job(
            secure_deletion.run,
            "interval",
            seconds=settings.retention.secure_deletion_interval_seconds,
            args=[db, settings.retention],
            id=secure_deletion.JOB_NAME,
        )
        scheduler.start()
        log.info("lifespan.scheduler.started")
    app.state.scheduler = scheduler

    log.info("lifespan.startup.complete")

    try:
        yield
    finally:
        log.info("lifespan.shutdown.begin")
        if scheduler is not None:
            try:
                scheduler.shutdown(wait=False)
            except Exception:
                log.exception("lifespan.scheduler.shutdown_failed")
        await background_runner.drain(timeout=30.0)
        ctx = getattr(app.state, "_checkpointer_ctx", None)
        if ctx is not None:
            try:
                await ctx.__aexit__(None, None, None)
            except Exception:
                log.exception("lifespan.checkpointer_exit_failed")
        if metrics_server is not None:
            metrics_server.should_exit = True
        if metrics_task is not None:
            metrics_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await metrics_task
            log.info("lifespan.metrics_server.stopped")
        await neo4j_client.disconnect()
        await redis_client.disconnect()
        await db.disconnect()
        log.info("lifespan.shutdown.complete")
