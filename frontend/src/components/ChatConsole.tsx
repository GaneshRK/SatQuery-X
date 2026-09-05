'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
  Send,
  Sparkles,
  Loader2,
  ShieldCheck,
  Zap,
  ChevronDown,
  ChevronRight,
  Bot,
  User,
  Layers,
  MapPin,
  CornerDownRight,
  Download,
  FileCode,
  FileSpreadsheet,
  FileText,
  AlertTriangle,
  Globe,
  Mic,
  MicOff,
  HelpCircle,
} from 'lucide-react';
import { ExecutionTrace, InputMode } from '@/types';
import { submitQuery, listQueries, QueryDetailData, getExportUrl } from '@/services/queries';

interface ChatConsoleProps {
  sessionId: string;
  detectedMode: InputMode | null;
  hasImages: boolean;
  pendingPrompt?: string | null;
  onClearPendingPrompt?: () => void;
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

  // Extract real bboxes if provided by detection/grounding models, otherwise empty
  const bboxes = evidenceRegions
    .filter((e) => (e as any).bbox && Array.isArray((e as any).bbox) && (e as any).bbox.length === 4)
    .map((e) => {
      const b = (e as any).bbox;
      return {
        x1: b[0],
        y1: b[1],
        x2: b[2],
        y2: b[3],
        label: e.class_name,
        confidence: e.confidence,
      };
    });

  // Extract change percentage from real measurements if computed
  const measurementPct = queryData.answer_contract?.measurements?.find(
    (m: any) => m.metric && (m.metric.toLowerCase().includes('percent') || m.unit === '%')
  );
  const changePct = measurementPct && typeof measurementPct.value === 'number'
    ? measurementPct.value
    : null;

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
    confidence: typeof queryData.confidence === 'number' ? queryData.confidence : 0.0,
    answer_contract: queryData.answer_contract,
    evidence: {
      bboxes,
      geojson: evidenceRegions.map((e) => e.geojson_geometry).filter(Boolean),
      quantified_area_km2: totalKm2 > 0 ? Number(totalKm2.toFixed(3)) : null,
      quantified_area_hectares: totalKm2 > 0 ? Number((totalKm2 * 100).toFixed(2)) : null,
      change_percentage: changePct,
    },
    structured_plan: queryData.structured_plan,
    follow_up_questions: queryData.follow_up_questions,
    evidence_graph: queryData.evidence_graph,
    external_evidence: queryData.external_evidence,
    ui_actions: queryData.ui_actions,
    clarification: queryData.clarification,
    timings_ms: timings,
    errors: queryData.status === 'FAILED' ? ['Execution error occurred.'] : [],
    created_at: new Date().toISOString(),
  };
}

