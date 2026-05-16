# eco - An AI-Native Cybersecurity & AI Safety Platform — MVP Execution Plan

## Status

Draft v1.0

## Purpose

This document defines the engineering execution plan for building the MVP of an AI-native cybersecurity and AI safety platform focused on:

1. AI-for-Security
   - AI-powered IOC Correlation & Investigation Agent

2. Security-for-AI
   - Model-agnostic AI Firewall for prompt injection and jailbreak detection

The MVP is backend-first, modular, explainable, and designed for rapid iteration without premature infrastructure complexity.

---

# 1. Project Overview

## Vision

Build an AI-native cybersecurity and AI safety operating system that enables:

- AI-assisted cyber investigations
- explainable IOC correlation
- graph-driven threat analysis
- AI runtime security
- prompt injection and jailbreak defense
- composable security workflows

The system should function as a unified intelligence and defense platform where:

- investigations are explainable,
- AI decisions are traceable,
- workflows are composable,
- and all security events become graph-connected entities.

---

# MVP Scope

The MVP includes only two flagship capabilities:

## AI-for-Security

An AI-powered investigation engine capable of:

- ingesting security artifacts
- extracting indicators of compromise (IOCs)
- enriching indicators
- correlating relationships
- generating investigation context
- storing evidence in a graph
- performing AI-assisted reasoning

---

## Security-for-AI

A model-agnostic AI Firewall capable of:

- intercepting prompts and outputs
- detecting prompt injection attempts
- detecting jailbreak behavior
- assigning risk scores
- blocking or sanitizing malicious interactions
- generating explainable decisions
- logging security events into the Investigation Graph

---

# MVP Boundaries

The MVP intentionally excludes:

- full SIEM functionality
- endpoint agents
- cloud-native CSPM tooling
- malware sandboxing
- autonomous remediation
- advanced SOAR execution
- multi-tenant SaaS architecture
- distributed microservices
- frontend-heavy dashboards
- streaming telemetry pipelines at scale

---

# Non-Goals

The MVP is NOT intended to:

- replace enterprise SIEM platforms
- support petabyte-scale telemetry
- fully automate incident response
- support every AI provider
- perform advanced malware reverse engineering
- implement full SOC workflows

---

# Guiding Principles

## 1. Explainability First

Every AI decision must be:

- traceable
- inspectable
- auditable
- reproducible

---

## 2. Backend-First Architecture

Focus on:

- APIs
- orchestration
- graph intelligence
- security workflows

UI implementation is intentionally deferred.

---

## 3. Modular Design

All major capabilities must be independently replaceable.

Avoid tightly coupled components.

---

## 4. Realistic MVP Scope

Prioritize execution velocity over architectural perfection.

Avoid premature optimization.

---

## 5. AI as an Assistant, Not an Oracle

AI outputs must be:

- evidence-backed
- confidence-scored
- reviewable

---

---

# 2. Core MVP Features

# Canonical Event Model

**CRITICAL: All workflow events must conform to this schema.**

Without canonical events, graph consistency breaks, tracing becomes impossible, and workflows become chaotic.

Every event must contain:

- `event_id` — unique identifier (UUID)
- `event_type` — machine-readable type (IOC_INGESTED, IOC_ENRICHED, GRAPH_UPDATED, INVESTIGATION_CREATED, PROMPT_ANALYZED, FIREWALL_BLOCKED, AGENT_COMPLETED)
- `timestamp` — ISO8601 UTC
- `source` — originating service/module
- `investigation_id` — parent investigation UUID (nullable for system events)
- `correlation_id` — tracing ID for distributed execution
- `actor` — agent/user/service performing action
- `target` — entity being acted upon
- `evidence_refs` — list of evidence IDs this event references
- `metadata` — JSON object for additional context
- `confidence` — float 0.0–1.0, confidence in event accuracy

All events are **immutable** and stored in PostgreSQL `investigation_events` table.

Events become:

- graph edges
- audit records
- reasoning references
- investigation timeline entries

---

# AI-for-Security Features

## IOC Ingestion

Support ingestion of:

- URLs
- domains
- IP addresses
- hashes
- emails
- raw logs
- alert payloads
- JSON evidence objects

Input methods:

- REST API
- file upload
- webhook ingestion

---

## IOC Extraction

Extract:

- URLs
- domains
- IPs
- hashes
- email addresses
- CVEs
- user agents

Techniques:

- regex extraction
- parser pipelines
- AI-assisted extraction
- structured enrichment parsing

---

## Enrichment Pipelines

Enrichment sources:

- WHOIS
- DNS
- GeoIP
- VirusTotal-compatible APIs
- AbuseIPDB-compatible APIs
- passive DNS
- internal knowledge graph context

Each enrichment result becomes graph-linked evidence.

**Source Reliability Model:**

Each enrichment provider must include:

```json
{
  "provider": "VirusTotal",
  "source_reliability": 0.95,
  "provider_reputation": "high|medium|low",
  "last_validation": "ISO8601",
  "confidence_weight": 0.95,
  "cache_ttl_seconds": 86400
}
```

This enables:

- trust scoring of derived findings
- evidence filtering by reliability
- forensic review traceability

---

## Investigation Workflows

Generate investigations that:

- correlate related entities
- construct timelines
- identify attack chains
- summarize findings
- explain relationships
- maintain evidence provenance

---

## Graph Relationship Generation

Automatically generate relationships between:

- users
- IPs
- domains
- alerts
- malware
- prompts
- agents
- investigations

