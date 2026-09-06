"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../../context/AuthContext";
import { Eye, EyeOff, Satellite } from "lucide-react";
import PublicNavbar from "../../components/PublicNavbar";

const sideImg =
  "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?auto=format&fit=crop&w=900&q=80";

export default function SignupPage() {
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [show, setShow] = useState(false);
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
      setMsg("Account created successfully. Redirecting to dashboard…");
      setTimeout(() => router.push("/dashboard"), 800);
    } catch (err: any) {
      setIsError(true);
      setMsg(
        err.response?.data?.detail ||
          err.response?.data?.error ||
          "Registration failed. Please check details."
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
            backgroundImage: `linear-gradient(0deg, rgba(1,13,20,.8), rgba(1,13,20,.1)), url(${sideImg})`,
          }}
        >
          <div className="quote">"Satellite data for a better tomorrow."</div>
        </div>

        <div className="auth-card">
          <div className="auth-head">
            <Satellite size={21} />
            <span>
              SatQuery <b>AI</b>
            </span>
          </div>

          <h1>Create Your Account</h1>
          <p>Join SatQuery AI and explore the Earth with AI.</p>

          <form onSubmit={submit} className="form">
            <label>
              Full Name
              <input
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                placeholder="e.g. Ganesh K"
                required
              />
            </label>

            <label>
              Email Address
              <input
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                type="email"
                placeholder="e.g. ganesh@example.com"
                required
              />
            </label>

            <label>
              Password
              <div className="input-icon">
                <input
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  type={show ? "text" : "password"}
                  placeholder="Create a strong password"
                  required
                  minLength={8}
                />
                <button type="button" onClick={() => setShow(!show)}>
                  {show ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </label>

            {msg && <div className={isError ? "error" : "info"}>{msg}</div>}

            <button className="btn primary full" disabled={loading}>
              {loading ? "Creating Account…" : "Create Account"}
            </button>

            <div className="or">OR</div>
            <button
              type="button"
              className="btn dark-outline full"
              onClick={() => router.push("/login")}
            >
              Sign In with Existing Account
            </button>

            <p className="auth-bottom">
              Already have an account? <Link href="/login">Sign In</Link>
            </p>
          </form>
        </div>
      </div>
    </>
  );
}
