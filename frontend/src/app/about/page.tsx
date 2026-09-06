"use client";

import React from "react";
import Link from "next/link";
import { Globe2, Users, Sprout, ShieldCheck, Satellite, ArrowRight } from "lucide-react";
import PublicNavbar from "../../components/PublicNavbar";

export default function AboutPage() {
  return (
    <div className="min-h-screen flex flex-col bg-[#040911] text-[#eef6f8]">
      <PublicNavbar />

      <main className="flex-1 max-w-6xl mx-auto px-6 py-16 w-full space-y-16">
        <div className="about-hero">
          <div className="space-y-4">
            <span className="eyebrow">ABOUT SATQUERY AI</span>
            <h1 className="text-4xl sm:text-5xl font-extrabold text-white leading-[1.1]">
              Calibrated Earth Data. <br />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-400">
                Verifiable Decisions.
              </span>
            </h1>
            <p className="text-slate-300 text-sm sm:text-base leading-relaxed">
              SatQuery AI is an autonomous, multi-agent geospatial intelligence engine designed to make
              complex satellite image reasoning accessible through natural language. By uniting
              Copernicus Earth observation data, vision-language foundation models, and deterministic
              geodesic verification, SatQuery delivers actionable planetary intelligence with zero
              hallucination.
            </p>
            <div className="pt-2">
              <Link
                href="/assistant"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-emerald-400 hover:bg-emerald-300 text-slate-950 font-bold text-xs transition-all"
              >
                <span>Explore the AI Workstation</span>
                <ArrowRight size={14} />
              </Link>
            </div>
          </div>

          <div className="relative rounded-2xl overflow-hidden border border-[#153245] shadow-2xl">
            <img
              src="https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1000&q=80"
              alt="Earth from Space"
              className="w-full h-80 sm:h-96 object-cover"
            />
          </div>
        </div>

        {/* Mission Section */}
        <section className="mission border-t border-slate-800/80 pt-16">
          <span className="eyebrow">CORE PRINCIPLES</span>
          <h2 className="text-3xl font-bold text-white mt-1 mb-2">Our Mission & Responsibility</h2>
          <p className="text-slate-400 text-sm max-w-xl mx-auto">
            Leveraging autonomous AI and Copernicus remote sensing data for climate resilience,
            responsible planning, and transparent ecological accountability.
          </p>

          <div className="mission-grid mt-10">
            <div className="p-8 rounded-xl bg-[#081420] border border-[#153245] text-center space-y-3">
              <div className="w-12 h-12 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 flex items-center justify-center mx-auto">
                <Users size={24} />
              </div>
              <h3 className="font-bold text-base text-white">Accessible Science</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Make complex satellite multispectral bands intuitive and interrogable by city planners,
                environmental agencies, and researchers alike.
              </p>
            </div>

            <div className="p-8 rounded-xl bg-[#081420] border border-[#153245] text-center space-y-3">
              <div className="w-12 h-12 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center justify-center mx-auto">
                <Globe2 size={24} />
              </div>
              <h3 className="font-bold text-base text-white">Zero Hallucination</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Transform high-dimensional pixels into physically verified, deterministic numbers with
                transparent pixel mathematics and audit logs.
              </p>
            </div>

            <div className="p-8 rounded-xl bg-[#081420] border border-[#153245] text-center space-y-3">
              <div className="w-12 h-12 rounded-lg bg-teal-500/10 border border-teal-500/30 text-teal-400 flex items-center justify-center mx-auto">
                <Sprout size={24} />
              </div>
              <h3 className="font-bold text-base text-white">Planetary Impact</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Empower proactive disaster response, coastal erosion tracking, and precision agriculture
                with reliable bi-temporal evidence.
              </p>
            </div>
          </div>
        </section>
      </main>

      <footer className="mt-auto border-t border-slate-800/80 py-6 text-center text-xs text-slate-500 font-mono">
        SatQuery AI — Planetary Remote Sensing Intelligence Workstation (SIH 26167)
      </footer>
    </div>
  );
}
