# SatQuery-X Security & Secrets Policy

## 1. Zero-Exposure Rule for Credentials

* **Server-Side Exclusivity:** All API keys (`OPENAI_API_KEY`, `HF_TOKEN`, `MAPTILER_API_KEY`) and authentication credentials (`CDSE_USERNAME`, `CDSE_PASSWORD`, `DATABASE_URL`) are strictly loaded server-side by Django settings or environment variables.
* **No Client Leakage:** No private keys or authentication tokens are ever passed into Next.js bundles or exposed in frontend state or network payloads.
* **CDSE Token Isolation:** Bearer tokens acquired from CDSE Identity Realm are retained in-memory within `CDSETokenManager` on the backend server and refreshed via server-to-server calls.

---

## 2. API Authorization & RBAC

* **Authentication:** Stateless JSON Web Tokens (JWT) via `rest_framework_simplejwt`.
* **RBAC Roles:**
  * `demo`: Access to demo datasets and evaluation sandbox.
  * `judge`: Access to SIH evaluation scenarios, test benchmarks, and performance metrics.
  * `analyst`: Full project creation, custom AOI monitoring, and intelligence query capability.
  * `admin`: Operational dashboard, data provider configurations, and audit inspection.
* **Ownership Verification:** All session, query, and AOI operations enforce object-level ownership checks (`user == request.user` or matching `organization`).

---

## 3. Upload & File Validation Security

* Maximum file size limits (500MB per raster upload).
* Magic byte MIME-type verification (only authentic GeoTIFF, TIFF, PNG, JPEG permitted).
* Path traversal prevention: filenames are sanitized using UUID prefixes; uploads are constrained to `MEDIA_ROOT/sessions/<uuid>/`.

---

## 4. Immutable Audit Trail

Every operational action is logged via `apps.audit.models.log_audit_event`:
* Submitting queries, selecting satellite scenes, clipping AOIs, exporting intelligence dossiers, and modifying permissions produce an immutable audit log entry containing timestamp, user ID, IP address, and parameters.
