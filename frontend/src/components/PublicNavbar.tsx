"use client";

import Link from "next/link";
import { Satellite, Bot, ArrowRight } from "lucide-react";

export default function PublicNavbar() {
  return (
    <header className="public-nav">
      <Link href="/" className="brand" title="SatQuery AI Platform">
        <span className="brand-mark">
          <Satellite size={18} />
        </span>
        <span>
          SatQuery <b>AI</b>
        </span>
      </Link>
      <nav>
        <Link href="/">Overview</Link>
        <Link href="/assistant">AI Workstation</Link>
        <Link href="/explore">Explore Earth</Link>
        <Link href="/docs">Docs & Specs</Link>
        <Link href="/about">Mission</Link>
        <Link href="/contact">Enterprise</Link>
      </nav>
      <div className="nav-actions">
        <Link className="btn ghost small" href="/login">
          Sign In
        </Link>
        <Link className="btn primary small" href="/assistant">
          <Bot size={14} />
          <span>Launch Workstation</span>
        </Link>
      </div>
    </header>
  );
}
