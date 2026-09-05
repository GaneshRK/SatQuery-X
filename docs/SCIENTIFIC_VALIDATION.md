# SatQuery-X — Scientific Validation Suite & Test Protocols

## 1. Scope of Scientific Testing
The scientific test suite (`backend/tests/scientific/`) validates physical and mathematical algorithms independent of UI and web frameworks:
1. **Coordinate Reference System (CRS) & Projection-Aware Math:**
   * Distinguishes projected meter CRS (UTM zones, EPSG:3857) from geographic degree CRS (WGS-84 EPSG:4326).
   * Ensures degrees are never multiplied as meters (averting $10^{-8}$ area errors or $10^{10}$ arbitrary scaling).
   * Uses local cylindrical equal-area projection or WGS-84 degree length formulas ($dx \cdot \text{deg\_lon\_m} \cdot dy \cdot \text{deg\_lat\_m}$) to quantify geodesic ground area.
2. **Spectral Indices Implementation:**
   * $\text{NDVI} = \frac{\text{NIR} - \text{Red}}{\text{NIR} + \text{Red}}$ clipped to $[-1.0, 1.0]$.
   * $\text{NDWI} = \frac{\text{Green} - \text{NIR}}{\text{Green} + \text{NIR}}$ for surface water detection.
   * $\text{NDBI} = \frac{\text{SWIR} - \text{NIR}}{\text{SWIR} + \text{NIR}}$ for built-up impervious surface mapping.
   * $\text{NBR} = \frac{\text{NIR} - \text{SWIR2}}{\text{NIR} + \text{SWIR2}}$ for burn scar and severity indexing.
   * Sensor profile verification ensuring correct bands are selected per sensor (Sentinel-2, Landsat-8/9).
3. **Anti-Hallucination & Honest Error Reporting:**
   * Absence of detected change emits explicit `"none above threshold"` narrative rather than blanket `"stable landcover distribution"` claims.
   * Uncatalogued satellite criteria produce structured `SATELLITE_DATA_UNAVAILABLE` exceptions.
4. **Spatial & Context Isolation:**
   * Ensures Coimbatore queries never return Chennai metadata or bounding boxes.
