# SatQuery-X Operations Runbook

## Service is DOWN

1. Check `/api/v1/health/liveness/`.
2. Check `/api/v1/health/readiness/`.
3. Inspect application and Celery logs.
4. Verify database and Redis availability.
5. Roll back the latest deployment if the failure began immediately after release.

## Provider is unavailable

1. Confirm the Copernicus health status.
2. Verify credentials and token configuration without printing secrets.
3. Check network/DNS/HTTP errors.
4. Do not enable a synthetic fallback.
5. Retry only through the existing provider boundary.

## Storage pressure

1. Inspect the media volume.
2. Identify temporary/cache artifacts.
3. Preserve imagery required for provenance and reproducibility.
4. Remove only artifacts covered by the retention policy.
5. Re-run readiness/health checks.

## Release rollback

1. Stop traffic to the new version.
2. Deploy the previous known-good image.
3. Restore database only when a backward-incompatible migration requires it.
4. Verify liveness, readiness and a golden scientific scenario.
5. Record the incident and root cause.
