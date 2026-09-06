"use client";

import React, { useState } from "react";
import AppShell from "../../components/AppShell";
import SectionTitle from "../../components/SectionTitle";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { useAuth } from "../../context/AuthContext";
import {
  User,
  Sliders,
  Satellite,
  Key,
  ShieldCheck,
  CheckCircle2,
  Lock,
  Globe2,
  Terminal,
  Layers,
} from "lucide-react";

export default function SettingsPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState("Account");
  const [fullName, setFullName] = useState(user?.full_name || "Enterprise Lead");
  const [defaultSensor, setDefaultSensor] = useState("Sentinel-2 L2A (10m MSI)");
  const [defaultCRS, setDefaultCRS] = useState("EPSG:4326 (WGS84)");
  const [saved, setSaved] = useState(false);

  const tabs = [
    { id: "Account", label: "Analyst Account", icon: User },
    { id: "Preferences", label: "Sensor Feeds", icon: Satellite },
    { id: "API Keys", label: "API Tokens", icon: Key },
    { id: "Data & Privacy", label: "STAC & Data Governance", icon: ShieldCheck },
  ];

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  return (
    <AppShell>
      <div className="p-6 max-w-5xl mx-auto space-y-6">
        <SectionTitle
          title="Mission Settings & Profile"
          subtitle="Configure analyst authentication, constellation ingestion preferences, and STAC API credentials."
        />

        <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
          {/* Settings Navigation */}
          <div className="md:col-span-4 space-y-1">
            <Card className="p-2 space-y-1">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-xs font-medium transition-all ${
                      isActive
                        ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30"
                        : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60"
                    }`}
                  >
                    <Icon size={15} className={isActive ? "text-cyan-400" : "text-slate-500"} />
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </Card>

            <div className="p-3 text-[11px] text-slate-500 font-mono leading-relaxed">
              Environment: Production Cluster <br />
              Node: cdse-worker-01 (EU Central)
            </div>
          </div>

          {/* Settings Content Panels */}
          <div className="md:col-span-8 space-y-6">
            {activeTab === "Account" && (
              <Card className="p-6 space-y-6">
                <div>
                  <h3 className="text-sm font-bold text-white mb-1">Analyst Profile</h3>
                  <p className="text-xs text-slate-400">
                    Your authenticated credentials for dispatching agentic remote sensing tasks.
                  </p>
                </div>

                <div className="flex items-center gap-4 pb-4 border-b border-slate-800">
                  <div className="w-14 h-14 rounded-full bg-gradient-to-br from-cyan-900 to-emerald-950 border border-cyan-700/50 flex items-center justify-center text-cyan-300 font-bold text-lg">
                    {(user?.full_name || user?.email || "G").slice(0, 1).toUpperCase()}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-white">
                      {user?.full_name || "Enterprise Lead Analyst"}
                    </div>
                    <div className="text-xs text-slate-400 font-mono">
                      {user?.email || "analyst@satquery.ai"}
                    </div>
                    <Badge variant="cyan" size="sm" className="mt-1">
                      ENTERPRISE LICENSE
                    </Badge>
                  </div>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Full Name
                    </label>
                    <input
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      className="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-cyan-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Registered Email
                    </label>
                    <input
                      type="email"
                      value={user?.email || "analyst@satquery.ai"}
                      readOnly
                      className="w-full px-3.5 py-2 rounded-lg bg-slate-900/60 border border-slate-800 text-xs text-slate-400 cursor-not-allowed"
                    />
                  </div>
                </div>

                <div className="pt-4 border-t border-slate-800 flex items-center justify-between">
                  <span className="text-[11px] text-slate-500 font-mono">
                    Session authentication persisted in localStorage
                  </span>
                  <Button variant="primary" size="sm" onClick={handleSave}>
                    {saved ? "Saved ✓" : "Save Changes"}
                  </Button>
                </div>
              </Card>
            )}

            {activeTab === "Preferences" && (
              <Card className="p-6 space-y-6">
                <div>
                  <h3 className="text-sm font-bold text-white mb-1">Default Constellation Ingestion</h3>
                  <p className="text-xs text-slate-400">
                    Configure preferred satellite sources for natural language query execution.
                  </p>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Primary Sensor
                    </label>
                    <select
                      value={defaultSensor}
                      onChange={(e) => setDefaultSensor(e.target.value)}
                      className="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-cyan-500"
                    >
                      <option>Sentinel-2 L2A (10m MSI Optical)</option>
                      <option>Sentinel-1 GRD (C-Band Synthetic Aperture Radar)</option>
                      <option>Landsat 8/9 OLI / TIRS (Multi-Spectral + Thermal)</option>
                      <option>Optical + SAR Fused Stream</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Default Coordinate Reference System (CRS)
                    </label>
                    <select
                      value={defaultCRS}
                      onChange={(e) => setDefaultCRS(e.target.value)}
                      className="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-cyan-500"
                    >
                      <option>EPSG:4326 (WGS84 Geodetic - Native GeoJSON)</option>
                      <option>EPSG:6933 (Equal Area Cylindrical - Exact Area Calculations)</option>
                      <option>EPSG:3857 (Web Mercator - Standard Tile Layer)</option>
                    </select>
                  </div>
                </div>

                <div className="pt-4 border-t border-slate-800 flex items-center justify-between">
                  <span className="text-[11px] text-slate-500 font-mono">
                    Client-side session preferences
                  </span>
                  <Button variant="primary" size="sm" onClick={handleSave}>
                    {saved ? "Saved ✓" : "Update Preferences"}
                  </Button>
                </div>
              </Card>
            )}

            {activeTab === "API Keys" && (
              <Card className="p-6 space-y-6">
                <div>
                  <h3 className="text-sm font-bold text-white mb-1">STAC & Contract API Access</h3>
                  <p className="text-xs text-slate-400">
                    Programmatic access tokens for querying the SatQuery-X Django REST contract.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-200">Active JWT Bearer Token</span>
                    <Badge variant="success" size="sm">VALID</Badge>
                  </div>
                  <div className="p-2.5 rounded bg-slate-900 border border-slate-800 font-mono text-[11px] text-slate-400 truncate">
                    eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.satquery_auth_token_active...
                  </div>
                  <p className="text-[10px] text-slate-500">
                    Use this token in Authorization headers for automated geospatial scripts.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/80 text-xs space-y-2">
                  <div className="font-semibold text-white flex items-center gap-2">
                    <Terminal size={14} className="text-cyan-400" />
                    <span>CLI / Python SDK Access Example:</span>
                  </div>
                  <pre className="p-3 rounded bg-black/60 font-mono text-[11px] text-slate-300 overflow-x-auto">
{`curl -X POST http://localhost:8000/api/analysis/query/ \\
  -H "Authorization: Bearer <TOKEN>" \\
  -H "Content-Type: application/json" \\
  -d '{"query": "What changed in Coimbatore?", "location": "Coimbatore"}'`}
                  </pre>
                </div>
              </Card>
            )}

            {activeTab === "Data & Privacy" && (
              <Card className="p-6 space-y-4">
                <div>
                  <h3 className="text-sm font-bold text-white mb-1">Data Governance & STAC Compliance</h3>
                  <p className="text-xs text-slate-400">
                    All satellite rasters are accessed via OGC-compliant STAC catalogs with strict provenance tracking.
                  </p>
                </div>

                <div className="space-y-3 pt-2 text-xs text-slate-300">
                  <div className="flex items-start gap-3 p-3 rounded-lg bg-slate-950 border border-slate-800">
                    <ShieldCheck size={18} className="text-emerald-400 shrink-0 mt-0.5" />
                    <div>
                      <strong className="text-white block mb-0.5">EU Copernicus Open Access License</strong>
                      <span>All Sentinel observations are retrieved in compliance with EU CDSE policies.</span>
                    </div>
                  </div>

                  <div className="flex items-start gap-3 p-3 rounded-lg bg-slate-950 border border-slate-800">
                    <CheckCircle2 size={18} className="text-cyan-400 shrink-0 mt-0.5" />
                    <div>
                      <strong className="text-white block mb-0.5">Deterministic Reproducibility</strong>
                      <span>Analyses record CRS, band math derivations, and exact pixel counts for auditing.</span>
                    </div>
                  </div>
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
