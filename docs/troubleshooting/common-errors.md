# Common errors

## `401 missing bearer token`

The route requires a JWT. Mint one via `/tokens/issue` (see
`docs/deployment/local.md`).

## `401 invalid bearer token`

The token failed structural validation. Check the structured log line
`auth.denied reason=...` — values: `missing|malformed|invalid_signature|
expired|wrong_issuer|wrong_audience|unknown_kid|missing_claim`. The
`auth_denials_total{reason}` counter tracks the same set.

## `403 permission_denied`

The token is valid but the principal's role lacks the required
permission. Cross-reference the role against
`core/security/rbac.py:ROLE_MATRIX`. Audit row in
`investigation_events` (event_type `AUTH_PERMISSION_DENIED`) names the
exact `(role, permission, route)` tuple.

## `413 request body exceeds N bytes`

`MaxBodyMiddleware` rejected the request. Increase
`SECURITY_MAX_BODY_BYTES` or split the payload.

## `429 rate limit exceeded`

`slowapi` rejected the call. The default is 120/min per JWT subject —
tune via `SECURITY_RATE_LIMIT_DEFAULT`. Inspect `Retry-After` header
for the cooldown.

## `503 not_ready` from `/ready`

A downstream is unhealthy. Hit the same endpoint with `-v` to see which
component reports false; cross-reference with `docker compose ps`.

## "graph queries are slow"

Check `db.slow_query` log lines (threshold:
`OBSERVABILITY_SLOW_QUERY_THRESHOLD_MS`, default 500ms). The template
+ params fingerprint identifies the query without leaking values.
Then `EXPLAIN ANALYZE` against `infra/scripts/pg_explain_baseline.sql`
to compare the live plan with the baseline.
