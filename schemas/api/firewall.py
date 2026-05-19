"""Pydantic DTOs for the AI Firewall endpoints.

The wire shape mirrors the internal :mod:`firewall.models.reports`
dataclasses but adds the Pydantic-level validation we want at the
boundary (max prompt length, enum values, threshold bounds). Internal
modules use the dataclasses for performance; the routers translate at
the edge.
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModelTargetDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)


class WorkflowContextDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_id: uuid.UUID
    route: str | None = Field(default=None, max_length=256)


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1)
    target_model: ModelTargetDTO
    workflow_context: WorkflowContextDTO | None = None


class DecisionRequest(AnalyzeRequest):
    """Same body as analyze."""


class ValidateOutputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response: str = Field(min_length=1)
    prompt_fingerprint: str = Field(min_length=64, max_length=64)
    investigation_id: uuid.UUID | None = None
    target_model: ModelTargetDTO | None = None


class SignalDTO(BaseModel):
    layer: str
    detector_id: str
    category: str
    severity: float
    weight: float
    evidence_span: tuple[int, int] | None = None
    explanation: str
    rule_id: str | None = None
    pattern_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExplainabilityDTO(BaseModel):
    matched_rules: list[str]
    triggered_patterns: list[str]
    reasoning_summary: str
    policy_hash: str
    policy_references: list[str] = Field(default_factory=list)


class RedactionDTO(BaseModel):
    start: int
    end: int
    rule_id: str
    replacement: str
    reason: str


class AnalysisResponse(BaseModel):
    prompt_fingerprint: str
    prompt_length: int
    normalized_length: int
    risk_score: float
    risk_level: str
    classifications: list[str]
    signals: list[SignalDTO]
    explainability: ExplainabilityDTO
    latency_ms: int
    llm_classifier_available: bool
    truncated: bool


class DecisionResponse(BaseModel):
    investigation_id: uuid.UUID
    firewall_event_id: uuid.UUID
    decision: str
    risk_score: float
    risk_level: str
    classifications: list[str]
    prompt_fingerprint: str
    sanitized_prompt: str | None = None
    redactions: list[RedactionDTO] = Field(default_factory=list)
    explainability: ExplainabilityDTO
    latency_ms: int
    llm_classifier_available: bool
    truncated: bool


class ValidateOutputResponse(BaseModel):
    response_fingerprint: str
    result: str
    sanitized_response: str | None = None
    findings: list[str]
    redactions: list[RedactionDTO] = Field(default_factory=list)
    reasoning_summary: str
    policy_hash: str
    latency_ms: int
