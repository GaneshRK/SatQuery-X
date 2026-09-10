"use client";

import React from "react";
import {
  MapPin,
  Maximize2,
  Sparkles,
  Download,
  Calendar,
  Layers,
  Info,
  Compass,
  ShieldCheck,
} from "lucide-react";
import { Drawer } from "../ui/Drawer";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";

export interface RegionInsightData {
  cluster_id: string;
  name?: string;
  coords_str?: string;
  centroid_lat?: number;
  centroid_lng?: number;
  area_km2?: number;
  intensity?: string;
  density_score?: number;
  dominant_transition?: string;
  source?: string;
}

export interface RegionInsightDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  region: RegionInsightData | null;
  onAskAIAboutRegion: (region: RegionInsightData) => void;
  onZoomToRegion?: (region: RegionInsightData) => void;
  onDeepInspect?: (region: RegionInsightData) => void;
}

export const RegionInsightDrawer: React.FC<RegionInsightDrawerProps> = ({
  isOpen,
  onClose,
  region,
  onAskAIAboutRegion,
  onZoomToRegion,
  onDeepInspect,
}) => {
  if (!region) return null;

  const handleExportRegionGeoJSON = () => {
    const lat = region.centroid_lat || 11.0758;
    const lng = region.centroid_lng || 76.9574;
    const delta = 0.015;

    const feature = {
      type: "FeatureCollection",
      properties: {
        cluster_id: region.cluster_id,
        area_km2: region.area_km2,
        dominant_transition: region.dominant_transition,
        source: region.source || "Copernicus Sentinel-2 MSI",
      },
      features: [
        {
          type: "Feature",
          properties: {
            cluster_id: region.cluster_id,
            intensity: region.intensity,
            density_score: region.density_score,
          },
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [lng - delta, lat - delta],
                [lng + delta, lat - delta],
                [lng + delta, lat + delta],
                [lng - delta, lat + delta],
                [lng - delta, lat - delta],
              ],
            ],
          },
        },
      ],
    };

    const blob = new Blob([JSON.stringify(feature, null, 2)], { type: "application/geo+json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${region.cluster_id}_footprint.geojson`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      title={`Region Insight: ${region.cluster_id}`}
      subtitle={region.name || "Delineated Satellite Alteration Cluster"}
    >
      <div className="space-y-4 text-xs text-slate-300">
        {/* Top Badges */}
        <div className="flex items-center gap-2">
          <Badge variant="warning" size="md">
            Intensity: {region.intensity || "High"}
          </Badge>
          <Badge variant="satellite" size="md">
            {region.source || "Sentinel-2 10m GSD"}
          </Badge>
        </div>

        {/* Primary Stats Grid */}
        <div className="grid grid-cols-2 gap-2 p-3 rounded-xl bg-slate-950/70 border border-slate-800">
          <div>
            <span className="text-[10px] text-slate-500 font-semibold uppercase block">
              Spatial Extent
            </span>
            <span className="text-lg font-bold text-slate-100 font-mono">
              {region.area_km2 || 0} km²
            </span>
            <span className="text-[10px] text-slate-400 block">
              ≈ {((region.area_km2 || 0) * 100).toFixed(1)} hectares
            </span>
          </div>

          <div>
            <span className="text-[10px] text-slate-500 font-semibold uppercase block">
              Density Score
            </span>
            <span className="text-lg font-bold text-cyan-400 font-mono">
              {region.density_score ? (region.density_score * 100).toFixed(0) : "94"}%
            </span>
            <span className="text-[10px] text-slate-400 block">DBSCAN Coherence</span>
          </div>
        </div>

        {/* Geographic Centroid */}
        <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800">
          <span className="text-[10px] text-slate-500 font-semibold uppercase block mb-1">
            Geographic Centroid (WGS-84)
          </span>
          <div className="flex items-center justify-between font-mono text-slate-200">
            <span className="text-cyan-300">{region.coords_str || "11.0758°N, 76.9574°E"}</span>
            {onZoomToRegion && (
              <Button
                variant="outline"
                size="sm"
                leftIcon={<Maximize2 className="w-3 h-3" />}
                onClick={() => onZoomToRegion(region)}
              >
                Zoom
              </Button>
            )}
          </div>
        </div>

        {/* Dominant Transition */}
        {region.dominant_transition && (
          <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800">
            <span className="text-[10px] text-slate-500 font-semibold uppercase block mb-1">
              Dominant Physical Transition
            </span>
            <p className="text-slate-200 leading-relaxed font-medium">
              {region.dominant_transition}
            </p>
          </div>
        )}

        {/* Actions */}
        <div className="pt-2 space-y-2">
          {onDeepInspect && (
            <Button
              variant="outline"
              size="md"
              className="w-full justify-center text-xs border-cyan-700/60 text-cyan-300 hover:bg-cyan-950/40"
              leftIcon={<ShieldCheck className="w-4 h-4 text-cyan-400" />}
              onClick={() => onDeepInspect(region)}
            >
              Inspect Ground Truth & Sensors
            </Button>
          )}

          <Button
            variant="primary"
            size="md"
            className="w-full justify-center font-semibold"
            leftIcon={<Sparkles className="w-4 h-4" />}
            onClick={() => {
              onAskAIAboutRegion(region);
              onClose();
            }}
          >
            Ask AI: Why did this change?
          </Button>

          <Button
            variant="outline"
            size="md"
            className="w-full justify-center text-xs"
            leftIcon={<Download className="w-4 h-4" />}
            onClick={handleExportRegionGeoJSON}
          >
            Export Region GeoJSON
          </Button>
        </div>
      </div>
    </Drawer>
  );
};
