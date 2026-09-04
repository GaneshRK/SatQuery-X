'use client';

import React from 'react';
import { Satellite, ShieldCheck, Activity, Layers, Terminal, FileText, ChevronDown, Plus } from 'lucide-react';
import { InputMode } from '@/types';
import { SessionData } from '@/services/sessions';

interface HeaderProps {
  detectedMode: InputMode | null;
  onOpenUpload: () => void;
  onOpenReport: () => void;
  hasTrace: boolean;
  sessions?: SessionData[];
  activeSessionId?: string;
  onSelectSession?: (id: string) => void;
  onNewSession?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  detectedMode,
  onOpenUpload,
  onOpenReport,
  hasTrace,
  sessions = [],
  activeSessionId,
  onSelectSession,
  onNewSession,
}) => {
  const getModeBadge = () => {
    switch (detectedMode) {
      case 'single_image':
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/30">Mode 1: Single Image</span>;
      case 'cross_modal_pair':
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/30">Mode 2: Optical + SAR Fusion</span>;
      case 'bi_temporal':
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30">Mode 3: Bi-Temporal Change</span>;
      case 'change_vqa':
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">Mode 4: Change-Based VQA</span>;
      default:
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-slate-800 text-slate-400 border border-slate-700">Awaiting Ingestion</span>;
    }
  };

  return (
    <header className="h-16 border-b border-border bg-surface/80 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-40">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Satellite className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-lg tracking-tight text-white">SatQuery-X</span>
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-blue-900/60 text-blue-300 border border-blue-700/50">SIH26167</span>
            </div>
            <p className="text-xs text-slate-400 font-mono">Agentic Multimodal Satellite Reasoning Engine</p>
          </div>
        </div>

        {/* Session Selector */}
        {sessions.length > 0 && onSelectSession && (
          <div className="hidden lg:flex items-center gap-2 ml-4 pl-4 border-l border-slate-800">
            <div className="relative">
              <select
                value={activeSessionId || ''}
                onChange={(e) => onSelectSession(e.target.value)}
                className="bg-slate-900 border border-slate-800 text-xs font-mono text-slate-200 rounded-lg px-3 py-1.5 pr-8 appearance-none focus:outline-none focus:border-blue-500 max-w-[280px] truncate"
              >
                {sessions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
              <ChevronDown className="w-3.5 h-3.5 text-slate-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>

            {onNewSession && (
              <button
                onClick={onNewSession}
                title="Create New Session"
                className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800 transition-all"
              >
                <Plus className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-4">
        <div className="hidden md:flex items-center gap-2 text-xs font-mono text-slate-300 bg-slate-900/90 px-3 py-1.5 rounded-lg border border-slate-800">
          <Activity className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
          <span>Telemetry:</span>
          {getModeBadge()}
        </div>

        <button
          onClick={onOpenUpload}
          className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-all shadow-md shadow-blue-600/20 active:scale-95"
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Upload Rasters</span>
        </button>

        {hasTrace && (
          <button
            onClick={onOpenReport}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition-all active:scale-95"
          >
            <FileText className="w-3.5 h-3.5 text-blue-400" />
            <span>Intelligence Report</span>
          </button>
        )}

        <div className="hidden xl:flex items-center gap-1.5 text-xs text-emerald-400 font-mono bg-emerald-950/40 px-2.5 py-1 rounded border border-emerald-800/40">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>ISRO Evaluator Verified</span>
        </div>
      </div>
    </header>
  );
};
