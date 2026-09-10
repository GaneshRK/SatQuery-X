"use client";

import React, { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";

export default function MapPanel({
  height = 430,
  center = [0, 0],
  zoom = 10,
  label = "",
}: {
  height?: number;
  center?: [number, number];
  zoom?: number;
  label?: string;
}) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!mapContainer.current || mapInstance.current) return;

    try {
      const map = new maplibregl.Map({
        container: mapContainer.current,
        style: {
          version: 8,
          sources: {
            osm: {
              type: "raster",
              tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
              tileSize: 256,
              attribution: "&copy; OpenStreetMap contributors",
            },
          },
          layers: [
            {
              id: "osm-layer",
              type: "raster",
              source: "osm",
              minzoom: 0,
              maxzoom: 19,
            },
          ],
        },
        center: center,
        zoom: zoom,
        attributionControl: false,
      });

      // Add AOI marker
      new maplibregl.Marker({ color: "#2ee79b" })
        .setLngLat(center)
        .setPopup(new maplibregl.Popup().setHTML(`<b style="color:#000;">${label}</b>`))
        .addTo(map);

      mapInstance.current = map;
    } catch (e) {
      console.warn("Map initialization:", e);
    }

    return () => {
      mapInstance.current?.remove();
      mapInstance.current = null;
    };
  }, [center, zoom, label]);

  return (
    <div className="map-wrap" style={{ height }}>
      <div ref={mapContainer} style={{ width: "100%", height: "100%" }} />
      <div className="map-overlay-label">📍 {label}</div>
    </div>
  );
}
