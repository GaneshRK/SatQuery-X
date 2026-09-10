# Stage 19 — Production Reliability & Observability

Stage 19 hardens SatQuery-X for repeatable service operation without changing the scientific evidence rules introduced in Stages 17–18.

## Reliability controls

- Explicit production environment validation.
- Django liveness and readiness probes.
- Detailed health checks for database, Redis, Celery, Copernicus, AI providers and storage.
- Structured logging remains safe: health responses do not expose secrets or connection strings.
- Celery is configured from environment variables and keeps JSON-only task serialization.
- Provider failures remain structured and are never silently replaced with synthetic imagery.
- Deployment checks are fail-fast for insecure production settings.

## Operational rule

A degraded external provider must be visible to operators. It must never be converted into a successful scientific result.

## Maintenance cadence

Daily: health/readiness checks and error-log review.

Weekly: dependency review, storage review, failed-task review, and backup restore spot-check.

Before every release: production configuration check, migrations check, compile check, and full pytest suite in an environment containing the project dependencies.
