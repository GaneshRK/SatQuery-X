# Earth Observation & 3D Globe Architecture

## 1. 3D Globe & Earth Observatory

The **Earth Observatory** serves as the primary visual entrypoint for SatQuery-X. Instead of a 2D web map, users view Earth rendered in 3D WebGL space with:
* Atmospheric scattering shader effect.
* NASA / Blue Marble & Esri World Imagery global satellite texture mosaic.
* Day / night terminator boundary shading.
* Dynamic orbital path overlays showing Sentinel-1 / Sentinel-2 ground tracks.
* Interactive 3D AOI boundary markers.

---

## 2. Orbital Camera Engine

The camera orchestrator handles progressive multi-scale transitions:
```typescript
interface CameraTarget {
  center: [number, number]; // [lng, lat]
  zoom: number;             // 1 (Orbit) to 14 (Ground GSD)
  pitch: number;            // 0° (Nadir) to 60° (Orbital horizon)
  bearing: number;          // Heading angle
  durationMs: number;       // Smooth flight duration
}
```

When a user searches for a location (e.g., *"Chennai"*, *"Pollachi"*, *"Brahmaputra Basin"*):
1. Location is geocoded to bounding envelope and centroid.
2. The orbital camera tilts, rotates the Earth globe toward the region, and begins a progressive descent.
3. As altitude drops below 100 km, the high-resolution Sentinel satellite observation is fetched and layered onto the terrain.

---

## 3. Sensor Modalities & Physical Radiometry

### Optical Multispectral (Sentinel-2 L2A)
* 10m spatial resolution across visible (B02, B03, B04) and near-infrared (B08).
* 20m spatial resolution across red-edge (B05-B07) and shortwave infrared (B11, B12).
* Bottom-of-Atmosphere (BOA) surface reflectance calibration.
* Cloud / Shadow masking using the Scene Classification Layer (SCL).

### Synthetic Aperture Radar (Sentinel-1 C-SAR GRD)
* C-band active microwave radar at 5.405 GHz.
* Dual polarization: VV (Vertical-Vertical) and VH (Vertical-Horizontal).
* Radiometric calibration to sigma-nought ($\sigma^0$) backscatter coefficient in decibels (dB).
* Penetrates cloud cover, fog, and smoke; operates during day and night.
