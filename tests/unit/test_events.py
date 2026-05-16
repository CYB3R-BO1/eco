"""Static / pure tests for the canonical event model.

We don't instantiate ``EventEmitter`` here — that needs a DB session. The
emitter's behavior is exercised in the integration tests. These checks only
prove the domain model and the emitter's public surface are right.
"""
from __future__ import annotations

import uuid

from core.events.emitter import EventEmitter
from core.events.event import Event
from core.events.types import EventType


def test_event_defaults_fill_in() -> None:
    e = Event(event_type=EventType.IOC_INGESTED, source="test")
    assert isinstance(e.event_id, uuid.UUID)
    assert e.timestamp is not None
    assert e.actor == "system"
    assert e.evidence_refs == []
    assert e.event_metadata == {}
    assert e.confidence == 1.0


def test_event_is_frozen() -> None:
    e = Event(event_type=EventType.IOC_INGESTED, source="test")
    try:
        e.source = "tampered"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("Event should be immutable")


def test_emitter_exposes_no_update_or_delete() -> None:
    forbidden = {"update", "delete", "remove", "modify", "patch", "set"}
    public = {name for name in dir(EventEmitter) if not name.startswith("_")}
    assert forbidden.isdisjoint(public), public & forbidden


def test_event_metadata_alias() -> None:
    e = Event.model_validate(
        {"event_type": "IOC_INGESTED", "source": "test", "metadata": {"k": "v"}}
    )
    assert e.event_metadata == {"k": "v"}
