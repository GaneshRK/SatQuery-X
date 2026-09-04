# AI & Computer Vision Architecture

SatQuery AI decouples high-level natural language reasoning from deterministic geospatial computations.

---

## 1. Pluggable AI Provider Architecture

```text
ModelRouter
   ├── LocalProvider (Deterministic CV & Baseline Models)
   ├── OpenAIProvider (GPT-4o / GPT-4o-mini Multimodal Reasoning)
   └── HuggingFaceProvider (Specialized Remote Sensing Models)
```

### Provider Responsibilities
* **LLM / VLM:** Decomposes queries, creates execution plans, interprets multi-modal results, explains evidence, generates structured intelligence.
* **Deterministic CV Engine:** Never delegates area calculations, contour extraction, or pixel math to an LLM. Executes using `RasterEngine`, `scipy.ndimage`, and `shapely`.

---

## 2. Model Registry & Health Checks

Every model in `ModelRegistry` implements:
* `health_check()`: Verifies local weights, GPU availability, or remote API reachability.
* Models are only marked `"READY"` if their inference pipeline functions without error.

---

## 3. Canonical 10-Key Answer Contract

Every AI response satisfies the production contract:
```json
{
  "answer": "string",
  "confidence": 0.92,
  "findings": ["Detailed findings..."],
  "measurements": [{ "metric": "area_km2", "value": 41.3, "unit": "km2" }],
  "regions": [/* GeoJSON Feature Array */],
  "evidence": [/* Artifact Crops & Layer References */],
  "sources": [{ "sensor": "SENTINEL-2", "provider": "CDSE" }],
  "models": ["detect_water", "calculate_ndvi"],
  "methods": ["Normalized Difference Water Index", "Cylindrical Equal Area Integration"],
  "limitations": ["Constrained by 10m GSD spatial resolution"]
}
```

---

## 4. Calibrated Confidence & Data Quality

Confidence is never fabricated by prompting an LLM. It is mathematically derived via `ConfidenceEngine`:
* **Cloud Contamination Penalty:** Reduces confidence if cloud cover exceeds 5%.
* **Resolution Penalty:** Accounts for sensor GSD constraints.
* **NoData Penalty:** Deducts for unobservable or corrupted pixels.
* **CRS Validation:** Confirms rigorous projection standards.
