# SatQuery-X Production Deployment Guide

## 1. Prerequisites

* **Operating System:** Ubuntu 22.04 LTS / Debian 12 / RHEL 9 (or Windows WSL2)
* **Python:** 3.11+
* **Node.js:** 18+ LTS or 20+ LTS
* **Database:** PostgreSQL 16+ with PostGIS 3.4 extension
* **Broker & Cache:** Redis 7+
* **Storage:** MinIO or AWS S3

---

## 2. Environment Configuration

Copy `.env.example` to `.env` in the project root and provide production credentials:

```bash
# Django Core
DJANGO_SECRET_KEY=production-secret-key-32-chars-minimum
DJANGO_DEBUG=False
ALLOWED_HOSTS=satquery.yourdomain.com,api.satquery.yourdomain.com

# PostgreSQL + PostGIS
DATABASE_URL=postgresql://satquery:secure_db_password@localhost:5432/satquery

# Redis
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0

# Copernicus CDSE
CDSE_USERNAME=your_copernicus_username
CDSE_PASSWORD=your_copernicus_password
CDSE_CLIENT_ID=cdse-public

# AI Provider (Optional server-side)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Mode
SATQUERY_MODE=production
```

---

## 3. Database Initialization & Migrations

```bash
# Activate virtual environment
source .venv/bin/activate # or .venv\Scripts\activate on Windows

# Run migrations
python backend/manage.py migrate

# Seed baseline AI models and showcase sessions
python backend/manage.py seed_sih_demos
```

---

## 4. Running Backend Services

### WSGI Web Server (Gunicorn)
```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4 --threads 2 --timeout 120
```

### Celery Background Worker & Beat Scheduler
```bash
# Terminal 1: Celery Worker
celery -A config worker --loglevel=info --concurrency=4

# Terminal 2: Celery Beat (NRT Catalogue Synchronizer)
celery -A config beat --loglevel=info
```

---

## 5. Running Frontend Production Build

```bash
cd frontend
npm ci
npm run build
npm start -- -p 3000
```