---

## AI Reasoning

Use LLM reasoning for:

- summarization
- attack-path explanation
- evidence interpretation
- IOC relationship explanation
- investigation narratives

AI reasoning must always include:

- evidence references
- confidence levels
- supporting entities

---

# Security-for-AI Features

## Prompt Injection Detection

Detect:

- instruction override attempts
- role manipulation
- hidden prompt instructions
- indirect injections
- delimiter abuse
- tool manipulation attempts

---

## Jailbreak Detection

Detect:

- DAN-style jailbreaks
- policy bypass attempts
- roleplay manipulation
- adversarial formatting
- recursive instruction abuse

---

## Risk Scoring

Assign normalized risk scores.

Example:

| Score  | Meaning    |
| ------ | ---------- |
| 0-20   | Safe       |
| 21-50  | Suspicious |
| 51-80  | High Risk  |
| 81-100 | Malicious  |

---

## AI Firewall Middleware

Middleware responsibilities:

- intercept prompts
- analyze requests
- classify attacks
- enforce policies
- sanitize requests
- validate outputs
- log security events

---

## Explainability Requirements

Every firewall decision must include:

- detection category
- matched patterns
- AI reasoning summary
- triggered policies
- confidence score
- final action

---

---

# 2.5. Threat Model

**CRITICAL: This section defines what the platform protects against.**

## Protected Assets

- investigation data and findings
- prompts and LLM inputs
- AI outputs and reasoning
- graph relationships and entities
- evidence and audit logs
- API credentials and secrets
- workflow execution state
- enrichment metadata

## Threat Actors

- **Malicious End Users** — attempt prompt injection, jailbreaks, evidence pollution
- **Attackers** — exploit firewall to bypass security controls
- **Insider Threats** — abusively query graph, modify investigations, exfiltrate evidence
- **Compromised Enrichment Providers** — return poisoned IOC data, false correlations
- **Malicious AI Agents** — generate fake findings, corrupt graph, manipulate reasoning
- **Supply Chain Attackers** — poisoned dependencies, malicious models

## Threat Categories

### AI Security Threats

- Prompt injection attacks
- Jailbreak attempts
- Role manipulation
- Context poisoning
- Hidden instruction injection
- Adversarial prompt crafting
- Output extraction attacks

### Graph Security Threats

- Graph poisoning (false relationships)
- Entity injection (fake IOCs)
- Evidence tampering
- Circular reasoning exploitation
- Relationship manipulation
- Timeline corruption

### Investigation Threats

- Evidence deletion/modification
- Investigation state manipulation
- Confidence score tampering
- Audit trail corruption
- API abuse (DOS, enumeration)
- Unauthorized investigation access

### Operational Threats

- Credential compromise
- API key exfiltration
- Memory corruption
- Context window abuse
- Enrichment provider compromise
- Redis/Neo4j/PostgreSQL breach

## Security Assumptions

**CRITICAL ASSUMPTIONS (verify frequently):**

- External enrichment APIs are **untrusted** until validated
- AI model outputs are **probabilistic** and may be incorrect
- Graph relationships **require validation** before usage
- Incoming prompts **may be malicious**
- Enrichment providers **may be compromised**
- Internal agents **may malfunction**
- User inputs **are not inherently trustworthy**
- Long-running investigations **may accumulate errors**

## Mitigations

| Threat              | Mitigation                                                                    |
| ------------------- | ----------------------------------------------------------------------------- |
| Graph poisoning     | Entity deduplication, schema validation, Evidence Engine linkage              |
| False findings      | Confidence propagation, REVIEW_REQUIRED state, deterministic layer separation |
| Prompt injection    | Firewall middleware, pattern detection, policy enforcement                    |
| Evidence tampering  | Immutable events, audit logs, evidence provenance                             |
| API abuse           | Rate limiting, authentication, RBAC, request validation                       |
| Memory explosion    | Bounded memory, TTL policies, context isolation                               |
| Provider compromise | Multi-source corroboration, reliability scoring, temporal validation          |
| Credential leakage  | Secret rotation, environment isolation, audit logging                         |

---

# 3. Technical Architecture

# High-Level Stack

| Layer                  | Technology             |
| ---------------------- | ---------------------- |
| API Layer              | FastAPI                |
| Language               | Python                 |
| Workflow Orchestration | LangGraph              |
| Graph Database         | Neo4j                  |
| Relational Storage     | PostgreSQL             |
| Cache / Queue          | Redis                  |
| AI Integration         | OpenAI-compatible APIs |
| Containerization       | Docker                 |

---

# Architecture Style

The MVP uses a:

## Modular Monolith

Reasons:

- faster iteration
- simpler deployment
- lower operational overhead
- easier debugging
- reduced infrastructure complexity

Services remain logically separated internally.

---

# Core Components

## 1. API Service

Responsibilities:

- REST APIs
- authentication
- validation
- request routing
- ingestion endpoints

---

## 2. Investigation Engine

Responsibilities:

- IOC extraction
- enrichment orchestration
- investigation generation
- graph correlation

---

## 3. AI Firewall Engine

Responsibilities:

- prompt analysis
- jailbreak detection
- policy enforcement
- output validation

---

## 4. Agent Runtime

Responsibilities:

- agent orchestration
- memory passing
- execution state tracking
- reasoning workflows

Implemented using LangGraph.

---

## 5. Graph Engine

Responsibilities:

- graph persistence
- relationship creation
- traversal queries
- attack path analysis

