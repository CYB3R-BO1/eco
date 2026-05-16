"""FastAPI dependency providers.

Long-lived components (``Database``, ``RedisClient``, ``Neo4jClient``,
``GraphService``, plus the Phase 2 pipeline services) are constructed in the
lifespan and parked on ``app.state``. These providers expose them via
FastAPI's ``Depends`` system so routes stay testable. Prefer the ``*Dep``
``Annotated`` aliases in route signatures.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache.redis import RedisClient
from core.config.settings import Settings, get_settings
from core.database.postgres import Database
from core.events.emitter import EventEmitter
from evidence.store import EvidenceStore
from graph.graph_service.service import GraphService
from graph.neo4j.driver import Neo4jClient
from investigation.background import BackgroundTaskRunner
from investigation.enrichment.executor import EnrichmentExecutor
from investigation.ingestion.pipeline import IngestionPipeline
from investigation.lifecycle.manager import LifecycleManager
from resolution.service import EntityResolutionService


def get_settings_dep() -> Settings:
    return get_settings()


def get_database(request: Request) -> Database:
    return request.app.state.db  # type: ignore[no-any-return]


def get_redis_client(request: Request) -> RedisClient:
    return request.app.state.redis  # type: ignore[no-any-return]


def get_neo4j_client(request: Request) -> Neo4jClient:
    return request.app.state.neo4j  # type: ignore[no-any-return]


def get_graph_service(request: Request) -> GraphService:
    return request.app.state.graph_service  # type: ignore[no-any-return]


def get_event_emitter(request: Request) -> EventEmitter:
    return request.app.state.event_emitter  # type: ignore[no-any-return]


def get_evidence_store(request: Request) -> EvidenceStore:
    return request.app.state.evidence_store  # type: ignore[no-any-return]


def get_resolver(request: Request) -> EntityResolutionService:
    return request.app.state.resolver  # type: ignore[no-any-return]


def get_enrichment_executor(request: Request) -> EnrichmentExecutor:
    return request.app.state.enrichment_executor  # type: ignore[no-any-return]


def get_lifecycle_manager(request: Request) -> LifecycleManager:
    return request.app.state.lifecycle_manager  # type: ignore[no-any-return]


def get_background_runner(request: Request) -> BackgroundTaskRunner:
    return request.app.state.background_runner  # type: ignore[no-any-return]


def get_ingestion_pipeline(request: Request) -> IngestionPipeline:
    return request.app.state.ingestion_pipeline  # type: ignore[no-any-return]


async def get_db_session(
    db: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[AsyncSession]:
    async with db.session() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DatabaseDep = Annotated[Database, Depends(get_database)]
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
RedisDep = Annotated[RedisClient, Depends(get_redis_client)]
Neo4jDep = Annotated[Neo4jClient, Depends(get_neo4j_client)]
GraphServiceDep = Annotated[GraphService, Depends(get_graph_service)]
EventEmitterDep = Annotated[EventEmitter, Depends(get_event_emitter)]
EvidenceStoreDep = Annotated[EvidenceStore, Depends(get_evidence_store)]
EntityResolutionDep = Annotated[EntityResolutionService, Depends(get_resolver)]
EnrichmentExecutorDep = Annotated[EnrichmentExecutor, Depends(get_enrichment_executor)]
LifecycleManagerDep = Annotated[LifecycleManager, Depends(get_lifecycle_manager)]
BackgroundRunnerDep = Annotated[BackgroundTaskRunner, Depends(get_background_runner)]
IngestionPipelineDep = Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)]
