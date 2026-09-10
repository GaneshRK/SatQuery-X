"use client";

import React from "react";
import Link from "next/link";
import {
  Satellite,
  Bot,
  Map,
  ScanSearch,
  GitCompare,
  ArrowRight,
  ShieldCheck,
  Activity,
  Layers,
  Sparkles,
  Flame,
  Globe2,
  CheckCircle2,
  Compass,
} from "lucide-react";
import PublicNavbar from "../components/PublicNavbar";

export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col bg-[#040911] text-[#eef6f8]">
      <PublicNavbar />

      {/* Hero Section */}
      <section className="relative overflow-hidden pt-12 pb-24 px-6 sm:px-12 max-w-7xl mx-auto w-full">
        <div className="earth-orbit-visual" aria-hidden="true" />
        {/* Subtle Background Glow */}
        <div className="absolute top-10 left-1/2 -translate-x-1/2 w-[700px] h-[350px] bg-emerald-500/10 rounded-full blur-3xl pointer-events-none -z-10" />

        <div className="flex flex-col items-center text-center max-w-4xl mx-auto space-y-6">
          {/* Status Badge */}
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-slate-900/90 border border-slate-700/60 shadow-lg text-xs font-mono text-emerald-400">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>Copernicus Sentinel-1/2 analysis pipeline</span>
            <span className="text-slate-500 font-sans">|</span>
            <span className="text-slate-300">SIH 26167</span>
          </div>

          <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight leading-[1.1] text-white">
            From satellite pixels to <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 via-emerald-300 to-teal-200">
              defensible Earth intelligence
            </span>
          </h1>

          <p className="text-base sm:text-lg text-slate-400 max-w-2xl leading-relaxed">
            Ask a natural-language question, inspect the processing chain, compare observations, and see why the
            final outcome is trustworthy. SatQuery turns satellite observations into measurable, auditable evidence.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-4 pt-4">
            <Link
              href="/assistant"
              className="inline-flex items-center gap-2.5 px-6 py-3.5 rounded-lg bg-emerald-400 hover:bg-emerald-300 text-slate-950 font-bold text-sm shadow-xl shadow-emerald-500/20 transition-all hover:scale-105 active:scale-95"
            >
              <Bot className="w-4 h-4" />
              <span>Launch AI Workstation</span>
              <ArrowRight className="w-4 h-4" />
            </Link>

            <Link
              href="/explore"
              className="inline-flex items-center gap-2 px-5 py-3.5 rounded-lg bg-slate-900/80 hover:bg-slate-800 text-slate-200 border border-slate-700 font-semibold text-sm transition-all hover:border-cyan-500/50"
            >
              <Map className="w-4 h-4 text-cyan-400" />
              <span>Explore Satellite Map</span>
            </Link>

            <Link
              href="/compare"
              className="inline-flex items-center gap-2 px-5 py-3.5 rounded-lg bg-slate-900/80 hover:bg-slate-800 text-slate-200 border border-slate-700 font-semibold text-sm transition-all hover:border-emerald-500/50"
            >
              <GitCompare className="w-4 h-4 text-emerald-400" />
              <span>Siamese Comparison</span>
            </Link>
          </div>
        </div>

        {/* Judge-facing validation strip */}
        <div className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-4 relative">
          <div className="p-5 rounded-2xl bg-white/[.035] border border-cyan-200/10 backdrop-blur-xl">
            <div className="eyebrow">01 · Process</div>
            <div className="text-sm font-semibold text-white mt-2">Every stage is visible</div>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">Query interpretation → satellite retrieval → temporal alignment → model inference → evidence generation.</p>
          </div>
          <div className="p-5 rounded-2xl bg-white/[.035] border border-cyan-200/10 backdrop-blur-xl">
            <div className="eyebrow">02 · Outcome</div>
            <div className="text-sm font-semibold text-white mt-2">Quantified, not just narrated</div>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">Changed pixels, area, hotspots, coordinates and source observations stay attached to the answer.</p>
          </div>
          <div className="p-5 rounded-2xl bg-white/[.035] border border-cyan-200/10 backdrop-blur-xl">
            <div className="eyebrow">03 · Correctness</div>
            <div className="text-sm font-semibold text-white mt-2">Confidence ≠ accuracy</div>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">The UI reports evidence quality separately and reserves accuracy claims for ground-truth evaluation.</p>
          </div>
        </div>

        {/* Live Demonstration Scenarios */}
        <div className="mt-20">
          <div className="text-center mb-8">
            <span className="text-[11px] font-mono tracking-widest text-emerald-400 uppercase font-semibold">
              Mission Scenarios
            </span>
            <h2 className="text-2xl font-bold text-white mt-1">Operational Intelligence Workflows</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Card 1: Change Detection */}
            <div className="p-6 rounded-xl bg-[#081420] border border-[#153245] hover:border-emerald-500/50 transition-all group flex flex-col justify-between">
              <div>
                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 mb-4">
                  <ScanSearch className="w-5 h-5" />
                </div>
                <div className="text-xs font-mono text-emerald-400 uppercase tracking-wider mb-1">
                  Bi-Temporal Siamese Analysis
                </div>
                <h3 className="text-lg font-bold text-white mb-2">
                  Coimbatore Multi-Year Change Detection
                </h3>
                <p className="text-xs text-slate-400 leading-relaxed mb-4">
                  Autonomous ChangeFormer paired inference between baseline T1 and comparison T2
                  Sentinel-2 scenes. Quantifies changed land-cover area with exact pixel mathematics.
                </p>
              </div>
              <Link
                href="/assistant?q=What%20is%20changing%20around%20Coimbatore%20over%20time%3F&loc=Coimbatore%2C%20Tamil%20Nadu"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-400 hover:text-emerald-300 group-hover:translate-x-1 transition-all"
              >
                <span>Run Scenario</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {/* Card 2: Thermal Hotspots */}
            <div className="p-6 rounded-xl bg-[#081420] border border-[#153245] hover:border-amber-500/50 transition-all group flex flex-col justify-between">
              <div>
                <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 mb-4">
                  <Flame className="w-5 h-5" />
                </div>
                <div className="text-xs font-mono text-amber-400 uppercase tracking-wider mb-1">
                  Thermal Cluster Detection
                </div>
                <h3 className="text-lg font-bold text-white mb-2">
                  SWIR / VNIR Heat Coordinate Clusters
                </h3>
                <p className="text-xs text-slate-400 leading-relaxed mb-4">
                  Spectral index clustering for industrial emissions and burn scars. Extracts top 3
                  dense centroid coordinates with sensor reality grounding.
                </p>
              </div>
              <Link
                href="/assistant?q=visualize%20the%20heat%20coordinates&loc=Coimbatore%2C%20Tamil%20Nadu"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-amber-400 hover:text-amber-300 group-hover:translate-x-1 transition-all"
              >
                <span>Run Scenario</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {/* Card 3: Urban Sprawl & Coast */}
            <div className="p-6 rounded-xl bg-[#081420] border border-[#153245] hover:border-cyan-500/50 transition-all group flex flex-col justify-between">
              <div>
                <div className="w-10 h-10 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 mb-4">
                  <Globe2 className="w-5 h-5" />
                </div>
                <div className="text-xs font-mono text-cyan-400 uppercase tracking-wider mb-1">
                  Regional Comparison
                </div>
                <h3 className="text-lg font-bold text-white mb-2">
                  Chennai Metropolitan vs Thoothukudi
                </h3>
                <p className="text-xs text-slate-400 leading-relaxed mb-4">
                  Cross-regional environmental disparity queries comparing urban density, wetland
                  encroachment, and coastal salt-pan activity.
                </p>
              </div>
              <Link
                href="/assistant?q=How%20does%20Thoothukudi%20differ%20from%20Chennai%3F&loc=Chennai%20Metropolitan%2C%20Tamil%20Nadu"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-cyan-400 hover:text-cyan-300 group-hover:translate-x-1 transition-all"
              >
                <span>Run Scenario</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>
        </div>

        {/* Feature Grid */}
        <div className="mt-24 border-t border-slate-800/80 pt-16">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="p-5 rounded-lg bg-[#06111a] border border-[#153245]">
              <ShieldCheck className="w-6 h-6 text-emerald-400 mb-3" />
              <div className="font-semibold text-sm text-white mb-1">Deterministic Proof Chain</div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Every calculation derived from exact CRS pixel projections with pixel math logs.
              </p>
            </div>

            <div className="p-5 rounded-lg bg-[#06111a] border border-[#153245]">
              <Layers className="w-6 h-6 text-cyan-400 mb-3" />
              <div className="font-semibold text-sm text-white mb-1">Multimodal Fusion</div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Joint reasoning over optical multispectral (10m) and Sentinel-1 SAR backscatter.
              </p>
            </div>

            <div className="p-5 rounded-lg bg-[#06111a] border border-[#153245]">
              <Activity className="w-6 h-6 text-indigo-400 mb-3" />
              <div className="font-semibold text-sm text-white mb-1">Auditable Action Trace</div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Step-by-step observable pipeline stages tracking query resolution and model inference.
              </p>
            </div>

            <div className="p-5 rounded-lg bg-[#06111a] border border-[#153245]">
              <Compass className="w-6 h-6 text-teal-400 mb-3" />
              <div className="font-semibold text-sm text-white mb-1">STAC & OGC Compliant</div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Direct export to GeoJSON vector polygons and Cloud-Optimized GeoTIFF rasters.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="mt-auto border-t border-slate-800/80 py-8 px-6 text-center text-xs text-slate-500 font-mono">
        <div>SatQuery AI — Planetary Remote Sensing Intelligence Workstation (SIH 26167)</div>
        <div className="mt-2 flex items-center justify-center gap-6">
          <Link href="/docs" className="hover:text-slate-300">Documentation</Link>
          <Link href="/about" className="hover:text-slate-300">Mission</Link>
          <Link href="/contact" className="hover:text-slate-300">Support</Link>
          <Link href="/dashboard" className="hover:text-slate-300">Dashboard</Link>
        </div>
      </footer>
    </div>
  );
}
