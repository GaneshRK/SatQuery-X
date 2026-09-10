# Stage 20 — Production Release & Scientific Acceptance

Stage 20 is the release gate for SatQuery-X. A release is accepted only when software, security, operations and scientific evidence requirements all pass.

## Release gates

1. `python -m compileall -q .` passes.
2. `python manage.py check --deploy` passes under production settings with real deployment environment variables.
3. Database migrations are present and `python manage.py migrate --check` reports no pending migration changes.
4. Full pytest suite passes in the project's supported Python environment.
5. `/api/v1/health/` reports the real dependency state.
6. `/api/v1/health/readiness/` is READY only when the primary database is reachable.
7. Provider outages remain structured failures.
8. No synthetic fixture is accepted as scientific satellite evidence.
9. Production secrets are supplied only through environment/secret management.
10. Rollback and backup procedures are documented and tested.

## Scientific acceptance

Every acceptance scenario must retain source, acquisition time, sensor/modality, spatial metadata, model/evidence references and provenance. Missing evidence must produce a failure or uncertainty state rather than a fabricated answer.

## Maintenance

- Keep dependencies pinned/regularly reviewed in deployment builds.
- Apply Django/security updates through a controlled release process.
- Run database backups according to the deployment SLA and perform restore tests.
- Monitor health, task failures, provider latency and storage capacity.
- Review logs for repeated provider/authentication/network failures.
- Never delete provenance records merely to clear operational storage.

## Deployment

Use the supplied Dockerfile and Compose example as a reference deployment. Production credentials, domain names, API keys and database passwords must never be committed.
