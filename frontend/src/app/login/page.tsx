"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../../context/AuthContext";
import { Eye, EyeOff, Satellite } from "lucide-react";
import PublicNavbar from "../../components/PublicNavbar";

const sideImg =
  "https://images.unsplash.com/photo-1500534623283-312aade485b7?auto=format&fit=crop&w=900&q=80";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
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
          "Unable to sign in. Check your credentials."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <PublicNavbar />
      <div className="auth-page">
        <div
          className="auth-image"
          style={{
            backgroundImage: `linear-gradient(0deg, rgba(1,13,20,.7), rgba(1,13,20,.1)), url(${sideImg})`,
          }}
        >
          <div className="quote">"Understand our planet. Make a difference."</div>
        </div>

        <div className="auth-card">
          <div className="auth-head">
            <Satellite size={21} />
            <span>
              SatQuery <b>AI</b>
            </span>
          </div>

          <h1>Welcome Back</h1>
          <p>Sign in to continue to SatQuery AI.</p>

          <form onSubmit={submit} className="form">
            <label>
              Email Address
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                type="email"
                placeholder="e.g. demo@satquery.ai"
                required
              />
            </label>

            <label>
              Password
              <div className="input-icon">
                <input
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  type={show ? "text" : "password"}
                  placeholder="Enter your password"
                  required
                />
                <button type="button" onClick={() => setShow(!show)}>
                  {show ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </label>

            <div className="form-row">
              <span />
              <Link href="/forgot-password">Forgot Password?</Link>
            </div>

            {error && <div className="error">{error}</div>}

            <button className="btn primary full" disabled={loading}>
              {loading ? "Signing In…" : "Sign In"}
            </button>

            <div className="or">OR QUICK DEMO LOGIN</div>
            <button
              type="button"
              className="btn dark-outline full"
              onClick={() => {
                setEmail("demo@satquery.ai");
                setPassword("password123");
              }}
            >
              Fill Demo Analyst Credentials
            </button>

            <p className="auth-bottom">
              Don't have an account? <Link href="/signup">Create Account</Link>
            </p>
          </form>
        </div>
      </div>
    </>
  );
}
