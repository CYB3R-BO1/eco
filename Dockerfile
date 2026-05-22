# syntax=docker/dockerfile:1.7

# ---------- base ----------
# Phase 6 WP8: pin the base image tag to a digest in production builds via
# the CI workflow's --build-arg PYTHON_DIGEST=sha256:... . Pinning here too
# would force every developer to update the digest on every base-image
# refresh, so the explicit pin lives in the release workflow.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# ---------- deps ----------
# Install only third-party dependencies. PYTHONPATH=/app handles imports, so
# the bind-mount in dev is seamless. Dep list parsed out of pyproject.toml
# via stdlib tomllib — single source of truth. Prefer requirements.lock when
# present (CI generates it; reproducible builds for prod).
FROM base AS deps
COPY pyproject.toml ./
COPY requirements.lock* /tmp/
RUN pip install --upgrade pip \
    && if [ -s /tmp/requirements.lock ]; then \
         echo "[deps] installing from requirements.lock"; \
         pip install -r /tmp/requirements.lock; \
       else \
         echo "[deps] no lock file — resolving from pyproject.toml"; \
         python -c "import tomllib; \
c=tomllib.load(open('pyproject.toml','rb'))['project']; \
print('\n'.join(c['dependencies']+c.get('optional-dependencies',{}).get('dev',[])))" \
           > /tmp/requirements.txt \
         && pip install -r /tmp/requirements.txt; \
       fi

# ---------- dev ----------
FROM deps AS dev
COPY . .
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/live || exit 1
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------- prod ----------
# Phase 6 WP8: drop build-essential from the runtime layer. Start from
# python:3.12-slim again so the final image doesn't carry the compiler
# toolchain; copy only the site-packages tree from the deps stage.
FROM python:3.12-slim AS prod

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# libpq5 is the runtime shared lib psycopg/asyncpg need; curl is needed by
# HEALTHCHECK. No build-essential, no libpq-dev — the deps stage already
# compiled what needed compiling.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY . .
RUN chown -R appuser:appuser /app

USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/live || exit 1
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
