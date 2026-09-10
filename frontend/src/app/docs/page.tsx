"use client";

import React from "react";
import Link from "next/link";
import {
  CheckCircle2,
  ArrowRight,
  BookOpen,
  Layers,
  Cpu,
  ShieldCheck,
  Code2,
  Compass,
} from "lucide-react";
import PublicNavbar from "../../components/PublicNavbar";
import { Card } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";

export default function DocumentationPage() {
  const steps = [
    {
      step: 1,
      title: "Define Target AOI & Ingestion",
      desc: "Search geolocations, select preset bounding boxes (e.g. Coimbatore, Chennai), or upload GeoTIFF / PNG rasters.",
    },
    {
      step: 2,
      title: "Select Multimodal Sensor Modality",
      desc: "Choose between Single Image RS-VQA, Cross-Modal Optical + SAR fusion, or Bi-Temporal ChangeFormer pairing.",
    },
    {
      step: 3,
      title: "Submit Natural Language Query",
      desc: "Pose specific analytical questions like 'What is changing around Coimbatore over time?' or 'Visualize heat coordinates'.",
    },
    {
      step: 4,
      title: "Autonomous Agent Orchestration",
      desc: "Agentic pipeline classifies intent, resolves spatial bounds, downloads Copernicus imagery, and runs computer vision inference.",
    },
    {
      step: 5,
      title: "Inspect Verifiable Proof Chain",
      desc: "Inspect pixel-level derivation from measured backend evidence, coordinate reference systems, and downloadable GeoTIFF masks.",
    },
  ];

  const modalities = [
    {
      title: "Mode 1: Single Image RS-VQA",
      desc: "Visual Question Answering and feature grounding over a single high-resolution optical scene.",
      tag: "Optical Only",
    },
    {
      title: "Mode 2: Optical + SAR Fusion",
      desc: "Cross-modal alignment of Sentinel-2 multispectral reflectance with Sentinel-1 C-Band synthetic aperture radar.",
      tag: "All-Weather",
    },
    {
      title: "Mode 3: Bi-Temporal Change Detection",
      desc: "ChangeFormer Siamese transformer comparing baseline T1 and observation T2 for physical land surface evolution.",
      tag: "Bi-Temporal",
    },
    {
      title: "Mode 4: Change-Based VQA",
      desc: "Conversational reasoning answering complex spatial questions based specifically on changed vector regions.",
      tag: "Reasoning",
    },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-[#040911] text-[#eef6f8]">
      <PublicNavbar />

      <main className="flex-1 max-w-6xl mx-auto px-6 py-16 w-full space-y-16">
        <div>
          <span className="eyebrow">TECHNICAL SPECIFICATIONS & USER GUIDE</span>
          <h1 className="text-3xl sm:text-5xl font-extrabold text-white mt-2 mb-3">
            SatQuery AI Documentation
          </h1>
          <p className="text-sm sm:text-base text-slate-300 max-w-2xl leading-relaxed">
            Architectural reference, multimodal sensor ingestion guide, and deterministic evidence
            derivation standards for SIH Problem Statement 26167.
          </p>
        </div>

        {/* 5-Step Process */}
        <section className="space-y-6">
          <div className="flex items-center gap-2 text-emerald-400 font-bold text-sm tracking-wider uppercase">
            <BookOpen size={16} />
            <span>Operational Workflow</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            {steps.map((st) => (
              <div
                key={st.step}
                className="p-5 rounded-xl bg-[#081420] border border-[#153245] flex flex-col justify-between space-y-3"
              >
                <div className="w-8 h-8 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-mono font-bold text-xs flex items-center justify-center">
                  0{st.step}
                </div>
                <div>
                  <h3 className="text-xs font-bold text-white mb-1.5">{st.title}</h3>
                  <p className="text-[11px] text-slate-400 leading-relaxed">{st.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 4 Sensor Modalities */}
        <section className="space-y-6 border-t border-slate-800/80 pt-12">
          <div className="flex items-center gap-2 text-cyan-400 font-bold text-sm tracking-wider uppercase">
            <Layers size={16} />
            <span>Supported Input Modalities</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {modalities.map((m, i) => (
              <Card key={i} className="p-5 space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-bold text-white">{m.title}</h4>
                  <Badge variant="cyan" size="sm">{m.tag}</Badge>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">{m.desc}</p>
              </Card>
            ))}
          </div>
        </section>

        {/* API Contract Reference */}
        <section className="space-y-6 border-t border-slate-800/80 pt-12">
          <div className="flex items-center gap-2 text-indigo-400 font-bold text-sm tracking-wider uppercase">
            <Code2 size={16} />
            <span>REST API Execution Contract</span>
          </div>

          <Card className="p-5 space-y-3 bg-[#06111a]">
            <div className="text-xs text-slate-400">
              The Django REST API at <code className="text-cyan-300 font-mono">/api/analysis/query/</code> accepts
              both JSON and multipart form data payloads.
            </div>
            <pre className="p-4 rounded-lg bg-black/70 font-mono text-[11px] text-slate-300 overflow-x-auto">
{`POST /api/analysis/query/ HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{
  "query": "What is changing around Coimbatore over time?",
  "location": "Coimbatore, Tamil Nadu",
  "source": "sentinel-2",
  "start_date": "2024-03-01",
  "end_date": "2026-09-01"
}`}
            </pre>
          </Card>
        </section>

        {/* Bottom CTA */}
        <div className="text-center pt-4">
          <Link
            href="/assistant"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-emerald-400 hover:bg-emerald-300 text-slate-950 font-bold text-sm shadow-xl shadow-emerald-500/20 transition-all"
          >
            <span>Launch SatQuery AI Workstation</span>
            <ArrowRight size={15} />
          </Link>
        </div>
      </main>

      <footer className="mt-auto border-t border-slate-800/80 py-6 text-center text-xs text-slate-500 font-mono">
        SatQuery AI — Planetary Remote Sensing Intelligence Workstation (SIH 26167)
      </footer>
    </div>
  );
}
