# SatQuery-X — Local Windows Run Guide

## Services

1. Memurai/Redis: Windows service on `localhost:6379`
2. Django API: `http://127.0.0.1:8000`
3. Celery: run with `--pool=solo` on Windows
4. Frontend: `http://localhost:3000`

## Start

### Terminal 1 — Django
```powershell
cd C:\Users\Manoj\OneDrive\Desktop\SatQuery-X\SatQuery-X
.\.venv\Scripts\Activate.ps1
cd backend
python manage.py migrate
python manage.py check
python manage.py runserver
```

### Terminal 2 — Celery
```powershell
cd C:\Users\Manoj\OneDrive\Desktop\SatQuery-X\SatQuery-X
.\.venv\Scripts\Activate.ps1
cd backend
celery -A config worker --loglevel=info --pool=solo
```

### Terminal 3 — Frontend
```powershell
cd C:\Users\Manoj\OneDrive\Desktop\SatQuery-X\SatQuery-X\frontend
npm install
npm run dev
```

## SQLite note

The local development database uses a 30-second SQLite lock timeout because Django and Celery can access the database concurrently. PostgreSQL is recommended for production.

## Scientific result note

A queued `202` response is not a final scientific answer. The frontend waits for the analysis task to complete and displays the actual result or structured failure. Ground-truth accuracy is shown only when a labeled evaluation result is supplied.

## Training

The package contains training/evaluation entry points, but no trained checkpoint is created by installing the software. Training requires a valid labeled manifest/dataset and should be performed before claiming model accuracy.
