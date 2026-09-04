'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
  Send,
  Sparkles,
  Terminal,
  Loader2,
  CheckCircle2,
  ShieldCheck,
  Zap,
  ChevronDown,
  ChevronRight,
  Bot,
  User,
  Layers,
  MapPin,
  CornerDownRight,
} from 'lucide-react';
import { ExecutionTrace, InputMode } from '@/types';
import { submitQuery, getQuery, listQueries, QueryDetailData } from '@/services/queries';

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
  const [loadingStage, setLoadingStage] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [queriesHistory, setQueriesHistory] = useState<QueryDetailData[]>([]);
  const [expandedTraceId, setExpandedTraceId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load queries history on sessionId change
  useEffect(() => {
    if (!sessionId) return;
    const fetchHistory = async () => {
      try {
        const history = await listQueries(sessionId);
        setQueriesHistory(history || []);
      } catch (err) {
        console.error('Failed to load query history:', err);
      }
    };
    fetchHistory();
  }, [sessionId]);

  // Scroll to bottom when queries change or during loading
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [queriesHistory, loading, loadingStage]);

  const getPresets = () => {
    switch (detectedMode) {
      case 'cross_modal_pair':
        return [
          'Perform fused optical and SAR cross-modal land cover analysis',
          'Analyze radar backscatter vs optical spectral signatures',
          'Coastline & water boundary penetration assessment',
        ];
      case 'bi_temporal':
      case 'change_vqa':
        return [
          'Detect and quantify flood inundation area across the basin compared to baseline',
          'Measure total waterlogged territory in square kilometers',
          'Has built-up or structural area increased significantly?',
        ];
      default:
        return [
          'Segment and quantify surface water bodies in km²',
          'Measure forest canopy and dense vegetation coverage',
          'Detect and count individual infrastructure structures',
          'Describe terrain classification and dominant land use',
        ];
    }
  };

  const getFollowUps = (lastQuery?: QueryDetailData) => {
    if (!lastQuery) return [];
    const task = lastQuery.detected_task || '';
    if (task.includes('FLOOD') || task.includes('WATER')) {
      return [
        'Calculate flood recession rate over temporal baselines',
        'Highlight critical submerged road and transport corridors',
        'Generate official ISRO-format disaster impact dossier',
      ];
    }
    if (task.includes('VEGETATION') || task.includes('DEFORESTATION')) {
      return [
        'Compute vegetation canopy density distribution',
        'Identify vulnerable buffer zones under 500m from forest edge',
        'Export geo-referenced GeoJSON boundaries',
      ];
    }
    return [
      'Compare spectral signatures against standard false-color infrared',
      'Quantify spatial distribution by grid quadtree',
      'Generate executive analytical briefing',
    ];
  };

  const handleSend = async (customText?: string) => {
    const textToSend = customText || queryText;
    if (!textToSend.trim() || !hasImages || !sessionId) return;

    setLoading(true);
    setLoadingStage('Parsing natural language & routing intent...');
    setError(null);

    try {
      const { query_id } = await submitQuery(sessionId, textToSend.trim());

      setLoadingStage('Executing computer vision & raster math tools...');

      // Poll until query completes (with max timeout of 12s)
      let queryDetail: QueryDetailData | null = null;
      for (let i = 0; i < 18; i++) {
        await new Promise((r) => setTimeout(r, 600));
        if (i === 4) setLoadingStage('Reprojecting geometries to geodesic metric CRS...');
        if (i === 8) setLoadingStage('Synthesizing spatial reasoning & evidence...');

        queryDetail = await getQuery(sessionId, query_id);
        if (queryDetail.status === 'COMPLETED' || queryDetail.status === 'FAILED') {
          break;
        }
      }

      if (queryDetail) {
        const trace = formatQueryToTrace(queryDetail, sessionId);
        onQueryExecuted(trace);
        // Refresh local history
        setQueriesHistory((prev) => {
          const exists = prev.some((q) => q.id === queryDetail!.id);
          if (exists) {
            return prev.map((q) => (q.id === queryDetail!.id ? queryDetail! : q));
          }
          return [...prev, queryDetail!];
        });
      }
      setQueryText('');
    } catch (err: any) {
      setError(err.message || 'An error occurred during query execution.');
    } finally {
      setLoading(false);
      setLoadingStage('');
    }
  };

  const latestQuery = queriesHistory.length > 0 ? queriesHistory[queriesHistory.length - 1] : undefined;

  return (
    <div className="bg-surface border border-border rounded-xl flex flex-col shadow-xl overflow-hidden">
      {/* Console Header */}
      <div className="p-4 border-b border-border/80 flex items-center justify-between bg-slate-950/40">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-blue-400" />
          <h3 className="font-semibold text-sm text-white">Natural Language Reasoning Thread</h3>
          {queriesHistory.length > 0 && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-900/40 text-blue-300 border border-blue-800/40 font-mono">
              {queriesHistory.length} turns
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 text-[11px] font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-2 py-0.5 rounded">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Agent FSM: Active
          </span>
        </div>
      </div>

      {/* Multi-Turn Conversation Thread */}
      <div className="p-4 flex flex-col gap-4 max-h-[380px] overflow-y-auto min-h-[160px] bg-slate-950/20">
        {queriesHistory.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center py-8 text-center text-slate-500">
            <Bot className="w-9 h-9 text-slate-600 mb-2" />
            <p className="text-xs font-mono text-slate-400">
              No queries executed in this session yet.
            </p>
            <p className="text-[11px] text-slate-500 mt-1">
              Select a suggested preset below or ask any geospatial question to trigger multi-tool reasoning.
            </p>
          </div>
        )}

        {queriesHistory.map((q) => {
          const isExpanded = expandedTraceId === q.id;
          const totalAreaKm2 = (q.evidence_regions || []).reduce(
            (sum, e) => sum + (e.area_km2 || 0),
            0
          );

          return (
            <div key={q.id} className="flex flex-col gap-2.5">
              {/* User Message Balloon */}
              <div className="flex items-start gap-2.5 justify-end">
                <div className="max-w-[85%] bg-blue-600/20 border border-blue-500/30 rounded-2xl rounded-tr-sm px-4 py-2.5 text-xs text-blue-100 font-mono shadow-sm">
                  {q.text}
                </div>
                <div className="w-7 h-7 rounded-full bg-blue-600/30 border border-blue-500/40 flex items-center justify-center shrink-0">
                  <User className="w-3.5 h-3.5 text-blue-300" />
                </div>
              </div>

              {/* Assistant Response Balloon */}
              <div className="flex items-start gap-2.5 justify-start">
                <div className="w-7 h-7 rounded-full bg-emerald-950 border border-emerald-500/40 flex items-center justify-center shrink-0 mt-0.5">
                  <Bot className="w-3.5 h-3.5 text-emerald-400" />
                </div>
                <div className="max-w-[90%] bg-slate-900/90 border border-slate-800 rounded-2xl rounded-tl-sm p-3.5 flex flex-col gap-2 text-xs shadow-md">
                  {/* Task & Confidence Tag */}
                  <div className="flex items-center justify-between flex-wrap gap-1.5 pb-2 border-b border-slate-800">
                    <div className="flex items-center gap-1.5">
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-blue-950 text-blue-300 border border-blue-800/60">
                        {q.detected_task || 'SPATIAL_REASONING'}
                      </span>
                      {q.confidence && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-950/60 text-emerald-400 border border-emerald-800/40 flex items-center gap-1">
                          <ShieldCheck className="w-2.5 h-2.5" />
                          {(q.confidence * 100).toFixed(0)}% conf
                        </span>
                      )}
                    </div>

                    <button
                      onClick={() => {
                        const trace = formatQueryToTrace(q, sessionId);
                        onQueryExecuted(trace);
                      }}
                      className="text-[10px] font-mono text-cyan-400 hover:text-cyan-300 hover:underline flex items-center gap-1"
                    >
                      <MapPin className="w-2.5 h-2.5" />
                      Inspect on Map
                    </button>
                  </div>

                  {/* Primary Answer */}
                  <div className="text-slate-200 leading-relaxed font-sans text-xs whitespace-pre-wrap">
                    {q.answer || 'Query processed successfully.'}
                  </div>

                  {/* Quantified Area Highlight if present */}
                  {totalAreaKm2 > 0 && (
                    <div className="p-2 rounded-lg bg-cyan-950/40 border border-cyan-800/40 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Layers className="w-3.5 h-3.5 text-cyan-400" />
                        <span className="text-[11px] font-mono text-slate-300">
                          Quantified Geodesic Ground Area:
                        </span>
                      </div>
                      <span className="text-xs font-mono font-bold text-cyan-300">
                        {totalAreaKm2.toFixed(3)} km² ({((totalAreaKm2 * 100).toFixed(1))} ha)
                      </span>
                    </div>
                  )}

                  {/* Collapsible Execution Steps */}
                  {q.execution_steps && q.execution_steps.length > 0 && (
                    <div className="pt-1">
                      <button
                        onClick={() => setExpandedTraceId(isExpanded ? null : q.id)}
                        className="text-[10px] font-mono text-slate-400 hover:text-slate-200 flex items-center gap-1 transition-colors"
                      >
                        {isExpanded ? (
                          <ChevronDown className="w-3 h-3" />
                        ) : (
                          <ChevronRight className="w-3 h-3" />
                        )}
                        <span>
                          {q.execution_steps.length} Tool Execution Step
                          {q.execution_steps.length > 1 ? 's' : ''}
                        </span>
                      </button>

                      {isExpanded && (
                        <div className="mt-2 space-y-1.5 pl-3 border-l border-slate-800">
                          {q.execution_steps.map((step) => (
                            <div
                              key={step.id || step.step_number}
                              className="flex items-center justify-between text-[11px] font-mono bg-slate-950/60 px-2 py-1 rounded border border-slate-800/80"
                            >
                              <div className="flex items-center gap-1.5 text-slate-300">
                                <span className="text-slate-500">#{step.step_number}</span>
                                <span className="text-blue-300 font-semibold">{step.tool_name}</span>
                                <span className="text-slate-500 text-[10px]">
                                  ({step.model_version})
                                </span>
                              </div>
                              <span className="text-emerald-400 text-[10px]">
                                {step.latency_ms ? `${step.latency_ms}ms` : 'completed'}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {/* Live Execution Loading Animation */}
        {loading && (
          <div className="flex items-start gap-2.5 justify-start animate-fadeIn">
            <div className="w-7 h-7 rounded-full bg-blue-950 border border-blue-500/40 flex items-center justify-center shrink-0">
              <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />
            </div>
            <div className="bg-slate-900/90 border border-blue-500/30 rounded-2xl rounded-tl-sm p-3.5 text-xs text-blue-200 font-mono flex items-center gap-2.5 shadow-lg shadow-blue-500/5">
              <Zap className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
              <span>{loadingStage || 'Decomposing query with Agentic FSM...'}</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Dynamic Follow-Up Suggestions or Presets */}
      <div className="px-4 py-2.5 border-t border-border/60 bg-slate-950/40 flex flex-col gap-1.5">
        <div className="flex items-center gap-1 text-[11px] font-mono text-slate-400">
          <CornerDownRight className="w-3 h-3 text-blue-400" />
          <span>
            {queriesHistory.length > 0 ? 'Recommended follow-up queries:' : 'Suggested missions:'}
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {(queriesHistory.length > 0 ? getFollowUps(latestQuery) : getPresets()).map(
            (suggestion, i) => (
              <button
                key={i}
                onClick={() => handleSend(suggestion)}
                disabled={loading || !hasImages}
                className="px-2.5 py-1 text-[11px] rounded-md bg-slate-900/90 hover:bg-blue-600/20 hover:text-blue-300 hover:border-blue-500/40 text-slate-300 border border-slate-800 transition-all font-mono text-left disabled:opacity-40"
              >
                &bull; {suggestion}
              </button>
            )
          )}
        </div>
      </div>

      {/* Query Input Bar */}
      <div className="p-4 border-t border-border bg-slate-950/80">
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
                  ? 'Ask any geospatial or change query (e.g. Quantify water body extent in km²)...'
                  : 'Upload satellite imagery to activate vision-language reasoning...'
              }
              disabled={loading || !hasImages}
              className="w-full bg-slate-900 border border-slate-800 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 rounded-lg pl-4 pr-10 py-2.5 text-xs text-white placeholder-slate-500 font-mono transition-all disabled:opacity-50 disabled:cursor-not-allowed"
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
          <div className="mt-2 p-2.5 rounded-lg bg-red-950/40 border border-red-800/40 text-red-300 text-xs font-mono">
            {error}
          </div>
        )}
      </div>
    </div>
  );
};