export const ChatConsole: React.FC<ChatConsoleProps> = ({
  sessionId,
  detectedMode,
  hasImages,
  pendingPrompt,
  onClearPendingPrompt,
  onQueryExecuted,
}) => {
  const [queryText, setQueryText] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [queriesHistory, setQueriesHistory] = useState<QueryDetailData[]>([]);
  const [expandedTraceId, setExpandedTraceId] = useState<string | null>(null);
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<any>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const toggleVoiceInput = () => {
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert('Speech Recognition is not supported by this browser. Please use Chrome, Edge, or Safari.');
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        setIsListening(true);
      };

      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        if (transcript) {
          setQueryText((prev) => (prev ? `${prev} ${transcript}` : transcript));
        }
        setIsListening(false);
      };

      recognition.onerror = (event: any) => {
        console.warn('Speech recognition error:', event.error);
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err) {
      console.error('Failed to start speech recognition:', err);
      setIsListening(false);
    }
  };

  // Auto-fill and execute when pendingPrompt arrives from "Ask This Area"
  useEffect(() => {
    if (pendingPrompt && !loading) {
      setQueryText(pendingPrompt);
      handleSend(pendingPrompt);
      if (onClearPendingPrompt) onClearPendingPrompt();
    }
  }, [pendingPrompt]);

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
        return [
          'Quantify total surface water change area in square kilometers',
          'Detect flood inundation extent and affected agricultural parcels',
          'Identify infrastructure at risk within 500m of inundated zones',
        ];
      case 'single_image':
      default:
        return [
          'Compute NDVI vegetation index and quantify healthy biomass canopy',
          'Extract all surface water bodies using spectral NDWI thresholding',
          'Detect and count structural footprints across the scene',
        ];
    }
  };

  const getFollowUps = (lastQuery?: QueryDetailData) => {
    if (lastQuery?.follow_up_questions && lastQuery.follow_up_questions.length > 0) {
      return lastQuery.follow_up_questions;
    }
    const task = lastQuery?.detected_task;
    if (task === 'CHANGE_DETECTION') {
      return [
        'Which specific agricultural parcels lost vegetation?',
        'Export detected change polygons as GeoJSON for QGIS',
        'Compare SAR backscatter penetration for confirmation',
      ];
    }
    return [
      'Quantify the metric surface area of detected regions',
      'What are the scientific limitations of this observation?',
      'Generate a comprehensive intelligence PDF dossier',
    ];
  };

  const handleSend = async (overrideText?: string) => {
    const textToSend = overrideText || queryText;
    if (!textToSend.trim() || !sessionId || loading) return;

    setLoading(true);
    setError(null);
    setLoadingStage('Analyzing query intent with Model Router...');
    setQueryText('');

    try {
      setTimeout(() => setLoadingStage('Validating CRS and reading raster chunks...'), 600);
      setTimeout(() => setLoadingStage('Executing deterministic computer vision & spectral math...'), 1400);

      const res = await submitQuery(sessionId, textToSend);

      setTimeout(async () => {
        try {
          const updatedHistory = await listQueries(sessionId);
          setQueriesHistory(updatedHistory || []);
          const latest = updatedHistory?.find((q) => q.id === res.query_id) || updatedHistory?.[0];
          if (latest) {
            const trace = formatQueryToTrace(latest, sessionId);
            onQueryExecuted(trace);
          }
        } catch (pollErr) {
          console.error('Error refreshing queries:', pollErr);
        } finally {
          setLoading(false);
          setLoadingStage('');
        }
      }, 2200);
    } catch (err: any) {
      console.error('Submit query failed:', err);
      setError(err?.message || 'Failed to submit query.');
      setLoading(false);
      setLoadingStage('');
    }
  };

  const handleDownloadExport = (queryId: string, format: string) => {
    const url = getExportUrl(sessionId, queryId, format);
    window.open(url, '_blank');
  };

  const latestQuery = queriesHistory[queriesHistory.length - 1];

  return (
    <div className="flex flex-col h-full bg-[#080d1a] border border-border rounded-xl overflow-hidden shadow-2xl">
      {/* Console Header */}
      <div className="h-11 border-b border-border bg-slate-950/80 px-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-blue-400" />
          <span className="text-xs font-mono font-semibold text-slate-200">
            AI Geospatial Copilot
          </span>
          {queriesHistory.length > 0 && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-900/40 text-blue-300 border border-blue-800/40 font-mono">
              {queriesHistory.length} turns
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 text-[11px] font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-2 py-0.5 rounded">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Deterministic CV + AI
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
              Select a suggested mission below or draw an AOI on the map to ask specific questions.
            </p>
          </div>
        )}

        {queriesHistory.map((q) => {
          const isExpanded = expandedTraceId === q.id;
          const totalAreaKm2 = (q.evidence_regions || []).reduce(
            (sum, e) => sum + (e.area_km2 || 0),
            0
          );
          const contract = q.answer_contract;

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
                  {/* Task & Confidence Header */}
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

                  {/* Ambiguity Clarification Options */}
                  {q.clarification && q.clarification.clarification_prompt && (
                    <div className="p-3 rounded-xl bg-amber-950/30 border border-amber-800/50 space-y-2 mt-1">
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-300 font-mono">
                        <HelpCircle className="w-3.5 h-3.5 text-amber-400" />
                        <span>Clarification Requested</span>
                      </div>
                      <p className="text-xs text-amber-200/90 leading-relaxed">
                        {q.clarification.clarification_prompt}
                      </p>
                      {q.clarification.clarification_options && q.clarification.clarification_options.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {q.clarification.clarification_options.map((opt: any, optIdx: number) => (
                            <button
                              key={optIdx}
                              type="button"
                              onClick={() => handleSend(opt.query || opt.label)}
                              className="px-2.5 py-1 bg-amber-900/40 hover:bg-amber-800/60 border border-amber-700/60 text-amber-200 rounded-lg text-xs font-mono transition-all flex items-center gap-1.5 hover:scale-105 active:scale-95 shadow-xs"
                            >
                              <Sparkles className="w-3 h-3 text-amber-300" />
                              <span>{opt.label}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Structured Measurements from Answer Contract */}
                  {contract?.measurements && contract.measurements.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {contract.measurements.map((m, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 rounded bg-cyan-950/40 border border-cyan-800/40 text-[10px] font-mono text-cyan-300 flex items-center gap-1"
                        >
                          <strong>{m.metric}:</strong> {typeof m.value === 'number' ? m.value.toFixed(2) : m.value} {m.unit || ''}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Quantified Area Highlight */}
                  {totalAreaKm2 > 0 && !contract?.measurements && (
                    <div className="p-2 rounded-lg bg-cyan-950/40 border border-cyan-800/40 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Layers className="w-3.5 h-3.5 text-cyan-400" />
                        <span className="text-[11px] font-mono text-slate-300">
                          Quantified Geodesic Ground Area:
                        </span>
                      </div>
                      <span className="text-xs font-mono font-bold text-cyan-300">
                        {totalAreaKm2.toFixed(3)} km² ({(totalAreaKm2 * 100).toFixed(1)} ha)
                      </span>
                    </div>
                  )}

                  {/* Scientific Limitations Notice */}
                  {contract?.limitations && contract.limitations.length > 0 && (
                    <div className="p-2 rounded bg-amber-950/20 border border-amber-900/30 text-[10px] font-mono text-amber-300/80 flex items-start gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                      <span>{contract.limitations[0]}</span>
                    </div>
                  )}

                  {/* External Web Corroboration Badge */}
                  {((q.external_evidence && q.external_evidence.length > 0) || (contract?.evidence && contract.evidence.some((e: any) => e.type === 'EXTERNAL_WEB_EVIDENCE'))) && (
                    <div className="flex items-center gap-1.5 text-[10px] font-mono text-blue-300 bg-blue-950/40 border border-blue-800/40 px-2 py-1 rounded w-fit">
                      <Globe className="w-3 h-3 text-blue-400" />
                      <span>Corroborated with audited external agency intelligence</span>
                    </div>
                  )}

                  {/* Dynamic Follow-up Suggestions on each message */}
                  {q.follow_up_questions && q.follow_up_questions.length > 0 && (
                    <div className="pt-2 border-t border-slate-800/80 space-y-1.5">
                      <span className="text-[10px] font-mono text-cyan-400 flex items-center gap-1">
                        <Sparkles className="w-3 h-3 text-cyan-400" />
                        Suggested Inquiries:
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {q.follow_up_questions.map((fq, fIdx) => (
                          <button
                            key={fIdx}
                            onClick={() => handleSend(fq)}
                            disabled={loading}
                            className="text-left px-2 py-1 rounded bg-slate-950/80 hover:bg-cyan-950/60 text-[11px] font-mono text-slate-300 hover:text-cyan-300 border border-slate-800 hover:border-cyan-700/60 transition-all disabled:opacity-40"
                          >
                            &bull; {fq}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Export Toolbar */}
                  <div className="pt-2 border-t border-slate-800 flex items-center justify-between flex-wrap gap-2 text-[10px] font-mono text-slate-400">
                    <span className="flex items-center gap-1">
                      <Download className="w-3 h-3" />
                      Export Data:
                    </span>
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => handleDownloadExport(q.id, 'geojson')}
                        className="px-2 py-0.5 rounded bg-slate-800 hover:bg-cyan-900/60 hover:text-cyan-300 text-slate-300 border border-slate-700 flex items-center gap-1 transition-all"
                        title="Download GeoJSON FeatureCollection"
                      >
                        <FileCode className="w-2.5 h-2.5" />
                        GeoJSON
                      </button>
                      <button
                        onClick={() => handleDownloadExport(q.id, 'csv')}
                        className="px-2 py-0.5 rounded bg-slate-800 hover:bg-emerald-900/60 hover:text-emerald-300 text-slate-300 border border-slate-700 flex items-center gap-1 transition-all"
                        title="Download Metrics CSV"
                      >
                        <FileSpreadsheet className="w-2.5 h-2.5" />
                        CSV
                      </button>
                      <button
                        onClick={() => handleDownloadExport(q.id, 'json')}
                        className="px-2 py-0.5 rounded bg-slate-800 hover:bg-blue-900/60 hover:text-blue-300 text-slate-300 border border-slate-700 flex items-center gap-1 transition-all"
                        title="Download 10-Key JSON Dossier"
                      >
                        <FileText className="w-2.5 h-2.5" />
                        JSON
                      </button>
                      <button
                        onClick={() => handleDownloadExport(q.id, 'geotiff')}
                        className="px-2 py-0.5 rounded bg-slate-800 hover:bg-purple-900/60 hover:text-purple-300 text-slate-300 border border-slate-700 flex items-center gap-1 transition-all"
                        title="Download Source GeoTIFF Raster"
                      >
                        GeoTIFF
                      </button>
                    </div>
                  </div>

                  {/* Collapsible Tool Execution Steps */}
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
                          {q.execution_steps.length} Execution Step
                          {q.execution_steps.length > 1 ? 's' : ''} (Trace)
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
              <span>{loadingStage || 'Decomposing query with Agentic Planner...'}</span>
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
                disabled={loading || !sessionId}
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
                  ? 'Ask any geospatial query (e.g. Quantify surface water extent in km²)...'
                  : 'Ask anything about Earth (e.g. What is changing around Chennai?)...'
              }
              disabled={loading || !sessionId}
              className="w-full bg-slate-900 border border-slate-800 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 rounded-lg pl-4 pr-10 py-2.5 text-xs text-white placeholder-slate-500 font-mono transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            />
            {loading && (
              <div className="absolute right-3 top-1/2 -translate-y-1/2">
                <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={toggleVoiceInput}
            disabled={loading || !sessionId}
            className={`p-2.5 rounded-lg border transition-all flex items-center justify-center ${
              isListening
                ? 'bg-red-950 text-red-400 border-red-500 animate-pulse ring-2 ring-red-500/50'
                : 'bg-slate-900 text-slate-400 hover:text-slate-200 hover:bg-slate-800 border-slate-800'
            }`}
            title={isListening ? 'Listening... click to stop' : 'Voice Input (Speech-to-Text)'}
          >
            {isListening ? <MicOff className="w-4 h-4 text-red-400" /> : <Mic className="w-4 h-4" />}
          </button>

          <button
            type="submit"
            disabled={loading || !queryText.trim() || !sessionId}
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
