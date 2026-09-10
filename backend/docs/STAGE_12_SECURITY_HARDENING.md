# Stage 12 — Production Security & API Hardening

This stage hardens the Django/DRF service without changing the scientific model behavior.

## Changes

- Base settings default to `DEBUG=False` and a non-wildcard local `ALLOWED_HOSTS`.
- Production settings (`config.settings.prod`) fail fast when the secret or hosts are unsafe.
- Production requires explicit CORS and CSRF origins.
- HTTPS redirect, secure cookies, HSTS, `nosniff`, referrer policy, COOP, and `X-Frame-Options` are configured.
- Added scoped DRF throttles for expensive operations:
  - analysis
  - satellite search
  - satellite acquisition
  - imagery upload
- Added `.env.production.example`.
- Development settings remain convenient but are explicitly local-only.

## Operational rules

1. Never deploy with `config.settings.dev`.
2. Never set `DJANGO_ALLOWED_HOSTS=*` in production.
3. Generate `DJANGO_SECRET_KEY` outside source control.
4. Put uploaded media behind authenticated/object storage or an authenticated media gateway; Django's `static()` media serving is development-only.
5. Tune throttle values to the deployment's worker/GPU capacity.

## Validation

Use:

```bash
python manage.py check --deploy --settings=config.settings.prod
```

with production environment variables configured. This environment may not contain Django, so the repository's static checks are used when Django is unavailable.
