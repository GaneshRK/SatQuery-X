"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  Bot,
  Layers,
  MapPin,
  Calendar,
  Satellite,
  Compass,
  Sparkles,
  ArrowRight,
  Filter,
  CheckCircle2,
} from "lucide-react";
import AppShell from "../../components/AppShell";
import SectionTitle from "../../components/SectionTitle";
import { UnifiedSatelliteMap } from "../../components/map/UnifiedSatelliteMap";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";

interface LocationPreset {
  name: string;
  coords: [number, number];
  bounds: [number, number, number, number];
  description: string;
  recommendedQuery: string;
}

const LOCATION_PRESETS: LocationPreset[] = [
  {
    name: "Coimbatore, Tamil Nadu",
    coords: [76.96, 11.01],
    bounds: [76.85, 10.95, 77.10, 11.15],
    description: "Western Ghats piedmont; rapid industrial & peri-urban sprawl",
    recommendedQuery: "What is changing around Coimbatore over time?",
  },
  {
    name: "Chennai Metropolitan, Tamil Nadu",
    coords: [80.27, 13.08],
    bounds: [80.15, 12.95, 80.35, 13.20],
    description: "Coromandel coastal delta, wetlands & urban expansion",
    recommendedQuery: "What is changing around Chennai?",
  },
  {
    name: "Thoothukudi Coast, Tamil Nadu",
    coords: [78.13, 8.76],
    bounds: [78.05, 8.65, 78.25, 8.85],
    description: "Gulf of Mannar industrial port, salt pans & thermal zone",
    recommendedQuery: "How does Thoothukudi differ from Chennai?",
  },
  {
    name: "Bengaluru Urban, Karnataka",
    coords: [77.59, 12.97],
    bounds: [77.45, 12.85, 77.75, 13.10],
    description: "Deccan plateau tech hub; lake encroachment & canopy loss",
    recommendedQuery: "Analyze urban growth and water body encroachment in Bengaluru",
  },
  {
    name: "Madurai River Basin, Tamil Nadu",
    coords: [78.12, 9.92],
    bounds: [78.02, 9.82, 78.22, 10.02],
    description: "Vaigai river agrarian basin and historical urban core",
    recommendedQuery: "Evaluate agrarian crop cycles and water availability in Madurai",
  },
];

export default function ExploreMapPage() {
  const router = useRouter();
  const [selectedLoc, setSelectedLoc] = useState<LocationPreset>(LOCATION_PRESETS[0]);
  const [sensor, setSensor] = useState<string>("SENTINEL-2");
  const [searchQuery, setSearchQuery] = useState("");
  const [timeRange, setTimeRange] = useState("2024 - 2026");

  const filteredPresets = LOCATION_PRESETS.filter((p) =>
    p.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleAskAI = (preset: LocationPreset) => {
    router.push(
      `/assistant?q=${encodeURIComponent(preset.recommendedQuery)}&loc=${encodeURIComponent(preset.name)}`
    );
  };

  return (
    <AppShell>
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        <SectionTitle
          title="Earth Explorer"
          subtitle="Browse high-resolution multi-spectral satellite imagery and dispatch AI reasoning over any Area of Interest."
          action={
            <Button
              variant="primary"
              icon={<Bot className="w-4 h-4" />}
              onClick={() => handleAskAI(selectedLoc)}
            >
              Ask AI about {selectedLoc.name.split(",")[0]}
            </Button>
          }
        />

        {/* 2-Column: Map Viewport (68%) & Observation Controls (32%) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-[720px]">
          {/* Map Surface */}
          <div className="lg:col-span-8 h-full rounded-2xl overflow-hidden border border-slate-800 shadow-2xl relative">
            <UnifiedSatelliteMap
              bounds={selectedLoc.bounds}
              center={selectedLoc.coords}
              locationName={selectedLoc.name}
              className="w-full h-full"
            />
          </div>

          {/* Sidebar / Observation Catalog */}
          <div className="lg:col-span-4 h-full flex flex-col gap-4 overflow-y-auto pr-1">
            {/* Quick Location Search */}
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-200">
                <MapPin className="w-4 h-4 text-cyan-400" />
                <span>Select Target AOI</span>
              </div>
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-2.5" />
                <input
                  type="text"
                  placeholder="Search city, region, or coordinates..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                {filteredPresets.map((preset) => {
                  const isSelected = selectedLoc.name === preset.name;
                  return (
                    <button
                      key={preset.name}
                      onClick={() => setSelectedLoc(preset)}
                      className={`w-full text-left p-2.5 rounded-xl border text-xs transition-all flex items-center justify-between ${
                        isSelected
                          ? "bg-cyan-500/10 border-cyan-500/50 text-cyan-200"
                          : "bg-slate-950/40 border-slate-800/80 text-slate-300 hover:bg-slate-900/60"
                      }`}
                    >
                      <div className="space-y-0.5">
                        <div className="font-medium flex items-center gap-1.5">
                          <span>{preset.name}</span>
                          {isSelected && <CheckCircle2 className="w-3 h-3 text-cyan-400" />}
                        </div>
                        <div className="text-[10px] text-slate-500">{preset.description}</div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </Card>

            {/* Satellite Sensor & Constellation */}
            <Card className="p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-200">
                  <Satellite className="w-4 h-4 text-emerald-400" />
                  <span>Constellation Sensor</span>
                </div>
                <Badge variant="cyan" size="sm">Copernicus CDSE</Badge>
              </div>

              <div className="grid grid-cols-2 gap-2">
                {[
                  { id: "SENTINEL-2", name: "Sentinel-2 MSI", desc: "10m Optical RGB/NIR" },
                  { id: "SENTINEL-1", name: "Sentinel-1 SAR", desc: "C-Band All-Weather" },
                  { id: "LANDSAT-8", name: "Landsat-8/9", desc: "30m Multi-Spectral" },
                  { id: "CROSS-MODAL", name: "Optical + SAR", desc: "Fused Sensor Stream" },
                ].map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setSensor(s.id)}
                    className={`p-2 rounded-lg border text-left text-xs transition-colors ${
                      sensor === s.id
                        ? "bg-emerald-500/10 border-emerald-500/50 text-emerald-200"
                        : "bg-slate-950/40 border-slate-800 text-slate-400 hover:border-slate-700"
                    }`}
                  >
                    <div className="font-medium text-[11px]">{s.name}</div>
                    <div className="text-[9px] text-slate-500">{s.desc}</div>
                  </button>
                ))}
              </div>
            </Card>

            {/* AI Agent Handoff Action */}
            <Card className="p-4 space-y-3 bg-gradient-to-br from-slate-900 to-cyan-950/30 border-cyan-500/30">
              <div className="flex items-center gap-2 text-xs font-semibold text-cyan-300">
                <Sparkles className="w-4 h-4 text-cyan-400" />
                <span>Ask AI About This AOI</span>
              </div>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Dispatch an autonomous bi-temporal query over{" "}
                <strong className="text-slate-200">{selectedLoc.name}</strong>.
              </p>

              <div className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800 text-[11px] text-slate-300 font-mono">
                &ldquo;{selectedLoc.recommendedQuery}&rdquo;
              </div>

              <Button
                variant="primary"
                className="w-full"
                icon={<ArrowRight className="w-4 h-4" />}
                onClick={() => handleAskAI(selectedLoc)}
              >
                Execute Query in AI Workstation
              </Button>
            </Card>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
