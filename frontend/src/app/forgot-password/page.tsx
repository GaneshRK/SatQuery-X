"use client";

import React, { useState } from "react";
import Link from "next/link";
import { authApi } from "../../services/contractClient";
import { Mail, Satellite, ArrowLeft, ArrowRight, CheckCircle2 } from "lucide-react";
import PublicNavbar from "../../components/PublicNavbar";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await authApi.forgotPassword({ email });
      setSent(true);
    } catch (err: any) {
      setError(
        err.response?.data?.detail ||
          err.response?.data?.error ||
          "Unable to dispatch reset link. Please check your email address."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-[#040911] text-[#eef6f8]">
      <PublicNavbar />

      <div className="flex-1 flex items-center justify-center p-6">
        <div className="auth-card w-full max-w-md p-8 rounded-xl bg-[#081420] border border-[#153245] shadow-2xl">
          <div className="auth-head flex items-center gap-2.5 mb-6">
            <span className="brand-mark">
              <Satellite size={18} />
            </span>
            <span className="font-bold text-lg text-white">
              SatQuery <b>AI</b>
            </span>
          </div>

          {sent ? (
            <div className="text-center space-y-4 py-4">
              <div className="w-14 h-14 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center justify-center mx-auto">
                <CheckCircle2 size={28} />
              </div>
              <h1 className="text-xl font-bold text-white">Dispatch Instructions Sent</h1>
              <p className="text-xs text-slate-400 leading-relaxed">
                We have transmitted recovery instructions to <b className="text-white">{email}</b> if
                an associated analyst profile exists.
              </p>
              <Link
                href="/login"
                className="inline-flex items-center justify-center gap-2 w-full py-2.5 rounded-lg bg-emerald-400 hover:bg-emerald-300 text-slate-950 font-bold text-xs transition-all"
              >
                <ArrowLeft size={14} />
                <span>Return to Login</span>
              </Link>
            </div>
          ) : (
            <>
              <h1 className="text-2xl font-extrabold text-white mb-1.5">Reset Security Password</h1>
              <p className="text-xs text-slate-400 mb-6">
                Enter your registered analyst email address to receive password reset authorization.
              </p>

              <form onSubmit={submit} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                    Registered Email Address
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
                    <span>Dispatching Instructions...</span>
                  ) : (
                    <>
                      <span>Send Recovery Link</span>
                      <ArrowRight size={15} />
                    </>
                  )}
                </button>

                <p className="text-center text-xs text-slate-400 pt-2">
                  <Link
                    href="/login"
                    className="text-emerald-400 font-semibold hover:underline inline-flex items-center gap-1.5"
                  >
                    <ArrowLeft size={12} />
                    <span>Back to Login</span>
                  </Link>
                </p>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
