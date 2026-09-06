"use client";

import { useState } from "react";
import Link from "next/link";
import { authApi } from "../../services/contractClient";
import { MailCheck } from "lucide-react";
import PublicNavbar from "../../components/PublicNavbar";

export default function VerifyEmailPage() {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await authApi.verifyEmail({ email, code });
      setDone(true);
    } catch {
      setError("Invalid verification code. Please check and try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <PublicNavbar />
      <div className="simple-auth">
        <div className="auth-card center">
          <div className="big-icon">
            <MailCheck size={32} />
          </div>
          <h1>{done ? "Email Verified" : "Verify Your Email"}</h1>

          {done ? (
            <div>
              <p>Your email account is verified. You can sign in to SatQuery AI now.</p>
              <Link className="btn primary full" href="/login">
                Go to Login
              </Link>
            </div>
          ) : (
            <form onSubmit={submit} className="form" style={{ textAlign: "left" }}>
              <label>
                Email Address
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter registered email"
                  required
                />
              </label>

              <label>
                Verification Code / OTP
                <input
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="Enter 6-digit code (e.g. 123456)"
                  required
                />
              </label>

              {error && <div className="error">{error}</div>}

              <button className="btn primary full" disabled={loading}>
                {loading ? "Verifying…" : "Verify Email"}
              </button>

              <p className="auth-bottom">
                <Link href="/login">Back to Login</Link>
              </p>
            </form>
          )}
        </div>
      </div>
    </>
  );
}
