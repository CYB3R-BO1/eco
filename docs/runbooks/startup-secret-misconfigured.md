# Startup failure: dev-default secret in production

## Symptom

The API process exits immediately on boot with:

```
ValueError: production deploy is using the dev-default JWT signing key.
Set SECURITY_JWT_KEYS to a JSON array of {kid, secret} objects from
your secret manager before booting.
```

Or:

```
ValueError: production deploy has empty SECURITY_BOOTSTRAP_ADMIN_SECRET.
Set it to a long random string so /tokens/issue can be authenticated
by the operator who is bootstrapping the system.
```

## Cause

The Phase 7 WP1 startup guardrail (`Settings._enforce_production_secret_guardrail`)
refuses to let the process serve traffic when:

1. `ENVIRONMENT=production` AND
2. The active JWT signing key is the literal `change-me-dev-only`
   sentinel (i.e. `SECURITY_JWT_KEYS` was never set), OR
3. `SECURITY_BOOTSTRAP_ADMIN_SECRET` is empty.

Either condition means a deploy slipped through without secrets,
which would otherwise let anyone with read access to the source forge
tokens.

## Fix

1. Generate a strong JWT signing secret:

   ```bash
   openssl rand -base64 48
   ```

2. Put it in your secret manager (Vault, AWS Secrets Manager, SOPS,
   sealed-secrets, etc.) — never in the container image.

3. Inject as env at boot time:

   ```
   SECURITY_JWT_KEYS=[{"kid":"prod-2026q2","secret":"<the random string>"}]
   SECURITY_BOOTSTRAP_ADMIN_SECRET=<another random string>
   ```

   The JWT keys env is JSON. Multiple entries → first is active for
   signing, the rest validate-only for in-flight tokens during rotation.

4. Restart the container. Verify boot success via `/health`.

## Why the process won't start instead of warning

Logging a warning means production runs with a forged-token-on-demand
vulnerability — silent failures of security controls are the most
expensive class of bug. Failing fast catches this before serving the
first request.

## Related

- [Key rotation](key-rotation.md)
- [Production deployment baseline](../deployment/prod-baseline.md)
