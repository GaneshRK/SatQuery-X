"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "../context/AuthContext";
import {
  LayoutDashboard,
  Bot,
  Map,
  ScanSearch,
  GitCompare,
  FolderKanban,
  Settings,
  LifeBuoy,
  LogOut,
  Satellite,
  Activity,
  Clock,
  Radio,
  Search,
} from "lucide-react";
import { SystemHealthModal } from "./SystemHealthModal";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/assistant", label: "AI Assistant", icon: Bot, badge: "AI" },
  { href: "/explore", label: "Explore Map", icon: Map },
  { href: "/analysis", label: "Analyze", icon: ScanSearch },
  { href: "/compare", label: "Compare", icon: GitCompare, badge: "Siamese" },
  { href: "/projects", label: "Projects", icon: FolderKanban },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [showHealth, setShowHealth] = useState(false);
  const [utcTime, setUtcTime] = useState("");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setUtcTime(now.toUTCString().replace("GMT", "UTC"));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/dashboard" className="brand side-brand">
          <span className="brand-mark">
            <Satellite size={18} />
          </span>
          <span>
            SatQuery <b>AI</b>
          </span>
        </Link>

        {/* Orbit Status Chip in Sidebar */}
        <div
          style={{
            margin: "0 8px 14px",
            padding: "8px 10px",
            background: "rgba(11, 33, 46, 0.7)",
            border: "1px solid #163a4d",
            borderRadius: "6px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "10px",
            color: "#8faab5",
          }}
        >
          <span className="pulse-dot"></span>
          <div style={{ lineHeight: 1.3 }}>
            <strong style={{ color: "#2ee79b", display: "block" }}>MISSION ACTIVE</strong>
            <span>Sentinel Constellation</span>
          </div>
        </div>

        <div className="side-nav">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`side-link ${isActive ? "active" : ""}`}
                style={{ position: "relative" }}
              >
                <Icon size={17} />
                <span>{item.label}</span>
                {item.badge && (
                  <span
                    style={{
                      marginLeft: "auto",
                      fontSize: "9px",
                      padding: "2px 6px",
                      borderRadius: "4px",
                      background: isActive ? "#2ee79b" : "#0d2b38",
                      color: isActive ? "#04151a" : "#7aa1b1",
                      fontWeight: 700,
                    }}
                  >
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}

          <div className="side-spacer" />

          <Link
            href="/settings"
            className={`side-link ${pathname === "/settings" ? "active" : ""}`}
          >
            <Settings size={17} />
            <span>Settings</span>
          </Link>
          <Link
            href="/contact"
            className={`side-link ${pathname === "/contact" ? "active" : ""}`}
          >
            <LifeBuoy size={17} />
            <span>Help & Support</span>
          </Link>
        </div>

        <button
          className="side-logout"
          onClick={() => {
            logout();
            router.push("/");
          }}
        >
          <LogOut size={17} />
          <span>Log out</span>
        </button>
      </aside>

      <main className="app-main">
        <header className="app-topbar">
          {/* Search bar with quick keyboard shortcut */}
          <div className="search-box">
            <Search size={14} color="#78919b" />
            <input placeholder="Search coordinates, AOI, or target (e.g. Aral Sea, 44.5° N)..." />
            <span
              style={{
                fontSize: "10px",
                padding: "2px 5px",
                background: "#081923",
                border: "1px solid #1c3d4e",
                borderRadius: "3px",
                color: "#6b8a97",
                fontFamily: "monospace",
              }}
            >
              ⌘K
            </span>
          </div>

          {/* Real-time Telemetry Bar */}
          <div className="telemetry-bar">
            <div className="telemetry-item" title="Universal Coordinated Time">
              <Clock size={12} color="#38bdf8" />
              <span>{utcTime || "UTC LIVE"}</span>
            </div>
            <div className="telemetry-item" title="Next Copernicus Constellation Overpass">
              <Radio size={12} color="#2ee79b" />
              <span>S2 Pass: <b>~38m</b></span>
            </div>
          </div>

          {/* Right Action & Profile Area */}
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <button
              onClick={() => setShowHealth(true)}
              className="btn ghost small"
              style={{ fontSize: 11, padding: "6px 12px", gap: "6px" }}
              title="View Model Cluster & System Health"
            >
              <Activity size={13} color="#2ee79b" />
              <span>System Health</span>
            </button>

            <span className="tier-pill enterprise">ENTERPRISE</span>

            <div className="profile-chip">
              <span>{(user?.full_name || user?.email || "G").slice(0, 1).toUpperCase()}</span>
              <span>{user?.full_name || "Enterprise Lead"}</span>
            </div>
          </div>
        </header>

        {children}
      </main>

      <SystemHealthModal isOpen={showHealth} onClose={() => setShowHealth(false)} />
    </div>
  );
}