Backed by Neo4j.

**CRITICAL CONSTRAINT: All graph mutations must pass through a centralized Graph Service layer.**

**No module may directly write arbitrary relationships into Neo4j.**

Reasoning:

- graph quality collapse (unconstrained writes)
- duplicate entity explosion
- meaningless relationships
- audit trail loss

Graph Service enforces:

- schema validation
- entity deduplication
- relationship constraints
- evidence linkage
- timestamp consistency

---

## 6. Evidence Engine

**NEW CORE COMPONENT — One of the highest-value architectural additions.**

Responsibilities:

- unified evidence model
- provenance tracking and tiering
- confidence scoring
- evidence linking
- forensic traceability
- AI grounding

Evidence structure:

```json
{
  "evidence_id": "uuid",
  "source": "VirusTotal|WHOIS|internal|extraction|...",
  "type": "ip|domain|hash|url|log|alert|...",
  "timestamp": "ISO8601",
  "raw_data": {},
  "normalized_data": {},
  "confidence": 0.91,
  "provenance": {
    "level": "PRIMARY_SOURCE|DERIVED_SOURCE|AI_GENERATED|THIRD_PARTY|USER_SUPPLIED",
    "source_reliability": 0.95,
    "extraction_method": "regex|parser|ai_extraction",
    "chain_of_custody": ["event_id_1", "event_id_2"]
  },
  "linked_entities": ["entity_id_1", "entity_id_2"]
}
```

**Provenance Levels (Critical for trust scoring):**

| Level          | Meaning                           | Trust       | Example                                    |
| -------------- | --------------------------------- | ----------- | ------------------------------------------ |
| PRIMARY_SOURCE | direct observation, authoritative | high        | DNS query result, VirusTotal report        |
| DERIVED_SOURCE | calculated from primary           | medium-high | correlation output, enrichment combination |
| AI_GENERATED   | AI reasoning output               | medium      | agent finding, narrative summary           |
| THIRD_PARTY    | external reference                | medium      | blog report, threat feed                   |
| USER_SUPPLIED  | end-user input                    | low-medium  | manual evidence submission                 |

All investigations, enrichments, findings, and AI reasoning must reference evidence IDs, never raw data.

Backed by PostgreSQL `evidence` table + indexed lookups by source, type, confidence, and provenance level.

---

## 8. Entity Resolution Layer

**NEW CORE COMPONENT — Critical for graph quality.**

Responsibilities:

- entity normalization (canonicalization)
- deduplication (same entity detection)
- alias tracking
- entity merging
- parent-child relationships
- variant resolution

**Problem it solves:**

```
google.com
Google.com
https://google.com
https://google.com/login
```

Are these same entity, related, or parent-child?

Entity Resolution enforces:

```json
{
  "canonical_form": "google.com",
  "normalizations": ["google.com", "Google.com", "https://google.com"],
  "entity_id": "uuid",
  "entity_type": "domain",
  "variants": [
    { "form": "https://google.com/login", "relation": "child_url" },
    { "form": "Google.com", "relation": "case_variant" }
  ],
  "confidence": 0.99
}
```

Backed by PostgreSQL `entity_aliases` table.

Graph mutations **must pass through Entity Resolution** before creating nodes.

Responsibilities:

- async jobs
- background execution
- workflow triggers
- event fan-out

Backed by Redis queues.

---

# Async Workflow Model

Use async execution for:

- enrichment jobs
- graph generation
- AI reasoning
- prompt analysis
- correlation tasks

Approach:

- FastAPI background tasks
- asyncio
- Redis-based queues

---

# Memory & Context Handling

## Short-Term Context

Stored in Redis:

- workflow state
- temporary agent memory
- execution context

---

## Long-Term Context

Stored in Neo4j/PostgreSQL:

- investigations
- graph relationships
- prompt history
- AI decisions
- audit logs

---

## Bounded AI Memory

**CRITICAL: Prevent memory explosion, context poisoning, and corruption.**

Memory constraints enforced per agent:

```json
{
  "max_memory_depth": 50,
  "max_tokens_per_memory": 2048,
  "max_total_tokens": 16384,
  "ttl_seconds": 3600,
  "retrieval_relevance_threshold": 0.5,
  "context_isolation": "investigation-scoped",
  "memory_type": "short_term|long_term"
}
```

Memory policies:

- Each agent has **investigation-scoped memory** (isolated per investigation)
- Memory entries **expire after TTL** (default 1 hour)
- Irrelevant memories **below threshold are purged**
- Memory **depth is capped** (FIFO eviction)
- Memory retrieval uses **relevance scoring**
- **Audit log** all memory access

This prevents:

- exploding context windows
- context poisoning attacks
- hallucination from stale context
- cross-investigation contamination

---

# AI Agent Orchestration

LangGraph manages:

- execution flows
- branching decisions
- retries
- agent communication
- reasoning pipelines

---

# 3.5. Operational Constraints

**CRITICAL: Prevent runaway workflows, graph explosions, and AI cost spirals.**

Enforce hard limits on all long-running operations:

