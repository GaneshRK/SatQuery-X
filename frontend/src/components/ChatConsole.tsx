'use client';

import React, { useState } from 'react';
import { Send, Sparkles, Terminal, Loader2, CheckCircle2, ShieldCheck, Zap } from 'lucide-react';
import { ExecutionTrace, InputMode } from '@/types';

interface ChatConsoleProps {
  sessionId: string;
  detectedMode: InputMode | null;
  hasImages: boolean;
  onQueryExecuted: (trace: ExecutionTrace) => void;
}

export const ChatConsole: React.FC<ChatConsoleProps> = ({
  sessionId,
  detectedMode,
  hasImages,
  onQueryExecuted,
}) => {
  const [queryText, setQueryText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getPresets = () => {
    switch (detectedMode) {
      case 'cross_modal_pair':
        return [
          'Perform fused optical and SAR cross-modal land cover analysis',
          'Analyze radar backscatter vs optical spectral signatures',
          'Mission: Coastline & water boundary assessment',
        ];
      case 'bi_temporal':
      case 'change_vqa':
        return [
          'Has built-up area increased significantly between these two dates?',
          'Detect spatial change and quantify altered surface area',
          'Mission: Comprehensive urban expansion assessment',
        ];
      default:
        return [
          'What are the primary terrain and infrastructure features in this scene?',
          'Locate vegetation and forest regions',
          'Describe this satellite image in detail',
        ];
    }
  };

  const handleSend = async (customText?: string) => {
    const textToSend = customText || queryText;
    if (!textToSend.trim() || !hasImages) return;

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`/api/v1/sessions/${sessionId}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: textToSend.trim(), sync: true }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Query failed with status ${res.status}`);
      }

      const trace: ExecutionTrace = await res.json();
      onQueryExecuted(trace);
      setQueryText('');
    } catch (err: any) {
      setError(err.message || 'An error occurred during query execution.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-surface border border-border rounded-xl p-5 flex flex-col gap-4 shadow-xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-blue-400" />
          <h3 className="font-semibold text-sm text-white">Natural Language Query Console</h3>
        </div>
        <span className="text-[11px] font-mono text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
          Orchestrator: Agentic FSM Tool Loop
        </span>
      </div>

      {/* Preset Quick Actions */}
      <div className="flex flex-wrap gap-1.5">
        {getPresets().map((preset, i) => (
          <button
            key={i}
            onClick={() => handleSend(preset)}
            disabled={loading || !hasImages}
            className="px-2.5 py-1 text-xs rounded-md bg-slate-900/80 hover:bg-blue-600/20 hover:text-blue-300 hover:border-blue-500/30 text-slate-300 border border-slate-800 transition-all font-mono text-left disabled:opacity-40"
          >
            &bull; {preset}
          </button>
        ))}
      </div>

      {/* Query Form */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
        className="flex items-center gap-2"
      >
        <div className="relative flex-1">
          <input
            type="text"
            value={queryText}
            onChange={(e) => setQueryText(e.target.value)}
            placeholder={
              hasImages
                ? 'Ask a question or enter a Mission instruction (e.g. "Has built-up area increased?")...'
                : 'Upload satellite rasters above to enable query reasoning...'
            }
            disabled={!hasImages || loading}
            className="w-full bg-slate-950/80 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors disabled:opacity-40 font-sans"
          />
          {queryText.toLowerCase().startsWith('mission') && (
            <span className="absolute right-3 top-2.5 text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-purple-900/60 text-purple-300 border border-purple-700/50 flex items-center gap-1">
              <Zap className="w-3 h-3 text-purple-400" /> Mission Mode
            </span>
          )}
        </div>

        <button
          type="submit"
          disabled={!hasImages || loading || !queryText.trim()}
          className="px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-sm font-medium transition-all shadow-md shadow-blue-600/20 flex items-center gap-2 active:scale-95 shrink-0"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          <span>Reason</span>
        </button>
      </form>

      {error && (
        <div className="p-3 rounded-lg bg-red-950/40 border border-red-800/50 text-red-300 text-xs font-mono">
          Error: {error}
        </div>
      )}
    </div>
  );
};
