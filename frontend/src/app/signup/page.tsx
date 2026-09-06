"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../../context/AuthContext";
import { Eye, EyeOff, Satellite, ShieldCheck, ArrowRight } from "lucide-react";
import PublicNavbar from "../../components/PublicNavbar";

export default function SignupPage() {
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [showPassword, setShowPassword] = useState(false);
  const [msg, setMsg] = useState("");
  const [isError, setIsError] = useState(false);
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const router = useRouter();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMsg("");
    setIsError(false);
    setLoading(true);
    try {
      await register(form);
      setMsg("Account created successfully. Initialising mission workspace...");
      setTimeout(() => router.push("/dashboard"), 800);
    } catch (err: any) {
      setIsError(true);
      setMsg(
        err.response?.data?.detail ||
          err.response?.data?.error ||
          "Registration failed. Please check your credentials."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-[#040911] text-[#eef6f8]">
      <PublicNavbar />

      <div className="flex-1 auth-page">
        {/* Left Side: Planetary Observational Artwork */}
        <div
          className="auth-image relative flex flex-col justify-end p-12 bg-cover bg-center"
          style={{
            backgroundImage: `linear-gradient(180deg, rgba(4, 9, 17, 0.3) 0%, rgba(4, 9, 17, 0.95) 100%), url('https://images.unsplash.com/photo-1446776811953-b23d57bd21aa?auto=format&fit=crop&w=1200&q=80')`,
          }}
        >
          <div className="relative z-10 space-y-4">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 text-xs font-mono">
              <ShieldCheck size={13} />
              <span>Multi-Spectral Foundation Pipeline</span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-bold text-white leading-snug">
              "Transform high-dimensional satellite rasters into actionable planetary intelligence."
            </h2>
            <p className="text-xs text-slate-400 font-mono">
              SIH Problem Statement 26167 • SatQuery AI
            </p>
          </div>
        </div>

        {/* Right Side: Signup Form */}
        <div className="flex items-center justify-center p-6 sm:p-12">
          <div className="auth-card w-full max-w-md">
            <div className="auth-head flex items-center gap-2.5 mb-6">
              <span className="brand-mark">
                <Satellite size={18} />
              </span>
              <span className="font-bold text-lg text-white">
                SatQuery <b>AI</b>
              </span>
            </div>

            <h1 className="text-2xl font-extrabold text-white mb-1.5">Create Analyst Seat</h1>
            <p className="text-xs text-slate-400 mb-6">
              Register for an individual or enterprise seat to run remote sensing reasoning pipelines.
            </p>

            <form onSubmit={submit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Full Name
                </label>
                <input
                  value={form.full_name}
                  onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                  placeholder="e.g. Dr. Rajesh Sundaram"
                  required
                  className="w-full px-3.5 py-2.5 rounded-lg bg-[#0d1f2e] border border-[#153245] text-white text-sm focus:outline-none focus:border-emerald-400 transition-colors"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Official Email Address
                </label>
                <input
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  type="email"
                  placeholder="rajesh@isro.gov.in"
                  required
                  className="w-full px-3.5 py-2.5 rounded-lg bg-[#0d1f2e] border border-[#153245] text-white text-sm focus:outline-none focus:border-emerald-400 transition-colors"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Password (min 8 characters)
                </label>
                <div className="relative">
                  <input
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    type={showPassword ? "text" : "password"}
                    placeholder="••••••••••••"
                    required
                    minLength={8}
                    className="w-full px-3.5 py-2.5 pr-10 rounded-lg bg-[#0d1f2e] border border-[#153245] text-white text-sm focus:outline-none focus:border-emerald-400 transition-colors"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              {msg && (
                <div
                  className={`p-3 rounded-lg text-xs ${
                    isError
                      ? "bg-red-950/40 border border-red-500/30 text-red-300"
                      : "bg-emerald-950/40 border border-emerald-500/30 text-emerald-300"
                  }`}
                >
                  {msg}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 rounded-lg bg-emerald-400 hover:bg-emerald-300 text-slate-950 font-bold text-sm shadow-lg shadow-emerald-500/20 transition-all active:scale-98 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {loading ? (
                  <span>Registering Account...</span>
                ) : (
                  <>
                    <span>Create Free Mission Account</span>
                    <ArrowRight size={15} />
                  </>
                )}
              </button>

              <p className="text-center text-xs text-slate-400 pt-2">
                Already registered?{" "}
                <Link href="/login" className="text-emerald-400 font-semibold hover:underline">
                  Sign In
                </Link>
              </p>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
