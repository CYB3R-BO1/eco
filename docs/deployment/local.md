# Local deployment

```bash
cp .env.example .env    # if it exists; otherwise see core/config/settings.py
make up                  # docker compose up -d --build
make migrate             # alembic upgrade head
```

Smoke test:

```bash
curl http://localhost:8000/health
curl http://127.0.0.1:9090/metrics | head
```

Issue your first token (uses the `SECURITY_BOOTSTRAP_ADMIN_SECRET` from
`.env`):

```bash
curl -X POST http://localhost:8000/api/v1/tokens/issue \
  -H "Content-Type: application/json" \
  -H "X-Admin-Bootstrap-Secret: $SECURITY_BOOTSTRAP_ADMIN_SECRET" \
  -d '{"subject": "dev", "role": "admin"}'
```

## Tear down

```bash
make down       # leave volumes intact
make clean      # nuke volumes too
```
