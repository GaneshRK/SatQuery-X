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
  ChevronLeft,
  ChevronRight,
  FileText,
  MapPin,
  ShieldCheck,
  User,
  ChevronDown,
} from "lucide-react";
import { SystemHealthModal } from "./SystemHealthModal";
import { CommandPalette } from "./ui/CommandPalette";

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
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);

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
      {/* Dynamic Collapsible Sidebar */}
      <aside
        className="sidebar"
        style={{
          width: isCollapsed ? "72px" : "240px",
          transition: "width 0.25s cubic-bezier(0.16, 1, 0.3, 1)",
        }}
      >
        <div className="flex items-center justify-between side-brand">
          <Link href="/dashboard" className="brand" title="SatQuery AI Workstation">
            <span className="brand-mark">
              <Satellite size={18} />
            </span>
            {!isCollapsed && (
              <span>
                SatQuery <b>AI</b>
              </span>
            )}
          </Link>
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="hidden lg:flex items-center justify-center p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
            title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
          </button>
        </div>

        {/* Orbit Status Chip in Sidebar */}
        {!isCollapsed ? (
          <div
            style={{
              margin: "0 4px 14px",
              padding: "8px 10px",
              background: "rgba(11, 33, 46, 0.6)",
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
              <strong style={{ color: "#2ee79b", display: "block", letterSpacing: "0.5px" }}>
                MISSION ACTIVE
              </strong>
              <span>Sentinel Constellation</span>
            </div>
          </div>
        ) : (
          <div className="flex justify-center my-3" title="Sentinel Constellation Active">
            <span className="pulse-dot"></span>
          </div>
        )}

        <nav className="side-nav">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`side-link ${isActive ? "active" : ""}`}
                title={isCollapsed ? item.label : undefined}
                style={{
                  justifyContent: isCollapsed ? "center" : "flex-start",
                  position: "relative",
                }}
              >
                <Icon size={17} className="shrink-0" />
                {!isCollapsed && <span>{item.label}</span>}
                {!isCollapsed && item.badge && (
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
            href="/docs"
            className={`side-link ${pathname === "/docs" ? "active" : ""}`}
            title={isCollapsed ? "Documentation" : undefined}
            style={{ justifyContent: isCollapsed ? "center" : "flex-start" }}
          >
            <FileText size={17} className="shrink-0" />
            {!isCollapsed && <span>Documentation</span>}
          </Link>

          <Link
            href="/settings"
            className={`side-link ${pathname === "/settings" ? "active" : ""}`}
            title={isCollapsed ? "Settings" : undefined}
            style={{ justifyContent: isCollapsed ? "center" : "flex-start" }}
          >
            <Settings size={17} className="shrink-0" />
            {!isCollapsed && <span>Settings</span>}
          </Link>

          <Link
            href="/contact"
            className={`side-link ${pathname === "/contact" ? "active" : ""}`}
            title={isCollapsed ? "Help & Support" : undefined}
            style={{ justifyContent: isCollapsed ? "center" : "flex-start" }}
          >
            <LifeBuoy size={17} className="shrink-0" />
            {!isCollapsed && <span>Help & Support</span>}
          </Link>
        </nav>

        {/* User Workspace Info & Logout */}
        <div className="pt-3 border-t border-slate-800/80 mt-auto">
          {!isCollapsed ? (
            <div className="flex items-center justify-between px-2 py-1.5 mb-2 rounded bg-slate-900/60 border border-slate-800 text-[11px]">
              <div className="truncate pr-2">
                <div className="text-white font-medium truncate">
                  {user?.full_name || "Analyst Workspace"}
                </div>
                <div className="text-slate-400 text-[10px] font-mono truncate">
                  {user?.email || "analyst@satquery.ai"}
                </div>
              </div>
              <ShieldCheck size={14} className="text-emerald-400 shrink-0" />
            </div>
          ) : null}

          <button
            className="side-logout w-full"
            onClick={() => {
              logout();
              router.push("/");
            }}
            title="Log out"
            style={{ justifyContent: isCollapsed ? "center" : "flex-start" }}
          >
            <LogOut size={16} className="shrink-0" />
            {!isCollapsed && <span>Log out</span>}
          </button>
        </div>
      </aside>

      <main
        className="app-main"
        style={{
          marginLeft: isCollapsed ? "72px" : "240px",
          width: isCollapsed ? "calc(100% - 72px)" : "calc(100% - 240px)",
          transition: "margin-left 0.25s cubic-bezier(0.16, 1, 0.3, 1), width 0.25s cubic-bezier(0.16, 1, 0.3, 1)",
        }}
      >
        <header className="app-topbar">
          <div className="flex items-center gap-4">
            {/* Search bar with quick keyboard shortcut */}
            <div
              className="search-box"
              onClick={() =>
                window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))
              }
              style={{ cursor: "pointer" }}
              title="Press Cmd+K or Ctrl+K to search"
            >
              <Search size={14} color="#78919b" />
              <input
                readOnly
                placeholder="Search coordinates, AOI, or target (e.g. Coimbatore, 11.0° N)..."
                style={{ cursor: "pointer" }}
              />
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

            {/* Active Context Chip */}
            <Link
              href="/explore"
              className="hidden 2xl:flex items-center gap-2 px-3 py-1 rounded-md bg-cyan-950/40 border border-cyan-800/40 text-[11px] font-mono text-cyan-300 hover:bg-cyan-900/30 transition-colors"
              title="Active Area of Interest (Click to change)"
            >
              <MapPin size={12} className="text-cyan-400" />
              <span>AOI: Coimbatore [11.01°N, 76.96°E]</span>
            </Link>
          </div>

          {/* Telemetry & Subsystems */}
          <div className="flex items-center gap-5">
            <div className="hidden lg:flex telemetry-bar">
              <div className="telemetry-item" title="Universal Coordinated Time">
                <Clock size={12} color="#38bdf8" />
                <span>{utcTime || "UTC LIVE"}</span>
              </div>
              <div className="telemetry-item" title="Next Copernicus Constellation Overpass">
                <Radio size={12} color="#2ee79b" />
                <span>
                  S2 Pass: <b>~38m</b>
                </span>
              </div>
            </div>

            <button
              onClick={() => setShowHealth(true)}
              className="btn ghost small"
              style={{ fontSize: 11, padding: "6px 12px", gap: "6px" }}
              title="Inspect Model Cluster & System Health"
            >
              <Activity size={13} color="#2ee79b" />
              <span className="hidden sm:inline">System Health</span>
            </button>

            <span className="tier-pill enterprise">ENTERPRISE</span>

            {/* User Dropdown */}
            <div className="relative">
              <button
                onClick={() => setShowUserMenu(!showUserMenu)}
                className="profile-chip flex items-center gap-2 focus:outline-none"
              >
                <span>{(user?.full_name || user?.email || "G").slice(0, 1).toUpperCase()}</span>
                <span className="hidden md:inline">{user?.full_name || "Enterprise Lead"}</span>
                <ChevronDown size={12} className="text-slate-400" />
              </button>

              {showUserMenu && (
                <div
                  className="absolute right-0 mt-2 w-48 bg-slate-900 border border-slate-800 rounded-lg shadow-xl py-1 z-50 text-xs"
                  onMouseLeave={() => setShowUserMenu(false)}
                >
                  <div className="px-3 py-2 border-b border-slate-800 text-slate-400">
                    <div className="font-medium text-white truncate">
                      {user?.full_name || "Enterprise Lead"}
                    </div>
                    <div className="text-[10px] font-mono text-slate-500 truncate">
                      {user?.email || "analyst@satquery.ai"}
                    </div>
                  </div>
                  <Link
                    href="/settings"
                    className="block px-3 py-2 text-slate-300 hover:bg-slate-800 hover:text-white"
                    onClick={() => setShowUserMenu(false)}
                  >
                    Profile & Settings
                  </Link>
                  <Link
                    href="/docs"
                    className="block px-3 py-2 text-slate-300 hover:bg-slate-800 hover:text-white"
                    onClick={() => setShowUserMenu(false)}
                  >
                    Documentation
                  </Link>
                  <button
                    onClick={() => {
                      setShowUserMenu(false);
                      logout();
                      router.push("/");
                    }}
                    className="w-full text-left px-3 py-2 text-red-400 hover:bg-red-950/30 hover:text-red-300 border-t border-slate-800"
                  >
                    Sign Out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {children}
      </main>

      <CommandPalette />
      <SystemHealthModal isOpen={showHealth} onClose={() => setShowHealth(false)} />
    </div>
  );
}
