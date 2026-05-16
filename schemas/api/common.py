from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorPayload(BaseModel):
    code: int
    message: str
    details: list[Any] | dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorPayload
