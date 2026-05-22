# Load testing

```bash
make load-test          # 10 users, 60s, against compose stack

# Or directly:
BOOTSTRAP_SECRET=$SECURITY_BOOTSTRAP_ADMIN_SECRET \
  locust -f tests/load/locustfile.py --headless -u 50 -r 5 -t 5m \
  --host http://localhost:8000
```

Scenarios:

| User class               | Goal                                                  |
|--------------------------|-------------------------------------------------------|
| `IOCIngestBurst`         | Sustained ~1000 IOCs / 60s                            |
| `GraphTraversalSteady`   | 50 RPS reads against `GET /graph/node/{id}`           |
| `InvestigationLifecycle` | 5 RPS end-to-end ingest → enrich → summarize          |

Locust mixes the three classes by default — to isolate one, run with
`--class-picker` or pass the class name via `-T <class>` (Locust v2.20+).
