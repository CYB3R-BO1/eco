"""AI Firewall — Phase 4.

Model-agnostic prompt-security middleware. Sits between callers and any
LLM provider; runs a six-layer analysis pipeline (normalize → heuristics
→ patterns → rules → LLM-assisted stub → scoring), applies a deterministic
policy, optionally sanitizes the prompt, and emits an immutable audit
trail + a graph correlation. Nothing in this package writes Neo4j directly
— all mutations route through :mod:`graph.graph_service` (CLAUDE.md
invariant #2). Nothing in this package logs raw prompt or response text
— only SHA-256 fingerprints (CLAUDE.md invariant #12).
"""
