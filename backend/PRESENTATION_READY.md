# SatQuery-X — Presentation Ready Backend

This package is the complete Django/Celery backend replacement for the current SatQuery-X backend.

## Runtime flow

1. Frontend submits a query and optional image(s).
2. Django persists the query and image assets.
3. Uploaded images are ingested first; metadata is extracted from the actual file.
4. Celery starts analysis only after ingestion completes.
5. Query understanding selects the analysis path.
6. Scientific tools/models execute and persist evidence.
7. Django persists `COMPLETED` or `FAILED` plus answer/evidence/trace.
8. Frontend polls the query detail endpoint until the terminal state.

## Location questions

For `What place is this?`, `Which area is this?`, and similar requests, a georeferenced raster is handled directly from its real CRS/WGS84 bounds. The backend returns the scene bounding box, centroid coordinates, CRS and, when network reverse-geocoding is available, the real place name.

An ordinary JPG/PNG without georeferencing is never assigned a fake coordinate. It returns a clear limitation and asks for a georeferenced GeoTIFF or an explicit map/AOI selection.

## Two-image analysis

The existing temporal/cross-modal pipeline remains available. Results are exposed from the actual backend evidence bundle; the frontend does not insert fallback area/confidence numbers.

## Image quality

The imagery ingestion pipeline creates display previews from the real uploaded raster using contrast normalization. The scientific source file remains unchanged.

## Windows startup

See `LOCAL_WINDOWS_RUN.md`.

Typical terminals:

```powershell
# Terminal 1
cd backend
.\.venv\Scripts\Activate.ps1
python manage.py runserver

# Terminal 2
cd backend
.\.venv\Scripts\Activate.ps1
celery -A config worker --loglevel=info --pool=solo

# Terminal 3
cd frontend
npm install
npm run dev
```

Redis/Memurai must be running on port 6379.
