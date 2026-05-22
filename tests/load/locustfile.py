"""Phase 6 WP10 — Locust load test harness.

Three scenarios run concurrently when invoked with ``locust -f``:

- ``IOCIngestBurst``        — sustained 1000 IOCs / 60s through
  ``POST /api/v1/iocs/ingest`` to baseline ingestion throughput.
- ``GraphTraversalSteady``  — 50 RPS reads against
  ``GET /api/v1/graph/node/{id}`` to validate read latency under
  steady-state load.
- ``InvestigationLifecycle``— end-to-end (ingest → enrich → summarize)
  at 5 RPS, the most expensive code path.

Auth: tokens are issued lazily via the bootstrap-secret endpoint and
cached on the locust ``User``. Set ``BOOTSTRAP_SECRET`` env var when
running — defaults match the dev compose stack.
"""
from __future__ import annotations

import os
import uuid

from locust import HttpUser, between, task

BOOTSTRAP_SECRET = os.environ.get("BOOTSTRAP_SECRET", "")


class _AuthMixin:
    """Lazy-mint a token on first task call. Avoids hammering /tokens/issue."""

    _token: str | None = None

    def _bearer(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        resp = self.client.post(  # type: ignore[attr-defined]
            "/api/v1/tokens/issue",
            json={"subject": f"locust-{uuid.uuid4().hex[:8]}", "role": "analyst"},
            headers={"X-Admin-Bootstrap-Secret": BOOTSTRAP_SECRET},
            name="/tokens/issue (setup)",
        )
        if resp.status_code != 201:
            return {}
        self._token = resp.json()["token"]
        return {"Authorization": f"Bearer {self._token}"}


class IOCIngestBurst(_AuthMixin, HttpUser):
    wait_time = between(0.05, 0.1)  # ~10-20 RPS per user → 1000/60s with 10 users

    @task
    def ingest(self) -> None:
        self.client.post(
            "/api/v1/iocs/ingest",
            json={"artifact": f"1.2.3.{uuid.uuid4().int % 255} phishing.example"},
            headers=self._bearer(),
            name="POST /iocs/ingest",
        )


class GraphTraversalSteady(_AuthMixin, HttpUser):
    wait_time = between(0.02, 0.02)

    @task
    def neighbors(self) -> None:
        self.client.get(
            f"/api/v1/graph/node/{uuid.uuid4()}",
            headers=self._bearer(),
            name="GET /graph/node/{id}",
        )


class InvestigationLifecycle(_AuthMixin, HttpUser):
    wait_time = between(0.2, 0.2)

    @task
    def cycle(self) -> None:
        ingest = self.client.post(
            "/api/v1/iocs/ingest",
            json={"artifact": "lifecycle.example 8.8.8.8"},
            headers=self._bearer(),
            name="POST /iocs/ingest (lifecycle)",
        )
        if ingest.status_code != 202:
            return
        inv_id = ingest.json().get("investigation_id")
        if not inv_id:
            return
        self.client.get(
            f"/api/v1/investigations/{inv_id}",
            headers=self._bearer(),
            name="GET /investigations/{id} (lifecycle)",
        )
