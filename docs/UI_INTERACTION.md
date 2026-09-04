# SatQuery-X — UI Interaction & Visual Grounding Specification

## 1. Visual Interaction Modes

### A. Point-and-Ask
* **User Action**: Click anywhere on the satellite viewport.
* **System Response**:
  - Drops a temporary inspection marker with coordinates.
  - Surfaces a floating quick-query bar:
    `"Point selected [13.082° N, 80.270° E]. Ask: [What is here?] [Measure area] [Find changes] [Compare over time]"`
  - Attaches coordinate point to the active query context.

### B. Draw-and-Ask
* **User Action**: Draw a bounding box, polygon, or radius circle.
* **System Response**:
  - Automatically calculates geodesic surface area (hectares / km²).
  - Sets `context.active_region` to the drawn GeoJSON geometry.
  - Focuses subsequent vision-language queries on the designated polygon boundary.

### C. Hover Intelligence
* **User Action**: Hover cursor over any AI-detected vector polygon or change boundary.
* **System Response**:
  - Renders a lightweight, unobtrusive tooltip:
    - **Class**: e.g., "New Construction" / "Water Inundation"
    - **Area**: e.g., "18.2 hectares"
    - **Date Interval**: e.g., "2020-01-10 $\to$ 2023-12-05"
    - **Confidence**: e.g., "94% calibrated"

### D. Click-to-Explain
* **User Action**: Click any AI-detected evidence polygon.
* **System Response**:
  - Opens the `ClickToExplainModal`:
    - Full breakdown of satellite observations compared (Sentinel-2 overpass dates, cloud coverage).
    - Spectral delta or backscatter ratio values explaining why the AI flagged the region.
    - Calibrated confidence drivers and uncertainties.
    - Quick actions: `[Ask about this change]` / `[Export GeoJSON]`.

---

## 2. ContextBar Component
Located directly above the main viewport:
* **AOI Indicator**: Active Area of Interest name.
* **Entity Focus**: Active target entity (e.g. "Built-up clusters").
* **Temporal Span**: Active observation dates (e.g. "2020 $\to$ 2026").
* **Interaction Mode Switch**: Toggle between **Simple Mode** (clean conversational plain text) and **Expert Mode** (sensor bands, CRS, resolution, algorithmic thresholds).
* **Reset Context**: One-click action clearing multi-turn memory to begin a fresh investigation.