```json
{
  "investigation": {
    "max_duration_seconds": 3600,
    "max_events_per_investigation": 10000,
    "max_evidence_items": 5000,
    "max_graph_depth": 10,
    "max_node_count": 50000
  },
  "agents": {
    "max_concurrent_executions": 10,
    "max_execution_time_seconds": 300,
    "max_memory_per_agent_mb": 256,
    "max_retries": 3
  },
  "enrichment": {
    "max_enrichment_retries": 3,
    "max_enrichment_time_seconds": 30,
    "max_enrichment_queue_depth": 1000,
    "rate_limit_per_second": 100
  },
  "ai": {
    "max_tokens_per_request": 4096,
    "max_tokens_per_investigation": 50000,
    "max_concurrent_ai_calls": 5,
    "timeout_seconds": 60
  },
  "api": {
    "rate_limit_requests_per_minute": 1000,
    "max_payload_size_mb": 100,
    "max_query_complexity": 100
  },
  "graph": {
    "max_traversal_depth": 8,
    "max_relationship_count_per_node": 1000,
    "query_timeout_seconds": 30
  }
}
```

Violations trigger:

- automatic termination with error
- event logging
- investigation state set to `FAILED`
- alert to monitoring system

---

---

# 4. Repository Structure

```text
platform/
│
├── apps/
│   ├── api/
│   ├── worker/
│   ├── scheduler/
│   └── cli/
│
├── core/
│   ├── config/
│   ├── logging/
│   ├── security/
│   ├── observability/
│   └── database/
│
├── agents/
│   ├── ioc_correlation/
│   ├── enrichment/
│   ├── reasoning/
│   └── firewall_analysis/
│
├── orchestration/
│   ├── graphs/
│   ├── workflows/
│   ├── memory/
│   └── runtime/
│
├── firewall/
│   ├── detectors/
│   ├── policies/
│   ├── scoring/
│   ├── sanitizers/
│   └── validators/
│
├── investigation/
│   ├── ingestion/
│   ├── extraction/
│   ├── enrichment/
│   ├── correlation/
│   └── timelines/
│
├── graph/
│   ├── neo4j/
│   ├── models/
│   ├── queries/
│   ├── traversal/
│   ├── schema_governance/
│   └── graph_service/
│
├── evidence/
│   ├── models/
│   ├── provenance/
│   ├── storage/
│   └── validation/
│
├── resolution/
│   ├── normalization/
│   ├── deduplication/
│   ├── entity_merge/
│   └── alias_tracking/
│
├── schemas/
│   ├── api/
│   ├── events/
│   ├── graph/
│   └── database/
│
├── storage/
│   ├── postgres/
│   ├── redis/
│   └── files/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── agents/
│   ├── firewall/
│   └── graph/
│
├── infra/
│   ├── docker/
│   ├── compose/
│   └── scripts/
│
├── docs/
│
├── pyproject.toml
├── docker-compose.yml
└── README.md
```

---

# 5. Database Design

# PostgreSQL Design

## investigations

```sql
id
title
status
severity
created_at
updated_at
summary
confidence_score
```

---

## investigation_events

```sql
id
investigation_id
event_type
event_data
timestamp
```

---

## evidence

```sql
id (uuid)
source (VirusTotal|WHOIS|internal|extraction|...)
type (ip|domain|hash|url|log|alert|...)
timestamp (ISO8601)
raw_data (jsonb)
normalized_data (jsonb)
confidence (float 0.0-1.0)
provenance (jsonb: source_reliability, extraction_method)
linked_entities (uuid[])
created_at
indexed: source, type, confidence
```

---

## firewall_events

```sql
id
request_id
risk_score
classification
action_taken
prompt_hash
response_hash
created_at
```

---

## audit_logs

```sql
id
actor
action
resource
metadata
timestamp
```

---

# Neo4j Graph Design

# Node Types

```text
User
IP
Domain
URL
Hash
Email
Alert
Investigation
Prompt
Model
Agent
Workflow
Finding
```

---

# Relationship Types

```text
CONNECTED_TO
RESOLVES_TO
TRIGGERED
RELATED_TO
GENERATED
ANALYZED_BY
PART_OF
COMMUNICATED_WITH
ATTEMPTED
BLOCKED
```

---

# Event Storage

Events are immutable.

All workflows emit events.

Events become:

- graph edges
- audit records
- reasoning references

---

---

# 6. Investigation Graph Design

## Investigation Lifecycle States

**CRITICAL: Investigations must transition through explicit states.**

```
CREATED           → initial ingestion
  ↓
ENRICHING        → enrichment pipelines active
  ↓
CORRELATING      → IOC correlation in progress
  ↓
ANALYZING        → AI reasoning phase
  ↓
REVIEW_REQUIRED  → human review needed
  ↓
COMPLETED        → investigation finalized
  ↓
ARCHIVED         → long-term storage

FAILED           → error state (can occur from any state)
```

Each state transition must emit an event and update PostgreSQL `investigations.status`.

---

## Confidence Propagation Logic

**CRITICAL for explainability: Derived relationships inherit weighted confidence.**

Confidence is never 100%. Each relationship compounds uncertainty.

Confidence propagation formula:

```
derived_confidence = min(
  source_reliability,
  enrichment_reliability,
  ai_confidence,
  corroborating_evidence_count_factor
)
```

Example:

- IP extracted via regex: confidence 0.95
- Enriched via VirusTotal (99% reliable): 0.95 × 0.99 = 0.94
- Cross-corroborated by 3 other evidence sources: 0.94 × 1.0 = 0.94
- AI reasoning confidence in connection: 0.85
- **Final relationship confidence: 0.85**

Every graph relationship stores `confidence` property.

Findings are sorted/prioritized by confidence.

Low-confidence findings trigger `REVIEW_REQUIRED` state.

---

## Deterministic vs. AI-Assisted Reasoning

