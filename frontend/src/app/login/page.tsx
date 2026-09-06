"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../../context/AuthContext";
import { Eye, EyeOff, Satellite, ShieldCheck, ArrowRight, Bot } from "lucide-react";
import PublicNavbar from "../../components/PublicNavbar";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const router = useRouter();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (err: any) {
      setError(
        err.response?.data?.detail ||
          err.response?.data?.error ||
          "Unable to sign in. Please verify your credentials."
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
            backgroundImage: `linear-gradient(180deg, rgba(4, 9, 17, 0.3) 0%, rgba(4, 9, 17, 0.95) 100%), url('https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1200&q=80')`,
          }}
        >
          <div className="relative z-10 space-y-4">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 text-xs font-mono">
              <ShieldCheck size={13} />
              <span>Certified Remote Sensing Intelligence</span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-bold text-white leading-snug">
              "Observing Earth's dynamic pulse with calibrated scientific precision."
            </h2>
            <p className="text-xs text-slate-400 font-mono">
              Sentinel-1/2 Constellation • SIH Problem Statement 26167
            </p>
          </div>
        </div>

        {/* Right Side: Authentication Form */}
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

            <h1 className="text-2xl font-extrabold text-white mb-1.5">Welcome Back</h1>
            <p className="text-xs text-slate-400 mb-6">
              Sign in to your mission workspace to access multispectral reasoning and change detection.
            </p>

            <form onSubmit={submit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Analyst Email
                </label>
                <input
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  type="email"
                  placeholder="analyst@satquery.ai"
                  required
                  className="w-full px-3.5 py-2.5 rounded-lg bg-[#0d1f2e] border border-[#153245] text-white text-sm focus:outline-none focus:border-emerald-400 transition-colors"
                />
              </div>

              <div>
                <div className="flex justify-between items-center mb-1.5">
                  <label className="text-xs font-semibold text-slate-300">
                    Security Password
                  </label>
                  <Link
                    href="/forgot-password"
                    className="text-[11px] text-emerald-400 hover:underline"
                  >
                    Forgot Password?
                  </Link>
                </div>
                <div className="relative">
                  <input
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    type={showPassword ? "text" : "password"}
                    placeholder="••••••••••••"
                    required
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

              {error && (
                <div className="p-3 rounded-lg bg-red-950/40 border border-red-500/30 text-red-300 text-xs">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 rounded-lg bg-emerald-400 hover:bg-emerald-300 text-slate-950 font-bold text-sm shadow-lg shadow-emerald-500/20 transition-all active:scale-98 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {loading ? (
                  <span>Authenticating Session...</span>
                ) : (
                  <>
                    <span>Sign In to Workstation</span>
                    <ArrowRight size={15} />
                  </>
                )}
              </button>

              <div className="relative my-4">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-slate-800" />
                </div>
                <div className="relative flex justify-center text-[10px] uppercase font-mono">
                  <span className="bg-[#081420] px-3 text-slate-500">Quick Access</span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => {
                  setEmail("demo@satquery.ai");
                  setPassword("password123");
                }}
                className="w-full py-2.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 text-xs font-semibold transition-colors flex items-center justify-center gap-2"
              >
                <Bot size={14} className="text-cyan-400" />
                <span>Fill Demo Analyst Credentials</span>
              </button>

              <p className="text-center text-xs text-slate-400 pt-2">
                Need an organizational seat?{" "}
                <Link href="/signup" className="text-emerald-400 font-semibold hover:underline">
                  Create Account
                </Link>
              </p>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
