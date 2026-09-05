# SatQuery-X — Production Readiness Checklist & Deployment Guide

## 1. Production Architecture Checklist
* [x] **Canonical Framework:** Standardized on Django 5.1 REST Framework (`backend/config/urls.py`).
* [x] **Database Isolation:** PostgreSQL 16 with PostGIS extension for spatial queries; connection pooling via `CONN_MAX_AGE`.
* [x] **Worker Topology:** Celery workers configured with Redis broker for long-running heavy raster downloads and multi-temporal diffs.
* [x] **Spatial Storage:** MinIO / AWS S3 for Cloud-Optimized GeoTIFF (COG) storage; PostgreSQL stores geometric metadata and vector polygons.
* [x] **Security & RBAC:** Session and query isolation enforced by Organization and User ID; no cross-user session leakage.
* [x] **Zero Synthetic Data:** All hardcoded area constants (`18.2` ha), fake bboxes, and static confidence scores (`0.82`) eradicated.
* [x] **Telemetry & Latency:** Real execution timings captured via `time.perf_counter()` on every tool step.

## 2. Environment Configuration
Ensure `.env` contains valid production secrets:
```bash
DJANGO_SECRET_KEY=production-secure-key-here
DATABASE_URL=postgres://satquery:securepass@postgres:5432/satquery_db
REDIS_URL=redis://redis:6379/0
S3_ENDPOINT=https://minio.internal:9000
S3_ACCESS_KEY=minio_admin
S3_SECRET_KEY=minio_secret_pass
COPERNICUS_CLIENT_ID=your-cdse-client-id
COPERNICUS_CLIENT_SECRET=your-cdse-client-secret
```

## 3. Deployment Commands
```bash
# Backend Migrations & Static Files
python manage.py migrate
python manage.py collectstatic --noinput

# Celery Worker
celery -A config worker --loglevel=info --concurrency=4

# Gunicorn WSGI Server
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4

# Frontend Production Build
cd frontend
npm run build
npm start
```