**CRITICAL: Do NOT let AI reasoning dominate investigations. Hallucinations corrupt evidence.**

Separate concerns explicitly:

### Deterministic Layer

Always trustworthy, reproducible, auditable:

- IOC extraction (regex, parsers)
- graph relationship creation (via schema governance)
- enrichment data normalization
- rules-based classification
- event logging
- timeline generation
- entity resolution

### AI Layer

Assistive, must be grounded in evidence:

- summarization (of deterministic findings)
- relationship interpretation (explaining why entities connect)
- prioritization (ranking findings by significance)
- narrative generation (attack chain storytelling)
- explainability (why was this classified as high risk)

All AI outputs:

- must cite evidence (with evidence_id)
- must include confidence and provenance level
- must be reviewable
- are stored separately from deterministic findings
- tracked in provenance chain

---

## Graph Schema Governance

**CRITICAL: Define allowed relationships to prevent semantic drift.**

Enforce via **Relationship Matrix** in Graph Service:

```
Allowed relationship patterns:

IP
  ├── RESOLVES_TO → DOMAIN
  ├── CONNECTS_FROM → IP (peer)
  └── RELATED_TO → ALERT

DOMAIN
  ├── OWNED_BY → USER
  ├── RESOLVES_FROM → IP
  └── RELATED_TO → MALWARE

PROMPT
  ├── SUBMITTED_BY → USER
  ├── TRIGGERED → FIREWALL_EVENT
  ├── ANALYZED_BY → AGENT
  └── PART_OF → INVESTIGATION

FINDING
  ├── GENERATED_BY → AGENT
  ├── REFERENCES → EVIDENCE
  ├── RELATED_TO → FINDING
  └── PART_OF → INVESTIGATION
```

Violating relationships are **rejected at Graph Service layer** with detailed error.

This prevents:

- nonsensical relationships
- semantic corruption
- graph quality degradation

---

# Objectives

The graph acts as:

- investigation memory
- evidence graph
- AI reasoning substrate
- explainability engine

---

# Node Design

Each node includes:

```json
{
  "id": "uuid",
  "type": "IP",
  "value": "1.1.1.1",
  "confidence": 0.91,
  "source": "VirusTotal",
  "created_at": "timestamp"
}
```

---

# Temporal Modeling

Relationships include:

- timestamps
- sequence ordering
- event context

Example:

```text
User -> Prompt -> Firewall -> Agent -> Investigation
```

---

# Agent Decision Tracking

Every AI decision creates:

- reasoning node
- confidence score
- linked evidence (via Evidence Engine)
- execution metadata
- audit log entry

All reasoning is stored separately from deterministic findings.

---

# Attack Path Modeling

The graph supports:

- traversal analysis
- relationship chaining
- investigation replay
- evidence lineage

---

---

# 7. AI Agent System

# IOC Correlation Agent

## Responsibilities

- correlate entities
- identify relationships
- generate findings

## Inputs

- extracted IOCs
- enrichment results
- graph context

## Outputs

- investigation graph updates
- findings
- correlation summaries

---

# Enrichment Agent

## Responsibilities

- external intelligence lookup
- metadata normalization
- confidence scoring

---

# Reasoning Agent

## Responsibilities

- summarize investigations
- explain relationships
- generate attack narratives

---

# Firewall Analysis Agent

## Responsibilities

- analyze prompts
- classify attacks
- generate risk scores
- explain decisions

---

# Agent Memory Model

## Short-Term

Redis-backed execution memory.

---

## Long-Term

Neo4j-backed investigation context.

---

# Orchestration Flow

```text
Ingestion
    ↓
Extraction
    ↓
Enrichment
    ↓
Correlation
    ↓
Graph Update
    ↓
Reasoning
    ↓
Investigation Output
```

---

# 8. AI Firewall Design

# Middleware Flow

```text
Client
   ↓
AI Firewall
   ↓
Prompt Analysis
   ↓
Risk Scoring
   ↓
Policy Engine
   ↓
Allow / Block / Sanitize
   ↓
LLM Provider
```

---

# Prompt Analysis Pipeline

Stages:

1. normalization
2. pattern detection
3. heuristic analysis
4. LLM-assisted classification
5. risk scoring
6. policy evaluation

---

# Classification Categories

```text
PROMPT_INJECTION
JAILBREAK
ROLE_MANIPULATION
DATA_EXTRACTION
TOOL_ABUSE
CONTEXT_POISONING
```

---

# Output Validation

Analyze responses for:

- sensitive data leakage
- unsafe instructions
- policy violations
- hidden prompts

---

# Audit Logging

All decisions must store:

- request metadata
- classifications
- risk scores
- triggered policies
- sanitized output
- timestamps

---

---

# 9. API Design

# Investigation APIs

```http
POST /api/v1/investigations
GET /api/v1/investigations/{id}
GET /api/v1/investigations/{id}/timeline
```

---

# IOC APIs

```http
POST /api/v1/iocs/ingest
POST /api/v1/iocs/extract
GET /api/v1/iocs/{id}
```

---

# Graph APIs

```http
GET /api/v1/graph/nodes/{id}
POST /api/v1/graph/query
GET /api/v1/graph/investigation/{id}
```

---

# Firewall APIs

```http
POST /api/v1/firewall/analyze
POST /api/v1/firewall/decision
POST /api/v1/firewall/validate-output
```

---

# Agent APIs

```http
POST /api/v1/agents/run
GET /api/v1/agents/status/{id}
```

