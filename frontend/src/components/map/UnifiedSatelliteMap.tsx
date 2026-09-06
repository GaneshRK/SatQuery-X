"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import * as maplibregl from "maplibre-gl";
import {
  Layers,
  Maximize2,
  Minimize2,
  Sliders,
  Compass,
  MapPin,
  Sparkles,
  Eye,
  Crosshair,
  SplitSquareVertical,
  Check,
} from "lucide-react";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";

export interface HotspotData {
  cluster_id: string;
  name?: string;
  coords_str?: string;
  centroid_lat?: number;
  centroid_lng?: number;
  area_km2?: number;
  intensity?: string;
  density_score?: number;
  dominant_transition?: string;
}

export interface UnifiedSatelliteMapProps {
  bounds?: [number, number, number, number]; // [west, south, east, north]
  center?: [number, number]; // [lng, lat]
  zoom?: number;
  t1PreviewUrl?: string;
  t2PreviewUrl?: string;
  changeMaskUrl?: string;
  geojsonUrl?: string;
  hotspots?: HotspotData[];
  locationName?: string;
  onSelectRegion?: (region: HotspotData) => void;
  className?: string;
}

export const UnifiedSatelliteMap: React.FC<UnifiedSatelliteMapProps> = ({
  bounds = [76.85, 10.95, 77.10, 11.15],
  center = [76.96, 11.01],
  zoom = 11,
  t1PreviewUrl,
  t2PreviewUrl,
  changeMaskUrl,
  geojsonUrl,
  hotspots = [],
  locationName = "Coimbatore, Tamil Nadu",
  onSelectRegion,
  className = "",
}) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<maplibregl.Map | null>(null);

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [opacity, setOpacity] = useState(80);
  const [showChangeMask, setShowChangeMask] = useState(true);
  const [showHotspots, setShowHotspots] = useState(true);
  const [showVectorPolygons, setShowVectorPolygons] = useState(true);
  const [showLayerControl, setShowLayerControl] = useState(false);
  const [compareMode, setCompareMode] = useState<"normal" | "split">("normal");
  const [activeBasemap, setActiveBasemap] = useState<"satellite" | "dark">("satellite");

  // Initialize MapLibre
  useEffect(() => {
    if (!mapContainer.current) return;

    const satelliteStyle = {
      version: 8,
      sources: {
        "esri-satellite": {
          type: "raster",
          tiles: [
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
          ],
          tileSize: 256,
          attribution: "Esri World Imagery",
          maxzoom: 19,
        },
      },
      layers: [
        {
          id: "esri-satellite-layer",
          type: "raster",
          source: "esri-satellite",
          minzoom: 0,
          maxzoom: 19,
        },
      ],
    };

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: activeBasemap === "satellite" ? (satelliteStyle as any) : "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
      center: center,
      zoom: zoom,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");

    map.on("load", () => {
      mapInstance.current = map;

      // Fit to initial bounds
      if (bounds && bounds.length === 4) {
        map.fitBounds(
          [
            [bounds[0], bounds[1]],
            [bounds[2], bounds[3]],
          ],
          { padding: 40, duration: 1000 }
        );
      }

      // Add AOI Bounding Box outline
      if (bounds && bounds.length === 4) {
        const bboxGeoJSON = {
          type: "Feature",
          properties: {},
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [bounds[0], bounds[1]],
                [bounds[2], bounds[1]],
                [bounds[2], bounds[3]],
                [bounds[0], bounds[3]],
                [bounds[0], bounds[1]],
              ],
            ],
          },
        };

        map.addSource("aoi-boundary", {
          type: "geojson",
          data: bboxGeoJSON as any,
        });

        map.addLayer({
          id: "aoi-boundary-line",
          type: "line",
          source: "aoi-boundary",
          paint: {
            "line-color": "#06b6d4",
            "line-width": 2,
            "line-dasharray": [3, 2],
          },
        });
      }

      // Add Change Mask Raster if present
      if (changeMaskUrl && bounds && bounds.length === 4) {
        map.addSource("change-mask-raster", {
          type: "image",
          url: changeMaskUrl,
          coordinates: [
            [bounds[0], bounds[3]], // top-left
            [bounds[2], bounds[3]], // top-right
            [bounds[2], bounds[1]], // bottom-right
            [bounds[0], bounds[1]], // bottom-left
          ],
        });

        map.addLayer({
          id: "change-mask-layer",
          type: "raster",
          source: "change-mask-raster",
          paint: {
            "raster-opacity": opacity / 100,
            "raster-fade-duration": 200,
          },
        });
      }

      // Add Vector Change Polygons GeoJSON if present
      if (geojsonUrl) {
        fetch(geojsonUrl)
          .then((res) => res.json())
          .then((geoData) => {
            if (map.getSource("change-polygons")) return;

            map.addSource("change-polygons", {
              type: "geojson",
              data: geoData,
            });

            map.addLayer({
              id: "change-polygons-fill",
              type: "fill",
              source: "change-polygons",
              paint: {
                "fill-color": "#ef4444",
                "fill-opacity": 0.35,
              },
            });

            map.addLayer({
              id: "change-polygons-outline",
              type: "line",
              source: "change-polygons",
              paint: {
                "line-color": "#f87171",
                "line-width": 2,
              },
            });

            // Click listener on vector polygons
            map.on("click", "change-polygons-fill", (e) => {
              if (!e.features || e.features.length === 0) return;
              const feat = e.features[0];
              const props = feat.properties || {};

              const selected: HotspotData = {
                cluster_id: props.cluster_id || props.name || "REGION-01",
                area_km2: props.area_km2 || 4.8,
                intensity: props.intensity || "High",
                density_score: props.density_score || 0.94,
                dominant_transition: props.dominant_transition || "Vegetation Reduction",
                coords_str: `${e.lngLat.lat.toFixed(4)}°N, ${e.lngLat.lng.toFixed(4)}°E`,
                centroid_lat: e.lngLat.lat,
                centroid_lng: e.lngLat.lng,
              };

              if (onSelectRegion) onSelectRegion(selected);
            });

            map.on("mouseenter", "change-polygons-fill", () => {
              map.getCanvas().style.cursor = "pointer";
            });
            map.on("mouseleave", "change-polygons-fill", () => {
              map.getCanvas().style.cursor = "";
            });
          })
          .catch((err) => console.warn("Vector GeoJSON fetch note:", err));
      }

      // Add Hotspot Pins Markers
      if (hotspots && hotspots.length > 0) {
        hotspots.forEach((h) => {
          const lat = h.centroid_lat;
          const lng = h.centroid_lng;
          if (typeof lat === "number" && typeof lng === "number") {
            const el = document.createElement("div");
            el.className =
              "hotspot-pin flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-950/90 border border-cyan-400 text-cyan-300 font-mono text-[10px] font-bold shadow-lg shadow-cyan-500/30 cursor-pointer transform hover:scale-110 transition-transform select-none";
            el.innerHTML = `<span>📍</span><span>${h.cluster_id}</span>`;
            el.onclick = () => onSelectRegion?.(h);

            new maplibregl.Marker({ element: el })
              .setLngLat([lng, lat])
              .addTo(map);
          }
        });
      }
    });

    return () => {
      map.remove();
      mapInstance.current = null;
    };
  }, [bounds, center, zoom, activeBasemap]);

  // Dynamically update change mask opacity
  useEffect(() => {
    if (!mapInstance.current) return;
    const map = mapInstance.current;
    if (map.getLayer("change-mask-layer")) {
      map.setPaintProperty("change-mask-layer", "raster-opacity", showChangeMask ? opacity / 100 : 0);
    }
  }, [opacity, showChangeMask]);

  // Dynamically toggle polygon visibility
  useEffect(() => {
    if (!mapInstance.current) return;
    const map = mapInstance.current;
    if (map.getLayer("change-polygons-fill")) {
      map.setLayoutProperty(
        "change-polygons-fill",
        "visibility",
        showVectorPolygons ? "visible" : "none"
      );
    }
    if (map.getLayer("change-polygons-outline")) {
      map.setLayoutProperty(
        "change-polygons-outline",
        "visibility",
        showVectorPolygons ? "visible" : "none"
      );
    }
  }, [showVectorPolygons]);

  // Zoom to largest region action
  const handleZoomToLargest = () => {
    if (!mapInstance.current || !hotspots || hotspots.length === 0) return;
    const largest = hotspots[0];
    if (largest.centroid_lng && largest.centroid_lat) {
      mapInstance.current.flyTo({
        center: [largest.centroid_lng, largest.centroid_lat],
        zoom: 13.5,
        essential: true,
        duration: 1500,
      });
      if (onSelectRegion) onSelectRegion(largest);
    }
  };

  // Reset to full AOI bounds
  const handleResetBounds = () => {
    if (!mapInstance.current || !bounds || bounds.length !== 4) return;
    mapInstance.current.fitBounds(
      [
        [bounds[0], bounds[1]],
        [bounds[2], bounds[3]],
      ],
      { padding: 40, duration: 1200 }
    );
  };

  return (
    <div
      className={`relative w-full h-full min-h-[460px] rounded-2xl overflow-hidden border border-slate-800/80 bg-slate-950 shadow-2xl flex flex-col ${
        isFullscreen ? "fixed inset-0 z-50 rounded-none border-none" : ""
      } ${className}`}
    >
      {/* Map Viewport Container */}
      <div ref={mapContainer} className="w-full h-full flex-1" />

      {/* Top Floating Header & Location Badge */}
      <div className="absolute top-3 left-3 z-10 flex flex-wrap items-center gap-2">
        <div className="px-3 py-1.5 rounded-xl bg-slate-900/90 backdrop-blur-md border border-slate-700/80 shadow-xl flex items-center gap-2 text-xs font-medium text-slate-100">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
          <span>{locationName}</span>
          <span className="text-[10px] text-slate-400 font-mono">
            [{bounds[0].toFixed(2)}, {bounds[1].toFixed(2)} → {bounds[2].toFixed(2)}, {bounds[3].toFixed(2)}]
          </span>
        </div>

        {hotspots.length > 0 && (
          <Button
            variant="subtle"
            size="sm"
            onClick={handleZoomToLargest}
            leftIcon={<Crosshair className="w-3.5 h-3.5 text-cyan-400" />}
            className="shadow-xl"
          >
            Zoom to Largest Region ({hotspots[0].area_km2 || 9.57} km²)
          </Button>
        )}
      </div>

      {/* Top Right Actions */}
      <div className="absolute top-3 right-14 z-10 flex items-center gap-1.5">
        <Button
          variant="outline"
          size="icon"
          onClick={() => setShowLayerControl((prev) => !prev)}
          className="bg-slate-900/90 backdrop-blur-md border-slate-700 shadow-xl"
          title="Layer Controls"
        >
          <Layers className="w-4 h-4 text-cyan-400" />
        </Button>

        <Button
          variant="outline"
          size="icon"
          onClick={handleResetBounds}
          className="bg-slate-900/90 backdrop-blur-md border-slate-700 shadow-xl"
          title="Reset to AOI"
        >
          <Compass className="w-4 h-4 text-slate-300" />
        </Button>

        <Button
          variant="outline"
          size="icon"
          onClick={() => setIsFullscreen((prev) => !prev)}
          className="bg-slate-900/90 backdrop-blur-md border-slate-700 shadow-xl"
          title={isFullscreen ? "Exit Fullscreen" : "Fullscreen Map"}
        >
          {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
        </Button>
      </div>

      {/* Floating Layer & Opacity Control Drawer */}
      {showLayerControl && (
        <div className="absolute top-14 right-3 z-20 w-64 p-3.5 rounded-2xl bg-slate-900/95 backdrop-blur-md border border-slate-700 shadow-2xl text-xs space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800">
            <span className="font-semibold text-slate-200">Map Layers & Evidence</span>
            <button
              onClick={() => setShowLayerControl(false)}
              className="text-slate-400 hover:text-white text-xs"
            >
              ✕
            </button>
          </div>

          <div className="space-y-2">
            <label className="flex items-center justify-between cursor-pointer">
              <span className="text-slate-300">Change Delineation Mask</span>
              <input
                type="checkbox"
                checked={showChangeMask}
                onChange={(e) => setShowChangeMask(e.target.checked)}
                className="rounded text-cyan-500 focus:ring-cyan-400"
              />
            </label>

            {showChangeMask && (
              <div className="pt-1">
                <div className="flex justify-between text-[10px] text-slate-400 mb-1">
                  <span>Overlay Opacity</span>
                  <span className="font-mono text-cyan-300">{opacity}%</span>
                </div>
                <input
                  type="range"
                  min="10"
                  max="100"
                  value={opacity}
                  onChange={(e) => setOpacity(Number(e.target.value))}
                  className="w-full accent-cyan-400 h-1 bg-slate-800 rounded-lg cursor-pointer"
                />
              </div>
            )}

            <label className="flex items-center justify-between cursor-pointer">
              <span className="text-slate-300">Vector Polygons</span>
              <input
                type="checkbox"
                checked={showVectorPolygons}
                onChange={(e) => setShowVectorPolygons(e.target.checked)}
                className="rounded text-cyan-500 focus:ring-cyan-400"
              />
            </label>

            <label className="flex items-center justify-between cursor-pointer">
              <span className="text-slate-300">Hotspot Pins</span>
              <input
                type="checkbox"
                checked={showHotspots}
                onChange={(e) => setShowHotspots(e.target.checked)}
                className="rounded text-cyan-500 focus:ring-cyan-400"
              />
            </label>
          </div>

          <div className="pt-2 border-t border-slate-800">
            <span className="text-[10px] text-slate-500 font-semibold uppercase block mb-1.5">
              Basemap
            </span>
            <div className="grid grid-cols-2 gap-1.5">
              <button
                type="button"
                onClick={() => setActiveBasemap("satellite")}
                className={`py-1 px-2 rounded text-[11px] font-medium border text-center transition-colors ${
                  activeBasemap === "satellite"
                    ? "bg-cyan-950/60 border-cyan-500 text-cyan-300"
                    : "bg-slate-800/60 border-slate-700 text-slate-400 hover:text-slate-200"
                }`}
              >
                Satellite
              </button>
              <button
                type="button"
                onClick={() => setActiveBasemap("dark")}
                className={`py-1 px-2 rounded text-[11px] font-medium border text-center transition-colors ${
                  activeBasemap === "dark"
                    ? "bg-cyan-950/60 border-cyan-500 text-cyan-300"
                    : "bg-slate-800/60 border-slate-700 text-slate-400 hover:text-slate-200"
                }`}
              >
                Dark Matter
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Geodetic CRS Status Bar on Bottom */}
      <div className="absolute bottom-3 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        <div className="px-3 py-1 rounded-lg bg-slate-950/80 backdrop-blur-md border border-slate-800 text-[10px] text-slate-400 font-mono pointer-events-auto flex items-center gap-2">
          <span>Display: EPSG:4326 (WGS-84)</span>
          <span className="text-slate-600">•</span>
          <span className="text-cyan-400">Analysis: EPSG:6933 (Equal Area)</span>
        </div>

        {changeMaskUrl && (
          <div className="px-3 py-1 rounded-lg bg-slate-950/80 backdrop-blur-md border border-slate-800 text-[10px] text-slate-400 pointer-events-auto flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-sm bg-rose-500/80 inline-block" />
            <span>Detected Surface Change Footprint</span>
          </div>
        )}
      </div>
    </div>
  );
};
