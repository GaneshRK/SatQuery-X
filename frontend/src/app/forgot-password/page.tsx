"use client";

import { useState } from "react";
import Link from "next/link";
import { authApi } from "../../services/contractClient";
import { Mail, Satellite } from "lucide-react";
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
        err.response?.data?.detail || "Unable to send reset link. Please check the email address."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <PublicNavbar />
      <div className="simple-auth">
        <div className="auth-card">
          <div className="auth-head">
            <Satellite size={21} />
            <span>
              SatQuery <b>AI</b>
            </span>
          </div>

          {sent ? (
            <div className="center">
              <div className="big-icon">
                <Mail size={32} />
              </div>
              <h1>Check Your Email</h1>
              <p>
                We've sent a password reset link to <b>{email}</b>.
              </p>
              <Link className="btn primary full" href="/login">
                Back to Login
              </Link>
            </div>
          ) : (
            <>
              <h1>Reset Your Password</h1>
              <p>Enter your email and we'll send you instructions to reset your password.</p>
              <form onSubmit={submit} className="form">
                <label>
                  Email Address
                  <input
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    type="email"
                    placeholder="Enter your email"
                    required
                  />
                </label>

                {error && <div className="error">{error}</div>}

                <button className="btn primary full" disabled={loading}>
                  {loading ? "Sending…" : "Send Reset Link"}
                </button>

                <p className="center" style={{ marginTop: 14 }}>
                  <Link className="center-link" href="/login">
                    Back to Login
                  </Link>
                </p>
              </form>
            </>
          )}
        </div>
      </div>
    </>
  );
}