---

# 10. Event & Workflow Architecture

# Event-Driven Model

Core events:

```text
IOC_INGESTED
IOC_ENRICHED
GRAPH_UPDATED
INVESTIGATION_CREATED
PROMPT_ANALYZED
FIREWALL_BLOCKED
AGENT_COMPLETED
```

---

# Queue Strategy

Redis queues handle:

- enrichment jobs
- graph updates
- AI reasoning
- firewall analysis

---

# Workflow Execution

LangGraph orchestrates:

- sequential execution
- branching
- retries
- failure recovery

---

# Background Tasks

Use for:

- enrichment
- graph indexing
- AI inference
- audit logging

---

# 10.5. Failure Handling Strategy

**CRITICAL: Failures are inevitable. Handle them explicitly.**

## Retry Policy

```json
{
  "enrichment_jobs": {
    "max_retries": 3,
    "backoff_strategy": "exponential",
    "backoff_base_seconds": 2,
    "max_backoff_seconds": 60
  },
  "graph_operations": {
    "max_retries": 2,
    "backoff_strategy": "linear",
    "backoff_interval_seconds": 1
  },
  "ai_requests": {
    "max_retries": 2,
    "backoff_strategy": "exponential",
    "backoff_base_seconds": 1
  }
}
```

## Dead-Letter Queues

Failed operations after max retries are moved to DLQ:

- `enrichment_dlq` — enrichment jobs that failed permanently
- `graph_dlq` — graph mutations that failed permanently
- `reasoning_dlq` — AI reasoning tasks that failed
- `workflow_dlq` — orchestration failures

DLQ entries are:

- logged with full context
- flagged for manual review
- never auto-retried
- retained for 30 days minimum

## Partial Investigation Recovery

If enrichment or reasoning fails mid-investigation:

- mark investigation as `REVIEW_REQUIRED`
- set confidence lower on partial findings
- emit `INVESTIGATION_DEGRADED` event
- log failure reason with evidence references
- allow user to manually retry specific enrichments

## Graph Rollback Strategy

If graph mutation fails:

- **no automatic rollback** (graph is append-only)
- emit `GRAPH_MUTATION_FAILED` event
- log failed mutation with reason
- investigation remains in same state
- user may retry via API

If graph becomes corrupted:

- manual intervention required
- reconstruct from event log
- validation via deterministic layer replay

## Enrichment Timeout Handling

If enrichment API times out:

1. immediate failure (no retry if timeout > threshold)
2. mark evidence as `TIMEOUT` state
3. log provider as `DEGRADED` temporarily
4. continue investigation without that enrichment
5. trigger alert if provider recovers

## AI Provider Failure Fallback

If AI provider is unavailable:

