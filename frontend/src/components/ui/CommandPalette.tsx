"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  Bot,
  Globe,
  Layers,
  History,
  FileText,
  FolderKanban,
  Sliders,
  ExternalLink,
  X,
} from "lucide-react";

export interface CommandPaletteProps {
  onSelectPrompt?: (prompt: string) => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({ onSelectPrompt }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const router = useRouter();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      } else if (e.key === "Escape") {
        setIsOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  if (!isOpen) return null;

  const navigationItems = [
    { label: "AI Assistant Workstation", icon: Bot, href: "/assistant" },
    { label: "Earth Explorer (Browse Observations)", icon: Globe, href: "/explore" },
    { label: "Observation Comparison (Swipe/Split)", icon: Layers, href: "/compare" },
    { label: "Mission Control (Dashboard)", icon: Sliders, href: "/dashboard" },
    { label: "Historical Analyses", icon: History, href: "/analysis" },
    { label: "Saved Projects & Workspaces", icon: FolderKanban, href: "/projects" },
  ];

  const quickPrompts = [
    "What is changing around Coimbatore over time?",
    "Visualize the heat coordinates in Coimbatore",
    "What is changing around Chennai?",
    "How does Thoothukudi differ from Chennai?",
    "Show vegetation cover and urban sprawl",
  ];

  const filteredNav = navigationItems.filter((item) =>
    item.label.toLowerCase().includes(query.toLowerCase())
  );
  const filteredPrompts = quickPrompts.filter((p) =>
    p.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24 p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-100">
      <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-800 bg-slate-950/60">
          <Search className="w-4 h-4 text-cyan-400 shrink-0" />
          <input
            autoFocus
            type="text"
            placeholder="Search commands, tools, or ask an Earth query..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full bg-transparent text-sm text-slate-100 placeholder-slate-500 focus:outline-none"
          />
          <button
            onClick={() => setIsOpen(false)}
            className="p-1 rounded text-slate-400 hover:text-slate-200"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="max-h-[360px] overflow-y-auto p-2 space-y-3">
          {filteredNav.length > 0 && (
            <div>
              <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Navigation
              </div>
              <div className="space-y-0.5">
                {filteredNav.map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.href}
                      onClick={() => {
                        router.push(item.href);
                        setIsOpen(false);
                      }}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800/80 hover:text-cyan-300 rounded-lg transition-colors text-left"
                    >
                      <Icon className="w-4 h-4 text-slate-400" />
                      <span>{item.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {filteredPrompts.length > 0 && (
            <div>
              <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Quick Satellite Queries
              </div>
              <div className="space-y-0.5">
                {filteredPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => {
                      if (onSelectPrompt) onSelectPrompt(prompt);
                      else router.push(`/assistant?q=${encodeURIComponent(prompt)}`);
                      setIsOpen(false);
                    }}
                    className="w-full flex items-center justify-between px-3 py-2 text-xs text-slate-300 hover:bg-slate-800/80 hover:text-cyan-300 rounded-lg transition-colors text-left"
                  >
                    <span>&bull; {prompt}</span>
                    <ExternalLink className="w-3 h-3 text-slate-500" />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="px-4 py-2 border-t border-slate-800 bg-slate-950/40 flex items-center justify-between text-[11px] text-slate-500">
          <span>Navigate with arrows</span>
          <span>ESC to close</span>
        </div>
      </div>
    </div>
  );
};
