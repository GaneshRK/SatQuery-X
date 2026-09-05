# SatQuery-X — Repository Audit & Architectural Integrity Report

## Executive Summary
This document provides an exhaustive, component-by-component scientific, security, and architectural audit of the **SatQuery-X** codebase (SIH 2026 PS 26167: *Agentic Multimodal Satellite Reasoning Engine*). Every finding documents the baseline behavior, problem classification, scientific and security risks, user impact, required fix, and independent verification method.

---

## Audit Matrix

### 1. Natural Language Input Unblocking & Chat Interface
* **Component:** `frontend/src/components/ChatConsole.tsx`
* **Current Behavior:** Previously, the chat submission button was disabled via `disabled={loading || !hasImages}`. Text-only queries were blocked on the frontend, and placeholders implied image uploads were mandatory.
* **Problem:** Direct violation of PS 26167 (§5 Natural Language Must Be First-Class). Users asking "What is changing around Chennai?" were blocked unless they uploaded a dummy raster or triggered a canned demo scenario.
* **Severity:** Critical
* **Scientific Risk:** High — prevented autonomous geospatial search from spatial bounding boxes and natural language place names.
* **Security Risk:** Low
* **User Impact:** System felt like an image captioner rather than an agentic satellite intelligence workstation.
* **Required Fix:** Removed `!hasImages` check from button and textarea disable attributes; updated prompt placeholder to dynamic rotation: *"Ask anything about Earth (e.g. What is changing around Chennai?)..."*.
* **Verification Method:** Verified via automated script `scripts/e2e_query_test.py` and scenario test runner without image payloads.

---

### 2. Hardcoded Fallback Scientific Constants (Area & Confidence)
* **Component:** `backend/apps/agent/executor.py`, `backend/apps/agent/georeason.py`, `backend/apps/models_ai/`
* **Current Behavior:** Previously contained `.get("changed_area_hectares", 18.2)`, `confidence = 0.82`, and synthetic area fallbacks.
* **Problem:** When change detection returned an empty set or failed to polygonize, the system silently substituted `18.2` ha and `82%` confidence.
* **Severity:** Critical
* **Scientific Risk:** Extreme — fabricating Earth observation metrics and false precision damages scientific credibility.
* **Security Risk:** Low
* **User Impact:** Users received identical 18.2 ha / 82% values regardless of the actual region analyzed.
* **Required Fix:** Eradicated `18.2` and static `0.82`. In `executor.py`, area metrics are dynamically derived from actual polygonized `EvidenceRegion` objects (`area_km2` and geodesic hectares). In `georeason.py`, implemented dynamic multi-factor confidence calibration (`cloud_quality`, `spatial_registration`, `model_agreement`, `evidence_coverage`).
* **Verification Method:** Grep search for `18.2` across the codebase; verified dynamic confidence varies across varying cloud cover and scene conditions.

---

### 3. Generic "Stable Landcover" Fallback for Change Queries
* **Component:** `backend/apps/agent/georeason.py`
* **Current Behavior:** When `change_events` was empty, `georeason.py` emitted: *"Satellite observations across {aoi_name} indicate stable landcover distribution with nominal seasonal vegetative and structural variation."*
* **Problem:** Directly called out in §6, §67, §107. When a user asked *"What is changing around Coimbatore?"*, an empty change result was disguised as an authoritative declaration of "stable landcover" rather than explicitly stating that no change was detected above threshold.
* **Severity:** High
* **Scientific Risk:** High — confusing `NO_CHANGE_DETECTED` with general landcover stability without multi-temporal verification.
* **Security Risk:** None
* **User Impact:** Users received deceptive canned statements instead of clear, calibrated change detection reports.
* **Required Fix:** Refactored `georeason.py` to differentiate query intent: for change queries, state *"Multispectral satellite observation analysis across {aoi_name} detected no surface reflectance transitions exceeding the change detection significance threshold. Detected change: none above threshold."*
* **Verification Method:** Tested with `What is changing around Coimbatore?` via scenario test suite.

---

### 4. Theatrical & Unsubstantiated Verification Badges
* **Component:** `frontend/src/components/Header.tsx`
* **Current Behavior:** Header displayed `ISRO Evaluator Verified` badge alongside `LIVE SATELLITE VIDEO` styling.
* **Problem:** Violation of §12, §37, §38. No official ISRO agency verification had occurred; Earth observation satellites are near-real-time sun-synchronous overpasses, not streaming video.
* **Severity:** Medium
* **Scientific Risk:** Medium — misleading scientific claims.
* **Security Risk:** None
* **User Impact:** Creates false expectations and damages academic and enterprise trust.
* **Required Fix:** Replaced with honest technical compliance badges: `STAC & OGC Compliant` and `Near-Real-Time Catalogue`.
* **Verification Method:** Inspected `Header.tsx` DOM rendering.

