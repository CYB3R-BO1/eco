# JWT signing-key rotation

Phase 6 ships HS256 self-issued JWTs with a `kid` header that selects
one of N keys in `SecuritySettings.jwt_keys`. Rotation is non-disruptive:

1. Generate a new strong secret (32+ random bytes, e.g.
   `openssl rand -base64 48`).
2. Call `POST /api/v1/tokens/rotate-key` with the new `kid` + secret
   and the `X-Admin-Bootstrap-Secret` header set to
   `SECURITY_BOOTSTRAP_ADMIN_SECRET`. This **prepends** the new key —
   it becomes active immediately; old keys remain valid until their
   in-flight tokens expire.
3. Persist the new keyset in your secret store. The in-process rotation
   above is intentionally ephemeral so a restart with stale
   `SECURITY_JWT_KEYS` reverts the rotation — production deployments
   should source the env from a secret manager.
4. After `jwt_default_ttl_seconds` has elapsed (default 1h), prune the
   old kid from `SECURITY_JWT_KEYS` and restart.

Verify with `GET /api/v1/tokens/whoami` using a fresh token — the
response should show the new `token_kid`.
