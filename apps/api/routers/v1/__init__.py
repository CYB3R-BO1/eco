"""v1 API router aggregator.

Phase 6 WP4: every route declares its own ``Depends(requires(Permission.X))``
which transitively pulls in :func:`apps.api.auth.get_current_principal`,
so authentication AND authorization both run before the handler. The
``tokens`` router is the only exception — ``/tokens/issue`` and
``/tokens/rotate-key`` are gated by the bootstrap secret (chicken-and-egg
for the very first token), and ``/tokens/whoami`` only needs the bare
principal (no permission required).
"""
from fastapi import APIRouter

from apps.api.routers.v1.agents import router as agents_router
from apps.api.routers.v1.evidence import router as evidence_router
from apps.api.routers.v1.firewall import router as firewall_router
from apps.api.routers.v1.graphs import router as graphs_router
from apps.api.routers.v1.investigations import router as investigations_router
from apps.api.routers.v1.iocs import router as iocs_router
from apps.api.routers.v1.tokens import router as tokens_router
from apps.api.routers.v1.workflows import router as workflows_router

router = APIRouter()
router.include_router(tokens_router)
router.include_router(iocs_router)
router.include_router(investigations_router)
router.include_router(evidence_router)
router.include_router(graphs_router)
router.include_router(firewall_router)
router.include_router(agents_router)
router.include_router(workflows_router)