---

### 5. Architectural Duality (Dead FastAPI vs Canonical Django)
* **Component:** `backend/api/` (8 route files), `backend/main.py`
* **Current Behavior:** Repository contained an orphaned FastAPI skeleton (`backend/main.py` and `backend/api/*`) alongside the production Django 5.1 + DRF application.
* **Problem:** Violation of §119. Created confusion over which backend was canonical, conflicting Dockerfiles, and diverging data models.
* **Severity:** High
* **Scientific Risk:** None
* **Security Risk:** Medium — potential unmaintained API attack surface if exposed.
* **User Impact:** Developer and deployment confusion.
* **Required Fix:** Deleted dead `backend/api/` directory and `backend/main.py`. Standardized all documentation and endpoints on Django 5.1 REST Framework (`/api/v1/...`).
* **Verification Method:** Clean directory structure; `python manage.py check` passes with 0 issues.

---

### 6. Session Workspace vs Demo Scenario Contamination
* **Component:** `frontend/src/components/Header.tsx`, `backend/apps/sessions/views.py`
* **Current Behavior:** Every user session loaded the first seeded demo scenario (e.g., Scenario 6 or Flood Kaziranga), polluting new user workspaces.
* **Problem:** Violation of §39, §131, §132. A fresh user was immediately thrust into a hardcoded historical scenario instead of a clean Earth Intelligence Workspace.
* **Severity:** High
* **Scientific Risk:** Medium — users conflated canned demo evidence with their live queries.
* **Security Risk:** None
* **User Impact:** Frustrating user experience where clean queries inherited old demo context.
* **Required Fix:** Partitioned sessions into `My Workspaces` and `Demo Scenarios`. Fresh logins default to a new, empty Earth Workspace.
* **Verification Method:** Verified session dropdown grouping and default state on fresh browser session.

---

### 7. Satellite Retrieval Non-Hallucination Guardrails
* **Component:** `backend/apps/agent/agent.py`
* **Current Behavior:** In certain edge cases when STAC provider searches returned 0 candidates, mock imagery was silently fetched or synthesized without user notification.
* **Problem:** Violation of §7, §79, §111, §117. The system must never hallucinate satellite data or scenes when none are catalogued.
* **Severity:** Critical
* **Scientific Risk:** Extreme — creates fabricated satellite observations.
* **Security Risk:** None
* **User Impact:** Misleads user into thinking real satellite passes were retrieved.
* **Required Fix:** Implemented strict guardrail in `agent.py:246`: if STAC search returns 0 scenes, execution halts with structured state `SATELLITE_DATA_UNAVAILABLE` and prompts user for wider temporal/spatial bounds.
* **Verification Method:** Verified by querying a future date or invalid cloud threshold.

---

### 8. Location & Temporal Contamination
* **Component:** `backend/apps/agent/query_optimizer.py`, `backend/apps/agent/executor.py`
* **Current Behavior:** Potential for Chennai metropolitan bounds to bleed into Coimbatore or Pollachi queries if context wasn't reset.
* **Problem:** Violation of §96, §97, §98. Querying Coimbatore must never return Chennai metadata or bounding boxes.
* **Severity:** Critical
* **Scientific Risk:** High — geospatial spatial mismatch.
* **Security Risk:** None
* **User Impact:** Incoherent answers where text refers to Coimbatore but coordinates show Chennai.
* **Required Fix:** Enhanced `QueryOptimizer` with distinct, authoritative spatial polygons and bboxes for Coimbatore (`[76.90, 10.95, 77.05, 11.08]`), Chennai, Pollachi, Western Ghats, Mumbai, and Delhi NCR. Explicitly pass resolved `aoi.name` into `georeason.py`.
* **Verification Method:** Automated location isolation tests in `scripts/test_all_scenarios.py`.

---

### 9. Latency & Execution Telemetry Fidelity
* **Component:** `backend/apps/agent/executor.py`, `frontend/src/components/ExecutionTrace.tsx`
* **Current Behavior:** Synthetic latencies (e.g. 18ms, 3ms) previously mocked in demo UI.
* **Problem:** Violation of §29, §103. Real raster manipulation and satellite IO cannot occur in 3ms.
* **Severity:** Medium
* **Scientific Risk:** Low
* **Security Risk:** None
* **User Impact:** Theatrical presentation eroded engineering trust.
* **Required Fix:** Instrument real monotonic server timestamps (`time.perf_counter()`) on every tool step (`started_at`, `finished_at`, `duration_ms`).
* **Verification Method:** Verified telemetry values reflect actual elapsed execution milliseconds.
