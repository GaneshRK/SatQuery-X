# SatQuery-X — Known Limitations & Honest Disclosure

In adherence to Section 63, Section 119, and Section 146 of the Master Specification, the following limitations are transparently disclosed:

## 1. Cloud & Atmospheric Obscuration
* **Limitation:** Optical Earth observation (Sentinel-2, Landsat-8/9) cannot penetrate dense cloud cover or thick convective storm systems.
* **System Handling:** Scenes with $>20\%$ cloud cover are penalized in the confidence engine and flagged with explicit uncertainty warnings. When optical imagery is occluded, SAR (Sentinel-1 / RISAT) should be requested for all-weather flood/structural penetration.

## 2. Spatial Resolution (GSD) Boundaries
* **Limitation:** Free public multispectral imagery (Sentinel-2 10m, Landsat 30m) cannot resolve individual vehicles, small roof details, or narrow pedestrian pathways.
* **System Handling:** Sub-pixel claims are avoided. Ground Sample Distance (GSD) limitations are stated in confidence reports when queries ask about features smaller than 10 meters.

## 3. Revisit Cycle & Temporal Latency
* **Limitation:** Sun-synchronous satellites do not provide real-time streaming video. Revisit rates range from 5 days (Sentinel-2 constellation) to 16 days (Landsat-8/9).
* **System Handling:** The system labels products as *"Near-Real-Time Overpasses"* or *"Latest Available Observation"*, never "Live Satellite Video".

## 4. Ground Truth & Validation Nuance
* **Limitation:** Remote sensing observations detect spectral reflectance shifts, which can be affected by seasonal phenology (e.g. crop harvesting vs urban clearing).
* **System Handling:** The system reports *"Evidence-calibrated confidence"*, never claiming *"Ground verified"* or *"ISRO Evaluator Verified"* unless empirical ground sensor/field survey data is linked.
