# syntax=docker/dockerfile:1.7

# ---------- base ----------
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
# Install only third-party dependencies. We don't install our own package;
# PYTHONPATH=/app handles imports, which makes the bind-mount in dev seamless
# (no .egg-info gets shadowed). Dep list is parsed out of pyproject.toml via
# stdlib tomllib so there's a single source of truth.
FROM base AS deps
COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && python -c "import tomllib; \
c=tomllib.load(open('pyproject.toml','rb'))['project']; \
print('\n'.join(c['dependencies']+c.get('optional-dependencies',{}).get('dev',[])))" \
    > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt

# ---------- dev ----------
FROM deps AS dev
COPY . .
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------- prod ----------
FROM deps AS prod
COPY . .
RUN useradd --create-home --shell /bin/bash appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
