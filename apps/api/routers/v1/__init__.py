"""v1 API router aggregator."""
from fastapi import APIRouter

from apps.api.routers.v1.evidence import router as evidence_router
from apps.api.routers.v1.firewall import router as firewall_router
from apps.api.routers.v1.graphs import router as graphs_router
from apps.api.routers.v1.investigations import router as investigations_router
from apps.api.routers.v1.iocs import router as iocs_router

router = APIRouter()
router.include_router(iocs_router)
router.include_router(investigations_router)
router.include_router(evidence_router)
router.include_router(graphs_router)
router.include_router(firewall_router)
