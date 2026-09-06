"use client";

import Link from "next/link";
import { Satellite } from "lucide-react";

export default function PublicNavbar() {
  return (
    <header className="public-nav">
      <Link href="/" className="brand">
        <span className="brand-mark">
          <Satellite size={18} />
        </span>
        <span>SatQuery <b>AI</b></span>
      </Link>
      <nav>
        <Link href="/">Home</Link>
        <Link href="/docs">Features</Link>
        <Link href="/about">Use Cases</Link>
        <Link href="/about">About</Link>
        <Link href="/contact">Contact</Link>
      </nav>
      <div className="nav-actions">
        <Link className="btn ghost small" href="/login">
          Login
        </Link>
        <Link className="btn primary small" href="/signup">
          Get Started
        </Link>
      </div>
    </header>
  );
}
