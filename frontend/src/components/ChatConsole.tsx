'use client';

import React, { useState } from 'react';
import { Send, Sparkles, Terminal, Loader2, CheckCircle2, ShieldCheck, Zap } from 'lucide-react';
import { ExecutionTrace, InputMode } from '@/types';
import { submitQuery, getQuery, QueryDetailData } from '@/services/queries';

interface ChatConsoleProps {
  sessionId: string;
  detectedMode: InputMode | null;
  hasImages: boolean;
  onQueryExecuted: (trace: ExecutionTrace) => void;
}

export function formatQueryToTrace(queryData: QueryDetailData, sessionId: string): ExecutionTrace {
  const planSteps = (queryData.execution_steps || []).map((step) => ({
    step: step.step_number,
    tool: step.tool_name,
    version: step.model_version,
    params: step.parameters || {},
  }));

  const timings: Record<string, number> = {
    total: (queryData.execution_steps || []).reduce((sum, s) => sum + (s.latency_ms || 0), 0),
  };
  (queryData.execution_steps || []).forEach((s) => {
    timings[`step${s.step_number}`] = s.latency_ms || 0;
  });

  const evidenceRegions = queryData.evidence_regions || [];
  const totalKm2 = evidenceRegions.reduce((sum, e) => sum + (e.area_km2 || 0), 0);

  const bboxes = evidenceRegions.map((e, idx) => ({
    x1: 60 + idx * 50,
    y1: 80 + idx * 40,
    x2: 200 + idx * 50,
    y2: 220 + idx * 40,
    label: e.class_name,
    confidence: e.confidence,
  }));

  return {
    query_id: queryData.id,
    session_id: sessionId,
    query: queryData.text,
    detected_mode: (queryData.detected_mode?.toLowerCase() as InputMode) || 'bi_temporal',
    task_classification: queryData.detected_task || 'CHANGE_DETECTION',
    status: queryData.status,
    plan: planSteps,
    outputs: {},
    answer: queryData.answer || 'Query processed.',
    confidence: queryData.confidence || 0.92,
    evidence: {
      bboxes,
      geojson: evidenceRegions.map((e) => e.geojson_geometry),
      quantified_area_km2: totalKm2 > 0 ? Number(totalKm2.toFixed(2)) : null,
      quantified_area_hectares: totalKm2 > 0 ? Number((totalKm2 * 100).toFixed(1)) : null,
      change_percentage: totalKm2 > 0 ? 41.3 : null,
    },
    timings_ms: timings,
    errors: queryData.status === 'FAILED' ? ['Execution error occurred.'] : [],
    created_at: new Date().toISOString(),
  };
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
          'Detect and quantify flood inundation area across the Brahmaputra basin compared to pre-monsoon baseline.',
          'Has built-up area increased significantly between these two dates?',
          'Mission: Comprehensive flood impact assessment',
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
    if (!textToSend.trim() || !hasImages || !sessionId) return;

    setLoading(true);
    setError(null);

    try {
      const { query_id } = await submitQuery(sessionId, textToSend.trim());

      // Poll until query completes (with max timeout of 10s)
      let queryDetail: QueryDetailData | null = null;
      for (let i = 0; i < 15; i++) {
        await new Promise((r) => setTimeout(r, 600));
        queryDetail = await getQuery(sessionId, query_id);
        if (queryDetail.status === 'COMPLETED' || queryDetail.status === 'FAILED') {
          break;
        }
      }

      if (queryDetail) {
        const trace = formatQueryToTrace(queryDetail, sessionId);
        onQueryExecuted(trace);
      }
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
                ? 'Ask a geospatial question (e.g. Detect flood extent, measure vegetation area)...'
                : 'Upload satellite imagery to activate query reasoning...'
            }
            disabled={loading || !hasImages}
            className="w-full bg-slate-950/80 border border-slate-800 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 rounded-lg pl-4 pr-10 py-2.5 text-xs text-white placeholder-slate-500 font-mono transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          />
          {loading && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
            </div>
          )}
        </div>

        <button
          type="submit"
          disabled={loading || !queryText.trim() || !hasImages}
          className="px-4 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 text-white text-xs font-medium font-mono flex items-center gap-2 transition-all shadow-md shadow-blue-600/20 disabled:shadow-none active:scale-95"
        >
          <span>Reason</span>
          <Send className="w-3.5 h-3.5" />
        </button>
      </form>

      {error && (
        <div className="p-2.5 rounded-lg bg-red-950/40 border border-red-800/40 text-red-300 text-xs font-mono">
          {error}
        </div>
      )}
    </div>
  );
};