1. immediately fail reasoning task (don't queue)
2. continue investigation with deterministic findings only
3. mark investigation as `AI_UNAVAILABLE`
4. log reason and timestamp
5. user may retry reasoning later
6. **do not degrade to local LLM without explicit user request**

## Circuit Breakers

For external services (enrichment APIs, AI providers):

```
HEALTHY: normal operation
  -> (after 5 consecutive failures)
OPEN: reject requests immediately, fail fast
  -> (after 30 seconds)
HALF_OPEN: allow 1 test request
  -> (if successful)
HEALTHY
  -> (if fails)
OPEN
```

Circuit breaker state affects:

- investigation progress (degrades gracefully)
- alerts to operations team
- fallback strategy selection

---

---

# 11. Development Phases

# Phase 1 — Foundation

## Objectives

- repository setup
- Docker environment
- FastAPI skeleton
- PostgreSQL integration
- Neo4j integration
- Redis setup

## Deliverables

- local dev environment
- API scaffold
- database connectivity

## Risks

- infra misconfiguration

## Complexity

Low

---

# Phase 2 — IOC Engine

## Objectives

- IOC ingestion
- extraction pipeline
- enrichment system

## Deliverables

- IOC APIs
- extraction services
- enrichment jobs

## Risks

- inconsistent enrichment data

## Complexity

Medium

---

# Phase 3 — Investigation Graph

## Objectives

- graph persistence
- relationship generation
- traversal APIs

## Deliverables

- Neo4j graph layer
- graph APIs
- timeline generation

## Risks

- graph schema instability

## Complexity

High

---

# Phase 4 — AI Firewall

## Objectives

- middleware interception
- prompt analysis
- jailbreak detection
- risk scoring

## Deliverables

- firewall APIs
- policy engine
- explainability pipeline

## Risks

- false positives

## Complexity

High

---

# Phase 5 — Orchestration Layer

## Objectives

- LangGraph workflows
- multi-agent coordination
- execution tracing

## Deliverables

- orchestration runtime
- workflow engine

## Risks

- state management complexity

## Complexity

High

---

# Phase 6 — Production Hardening

## Objectives

- observability
- testing
- security
- performance tuning

## Deliverables

- monitoring
- tracing
- CI/CD
- hardened configs

## Risks

- operational overhead

## Complexity

Medium

---

# 11.5. Schema Versioning Strategy

**CRITICAL: Migrations and replays become impossible without versioning.**

Version all structural schemas and APIs with schema_version, event_version, graph_model_version, api_version.

- **Breaking changes**: increment major version, requires migration
- **Additive changes**: increment minor version, backward compatible
- **Bug fixes**: increment patch version

Maintain migration scripts, replay events through versioned pipeline, store old schemas for forensic replay, never delete schema documentation.

Store `schema_version` at investigation creation. Old investigations remain queryable with original schema. Migration is **opt-in, never automatic**.

---

# 11.6. Idempotency Guarantees

**CRITICAL: Retries must not create duplicates in event-driven systems.**

Idempotency applies to: events, enrichment jobs, graph mutations, API requests

## Event Deduplication

- events include `idempotency_key` (UUID)
- duplicate detection on `(event_id, idempotency_key)` pair
- failed retry returns cached result

## Enrichment Deduplication

- enrichment job includes `(ioc_id, provider, timestamp)` fingerprint
- duplicate enrichments rejected during processing
- result cached and reused within TTL window

## Graph Mutation Idempotency

- graph operations include fingerprint: `(node_id, relationship_type, target_id)`
- upsert logic: if relationship exists with same fingerprint, skip
- **no duplicates** added on retry

## Replay Protection

- investigation replay includes `replay_id`
- events marked `is_replay = true` do not trigger downstream jobs
- replay only reconstructs state, no side effects

---

# 11.7. Authorization Boundaries

**CRITICAL: Operationalize RBAC explicitly.**

**Roles:** admin, analyst, readonly, external_user, ai_agent, service_account

**Resource-Level Access Control:**

- **GRAPH**: admin (read/write all), analyst (read all, write investigations), external_user (read assigned only)
- **EVIDENCE**: admin (read/write/delete all), analyst (read all, write own), external_user (read assigned only)
- **PROMPTS**: admin (read all), analyst (read own investigations), others (no access)
- **MUTATIONS**: admin (any), analyst (create investigations), ai_agent (emit/update graph), service_account (add evidence)
- **EXPORT**: admin (any format), analyst (CSV/PDF investigation scope), readonly (PDF summary only)

## Implementation

- all API endpoints check `(user_role, resource_id, action)` tuple
- evidence access filtered by investigation authorization
- audit log all permission denials
- fail-safe: deny by default if authorization check fails

---

# 11.8. Investigation Integrity Verification

**NEW DIFFERENTIATOR: Automatically validate investigation coherence.**

Run integrity checks on investigations in `REVIEW_REQUIRED` or `COMPLETED` state:

- **Orphan Relationship Detection**: find relationships where source or target node was deleted, flag as `INTEGRITY_WARNING_ORPHAN_RELATIONSHIP`

- **Confidence Inconsistency**: find relationships where confidence > min(source_confidence, target_confidence), flag as `INTEGRITY_WARNING_CONFIDENCE_VIOLATION`

- **Circular Reasoning**: detect evidence → AI_GENERATED → evidence loops, flag as `INTEGRITY_WARNING_CIRCULAR_REASONING`

- **Evidence Chain Validation**: verify provenance chain completeness, check chain_of_custody references exist, validate timestamp ordering

- **Missing Provenance**: find evidence without provenance level, findings without evidence references, relationships without confidence

- **Stale Enrichment**: find enrichments older than configured age, mark as `ENRICHMENT_STALE`, flag dependent findings

Generate integrity report with violations, severity levels, and remediation recommendations.

---

# 12. Testing Strategy

# Unit Testing

Test:

- extraction logic
- scoring logic
- graph builders
- middleware policies

---

# Integration Testing

Test:

- API workflows
- database interactions
- orchestration flows

---

# Agent Testing

Validate:

- reasoning quality
- workflow consistency
- execution reliability

---

# Prompt Attack Testing

Maintain adversarial datasets for:

- jailbreaks
- injections
- role manipulation

---

# Security Testing

Include:

- fuzzing
- auth testing
- API abuse testing
- rate limit testing

---

# 13. Observability & Monitoring

# Logging

Structured JSON logs.

Include:

- correlation IDs
- workflow IDs
- investigation IDs

---

# Metrics

Track:

- request latency
- agent execution time
- enrichment success rate
- firewall detection rate

---

# Tracing

Implement distributed tracing for:

- workflows
- agent execution
- AI calls

---

# AI Decision Traceability

Every AI action should include:

- prompt
- response
- confidence
- evidence references
- execution metadata

---

# 14. Security Considerations

# API Security

- JWT authentication
- RBAC
- input validation
- schema enforcement

---

# Secret Management

Use:

- environment variables
- Docker secrets
- secret rotation

---

# AI Abuse Prevention

Implement:

- prompt limits
- token limits
- abuse rate detection

---

# Sandboxing

Isolate:

- untrusted processing
- file analysis
- enrichment pipelines

---

# Validation Pipelines

Validate:

- incoming payloads
- graph mutations
- AI outputs

---

# 14.5. Data Retention & Privacy

**CRITICAL: Prompts, logs, investigations, and evidence may contain sensitive information.**

This matters if you:

- open-source the platform
- demo publicly
- onboard external users
- operate in regulated industries

## Evidence Retention Policy

```json
{
  "evidence": {
    "default_retention_days": 90,
    "max_retention_days": 365,
    "archive_after_days": 30,
    "secure_delete_after_expiry": true
  },
  "by_provenance_level": {
    "PRIMARY_SOURCE": 180,
    "DERIVED_SOURCE": 90,
    "AI_GENERATED": 30,
    "THIRD_PARTY": 60,
    "USER_SUPPLIED": 30
  }
}
```

## Prompt Retention Limits

- Raw prompts: retain **max 30 days**
- Prompt hashes: retain indefinitely (for deduplication)
- Classified prompts (injection/jailbreak): retain **max 90 days**
- **Do not log full prompt content in stdout/debug**
- Hash all prompts for logging

## Audit Log Retention

```json
{
  "audit_logs": {
    "retention_days": 365,
    "immutable": true,
    "never_delete": [
      "authentication_events",
      "authorization_decisions",
      "data_access_events"
    ]
  }
}
```

## Investigation Archival

After investigation is `COMPLETED` or `ARCHIVED`:

- compress investigation data
- move to cold storage (PostgreSQL archive partition)
- retain Neo4j relationships (query-only, no mutations)
- evidence still accessible via API but marked as archived
- archival timestamp recorded

## PII Masking

Automatically detect and mask:

- email addresses: `user***@domain.com`
- IP addresses: `192.168.***.*`
- phone numbers: `+1-***-***-1234`
- credit card numbers: `****-****-****-1234`
- API keys: `sk_***...***`
- passwords: `[REDACTED]`

Masking applied to:

- logs (application logs, audit logs)
- evidence display (API responses)
- investigation summaries
- **NOT** to stored data (raw data remains for forensic investigation)

Masking configuration per user role:

- admin: see full data
- analyst: see masked data
- third-party: see heavily masked data

## GDPR Considerations

**If operating in EU or processing EU citizen data:**

- **Right to be forgotten**: API endpoint to purge investigation + all related data
- **Data portability**: export investigation in standard format
- **Transparency**: log all data access by actor/purpose
- **Consent**: track if prompts contain user consent
- **Data processing agreement**: maintain with enrichment providers

Implementation:

```json
{
  "user": {
    "id": "uuid",
    "gdpr_region": "EU|US|APAC",
    "data_processing_consent": true,
    "data_retention_override_days": null
  },
  "investigation": {
    "gdpr_applicable": true,
    "owner_jurisdiction": "DE",
    "contains_pii": true,
    "pii_types": ["email", "ip_address"]
  }
}
```

## Secure Deletion Strategy

When data reaches retention limit:

1. query all affected records (PostgreSQL + Neo4j)
2. emit `DATA_DELETION_REQUESTED` event
3. **overwrite data 3 times** (Gutmann method)
4. delete rows/nodes
5. emit `DATA_DELETION_COMPLETED` event
6. log deletion with timestamp + count
7. verify deletion via audit query

For sensitive data (prompts with injections, API keys):

- immediate deletion if flagged as sensitive
- **no retention period override**

## Compliance Checklist

- [ ] PII detection rules configured
- [ ] Masking rules applied to all output layers
- [ ] Retention policies enforced via scheduled jobs
- [ ] Secure deletion verified
- [ ] GDPR right-to-be-forgotten implemented
- [ ] Data access audit trail maintained
- [ ] Third-party enrichment providers have DPA
- [ ] User consent tracking implemented

---

# 15. Future Expansion Paths

# Multi-Agent Systems

Add:

- collaborative agents
- specialized reasoning agents
- autonomous workflows

---

# Autonomous Investigations

Support:

- automated triage
- investigation replay
- remediation recommendations

---

# Streaming Telemetry

Add:

- Kafka
- real-time event ingestion
- continuous graph updates

---

# SIEM Integrations

Future integrations:

- Splunk
- Elastic
- Microsoft Sentinel

---

# Local LLM Support

Add:

- Ollama
- vLLM
- GPU inference

---

# Cloud-Native Scaling

Future migration path:

- Kubernetes
- event streaming
- distributed workers
- multi-tenant architecture

---

# Final Notes

## ⚠️ CRITICAL: Stop Architecting, Start Building

**This plan is now COMPLETE. Implementation should BEGIN IMMEDIATELY.**

The architecture now includes:

✓ Event canonicalization & versioning
✓ Graph quality constraints & governance  
✓ Evidence provenance & tiering
✓ Entity resolution & deduplication
✓ AI/deterministic separation
✓ Threat surface & security model
✓ Operational bounds & constraints
✓ Failure handling & recovery
✓ Privacy & retention policies
✓ Authorization & RBAC
✓ Idempotency guarantees
✓ Integrity verification

**This is already more sophisticated than many shipping security platforms.**

### The Danger Zone

Architecture documents expand indefinitely if you let them:

- "what about X?"
- "we should also handle Y?"
- "let's define Z for completeness"

**This is how platforms die in planning.**

### The Real Learning Happens During Implementation

Phase 1 will teach you more than additional architecture refinement:

1. **Schema design** — FastAPI + PostgreSQL will reveal what actually matters
2. **Graph integration** — Neo4j will show you which relationships work
3. **Agent execution** — Real failure modes emerge, not theoretical ones
4. **Enrichment** — Rate limiting + retry behavior becomes concrete
5. **Investigation workflows** — Actual UX needs become clear

Questions that architecture cannot answer:

- Is evidence structure too deep or too shallow?
- Which relationship types are actually queried?
- How do retries behave in real Redis queues?
- What does graph performance look like at 50K nodes?
- Where are the real bottlenecks?

### The MVP should prioritize:

- execution speed
- modularity
- explainability
- maintainability
- observability

### Avoid:

- premature microservices
- excessive abstraction
- over-engineering
- **more architecture documents**

### The immediate goal is to build:

A stable, explainable, graph-centric backend platform capable of:

- AI-assisted cyber investigations
- AI runtime security enforcement
- graph-based reasoning
- composable orchestration

**Lock this plan. Move to Phase 1 bootstrap now. Stop planning.**
