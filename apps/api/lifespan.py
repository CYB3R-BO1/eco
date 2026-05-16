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
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from core.cache.redis import RedisClient
from core.config.settings import Settings, get_settings
from core.database.postgres import Database
from core.events.emitter import EventEmitter
from evidence.store import EvidenceStore
from graph.graph_service.service import GraphService
from graph.neo4j.driver import Neo4jClient
from investigation.background import BackgroundTaskRunner
from investigation.enrichment.executor import EnrichmentExecutor
from investigation.enrichment.providers import default_providers
from investigation.enrichment.registry import ProviderRegistry
from investigation.ingestion.pipeline import IngestionPipeline
from investigation.lifecycle.manager import LifecycleManager
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

    graph_service = GraphService(neo4j_client)

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
    ingestion_pipeline = IngestionPipeline(
        database=db,
        evidence_store=evidence_store,
        event_emitter=event_emitter,
        resolver=resolver,
        enrichment_executor=enrichment_executor,
        lifecycle_manager=lifecycle_manager,
        background_runner=background_runner,
    )

    app.state.db = db
    app.state.redis = redis_client
    app.state.neo4j = neo4j_client
    app.state.graph_service = graph_service
    app.state.event_emitter = event_emitter
    app.state.evidence_store = evidence_store
    app.state.resolver = resolver
    app.state.enrichment_executor = enrichment_executor
    app.state.lifecycle_manager = lifecycle_manager
    app.state.background_runner = background_runner
    app.state.ingestion_pipeline = ingestion_pipeline

    log.info("lifespan.startup.complete")

    try:
        yield
    finally:
        log.info("lifespan.shutdown.begin")
        await background_runner.drain(timeout=30.0)
        await neo4j_client.disconnect()
        await redis_client.disconnect()
        await db.disconnect()
        log.info("lifespan.shutdown.complete")
