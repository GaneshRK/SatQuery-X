"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Mail, Phone, MapPin, Send, CheckCircle2, ShieldCheck } from "lucide-react";
import PublicNavbar from "../../components/PublicNavbar";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";

export default function ContactPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => {
      setSent(true);
      setLoading(false);
    }, 600);
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#040911] text-[#eef6f8]">
      <PublicNavbar />

      <main className="flex-1 max-w-6xl mx-auto px-6 py-16 w-full">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-12 items-start">
          {/* Left Column: Direct Info */}
          <div className="md:col-span-5 space-y-6">
            <div>
              <span className="eyebrow">ENTERPRISE INQUIRIES & SUPPORT</span>
              <h1 className="text-3xl sm:text-4xl font-extrabold text-white mt-1 mb-3">
                Connect with the Earth Intelligence Team
              </h1>
              <p className="text-sm text-slate-300 leading-relaxed">
                Have questions regarding custom Copernicus constellation ingestion, high-resolution
                commercial satellite tasking, or on-premise deployment? Contact our remote sensing
                engineering team.
              </p>
            </div>

            <div className="space-y-4 pt-2 text-xs">
              <div className="flex items-center gap-3 p-3.5 rounded-xl bg-[#081420] border border-[#153245]">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center shrink-0">
                  <Mail size={16} />
                </div>
                <div>
                  <div className="text-slate-400 text-[10px] uppercase font-mono">Operations Email</div>
                  <div className="font-semibold text-white">support@satquery.ai</div>
                </div>
              </div>

              <div className="flex items-center gap-3 p-3.5 rounded-xl bg-[#081420] border border-[#153245]">
                <div className="w-8 h-8 rounded-lg bg-cyan-500/10 text-cyan-400 flex items-center justify-center shrink-0">
                  <Phone size={16} />
                </div>
                <div>
                  <div className="text-slate-400 text-[10px] uppercase font-mono">Direct Line</div>
                  <div className="font-semibold text-white">+91 98765 43210</div>
                </div>
              </div>

              <div className="flex items-center gap-3 p-3.5 rounded-xl bg-[#081420] border border-[#153245]">
                <div className="w-8 h-8 rounded-lg bg-indigo-500/10 text-indigo-400 flex items-center justify-center shrink-0">
                  <MapPin size={16} />
                </div>
                <div>
                  <div className="text-slate-400 text-[10px] uppercase font-mono">Engineering Hub</div>
                  <div className="font-semibold text-white">Coimbatore, Tamil Nadu, India</div>
                </div>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 text-xs text-slate-400 space-y-2">
              <div className="flex items-center gap-2 text-emerald-400 font-semibold">
                <ShieldCheck size={16} />
                <span>Encrypted Transmission</span>
              </div>
              <p className="text-[11px] leading-relaxed">
                All communications and tasking coordinates are handled under enterprise non-disclosure
                and strict data sovereignty standards.
              </p>
            </div>
          </div>

          {/* Right Column: Contact Form */}
          <div className="md:col-span-7">
            <Card className="p-8 space-y-6">
              <div>
                <h3 className="text-lg font-bold text-white mb-1">Dispatch Direct Inquiry</h3>
                <p className="text-xs text-slate-400">
                  Fill in your mission specifications and an analyst will respond within 4 business hours.
                </p>
              </div>

              {sent ? (
                <div className="p-6 rounded-xl bg-emerald-950/30 border border-emerald-500/30 text-center space-y-3">
                  <div className="w-12 h-12 rounded-full bg-emerald-500/10 text-emerald-400 flex items-center justify-center mx-auto">
                    <CheckCircle2 size={24} />
                  </div>
                  <h4 className="text-sm font-bold text-white">Message Successfully Transmitted</h4>
                  <p className="text-xs text-slate-300">
                    Thank you! Our engineering team has received your inquiry and will follow up shortly.
                  </p>
                  <Button variant="outline" size="sm" onClick={() => setSent(false)}>
                    Send Another Message
                  </Button>
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Analyst / Representative Name
                    </label>
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="e.g. Dr. Maya Raman"
                      required
                      className="w-full px-3.5 py-2.5 rounded-lg bg-[#0d1f2e] border border-[#153245] text-white text-xs focus:outline-none focus:border-emerald-400 transition-colors"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Official Email Address
                    </label>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="maya@organization.org"
                      required
                      className="w-full px-3.5 py-2.5 rounded-lg bg-[#0d1f2e] border border-[#153245] text-white text-xs focus:outline-none focus:border-emerald-400 transition-colors"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      Mission Inquiry / Dataset Requirements
                    </label>
                    <textarea
                      value={message}
                      onChange={(e) => setMessage(e.target.value)}
                      placeholder="Specify your target AOI, sensor modalities, or analytics integration requirements..."
                      rows={4}
                      required
                      className="w-full px-3.5 py-2.5 rounded-lg bg-[#0d1f2e] border border-[#153245] text-white text-xs focus:outline-none focus:border-emerald-400 transition-colors"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full py-3 rounded-lg bg-emerald-400 hover:bg-emerald-300 text-slate-950 font-bold text-sm shadow-lg shadow-emerald-500/20 transition-all active:scale-98 disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {loading ? (
                      <span>Transmitting...</span>
                    ) : (
                      <>
                        <span>Submit Inquiry</span>
                        <Send size={14} />
                      </>
                    )}
                  </button>
                </form>
              )}
            </Card>
          </div>
        </div>
      </main>

      <footer className="mt-auto border-t border-slate-800/80 py-6 text-center text-xs text-slate-500 font-mono">
        SatQuery AI — Planetary Remote Sensing Intelligence Workstation (SIH 26167)
      </footer>
    </div>
  );
}
