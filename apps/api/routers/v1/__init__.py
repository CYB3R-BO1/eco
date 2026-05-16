"""v1 API router.

Phase 1 leaves this empty. Sub-routers for investigations, IOCs, graph, and
firewall mount here in later phases via ``router.include_router(...)``.
"""
from fastapi import APIRouter

router = APIRouter()
