from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class ComponentStatus(BaseModel):
    name: str
    healthy: bool


class ReadinessResponse(BaseModel):
    status: str
    components: list[ComponentStatus]
