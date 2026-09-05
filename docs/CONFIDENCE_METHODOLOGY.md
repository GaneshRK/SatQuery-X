# SatQuery-X — Empirical Confidence Calibration Methodology

## 1. Principles of Scientific Calibration
Under PS 26167 and ISO/OGC remote sensing standards, confidence must never be a hardcoded number (`0.82`, `0.92`) or a theatrical claim (`ISRO Evaluator Verified`). Instead, confidence is an empirical mathematical composite of verifiable observation and execution telemetry.

## 2. Multi-Factor Formula
The composite confidence score $C \in [0.40, 0.97]$ is computed as:

$$C = (w_1 \cdot Q_{\text{cloud}}) + (w_2 \cdot Q_{\text{spatial}}) + (w_3 \cdot Q_{\text{agreement}}) + (w_4 \cdot Q_{\text{coverage}})$$

Where:
* $w_1 = 0.35$: **Cloud & Atmospheric Quality ($Q_{\text{cloud}}$)**
  * Evaluated from satellite metadata and QA60/SCL masks.
  * $Q_{\text{cloud}} = \max(0.30, 1.0 - (\text{CloudPct} / 100) \times 1.1)$ for cloudy scenes; $\ge 0.85$ under optimal clear-sky overpasses ($<15\%$).
* $w_2 = 0.25$: **Spatial Registration & Resolution ($Q_{\text{spatial}}$)**
  * $0.93$ when dual-overpasses are coregistered on 10m Sentinel-2 GSD grid.
  * $0.88$ for single-pass reference.
  * $0.65$ when operating solely on administrative bounding box approximations.
* $w_3 = 0.15$: **Model & External Agreement ($Q_{\text{agreement}}$)**
  * Incorporates cross-model agreement and corroboration from tier-1 government sources (e.g. TNSDMA, IMD).
* $w_4 = 0.25$: **Evidence Coverage & Density ($Q_{\text{coverage}}$)**
  * Evaluated from the presence, continuity, and spatial cohesion of polygonized change vectors or spectral indices.

## 3. Machine-Readable Telemetry Schema
Every query response exposes the complete factor breakdown:
```json
{
  "score": 0.89,
  "level": "HIGH",
  "factors": [
    { "name": "cloud_quality", "score": 0.96 },
    { "name": "spatial_registration", "score": 0.93 },
    { "name": "model_agreement", "score": 0.83 },
    { "name": "evidence_coverage", "score": 0.88 }
  ]
}
```
