'use client';

import React, { useState } from 'react';
import {
  Activity,
  Clock,
  Cpu,
  CheckCircle2,
  AlertTriangle,
  ShieldCheck,
  ChevronRight,
  ChevronDown,
  Terminal,
  Zap,
  Layers,
  ArrowRight,
} from 'lucide-react';
import { ExecutionTrace } from '@/types';

interface ExecutionTraceTimelineProps {
  trace?: ExecutionTrace | null;
  agentSteps?: Array<{
    tool?: string;
    action?: string;
    status?: string;
    duration_s?: number;
    step_number?: number;
    parameters?: Record<string, any>;
    model_version?: string;
    latency_ms?: number;
  }>;
  totalLatencyMs?: number;
  taskClassification?: string;
  confidence?: number;
  answer?: string;
}

export const ExecutionTraceTimeline: React.FC<ExecutionTraceTimelineProps> = ({
  trace,
  agentSteps,
  totalLatencyMs,
  taskClassification,
  confidence,
  answer,
}) => {
  const [expandedStep, setExpandedStep] = useState<number | null>(null);

  // Normalize steps from either trace.plan or agentSteps
  const steps = (trace?.plan || agentSteps || []).map((s: any, idx: number) => ({
    step: s.step || s.step_number || idx + 1,
    tool: s.tool || s.action || 'satellite_inference',
    version: s.version || s.model_version || 'ChangeFormerV6',
    params: s.params || s.parameters || {},
    latency_ms: s.latency_ms || (s.duration_s ? Math.round(s.duration_s * 1000) : (trace?.timings_ms ? trace.timings_ms[`step${s.step || idx + 1}`] : 0)) || 0,
    status: s.status || 'STATUS_OK',
  }));

  const totalTime = totalLatencyMs ?? trace?.timings_ms?.total ?? steps.reduce((sum, s) => sum + s.latency_ms, 0);
  const task = taskClassification || trace?.task_classification || 'CHANGE_DETECTION';
  const conf = confidence ?? trace?.confidence;
  const verifiedAnswer = answer || trace?.answer;

  if (steps.length === 0 && !trace) {
    return (
      <div className="p-6 rounded-2xl bg-[#081420] border border-[#153245] text-center space-y-3">
        <Activity className="w-7 h-7 text-cyan-500/60 mx-auto animate-pulse" />
        <h4 className="text-sm font-semibold text-slate-300">Backend Execution Stream Standing By</h4>
        <p className="text-xs text-slate-500 font-mono max-w-sm mx-auto">
          Dispatch a query or select a test scenario to inspect real-time agent tool orchestration, neural inference, and latency.
        </p>
      </div>
    );
  }

  // Pipeline stages flow
  const pipelineFlow = [
    { label: 'Intent Analysis', icon: Zap },
    { label: 'Copernicus Fetch', icon: Layers },
    { label: 'Spectral Alignment', icon: Cpu },
    { label: 'Neural Inference', icon: Activity },
    { label: 'Geodesic Quant', icon: ShieldCheck },
  ];

  return (
    <div className="p-5 rounded-2xl bg-[#081420] border border-[#153245] space-y-5 shadow-2xl">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#153245] pb-3.5">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-cyan-950/80 border border-cyan-800/60 text-cyan-400">
            <Activity className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
              Backend Execution Pipeline (§5 Contract)
            </h3>
            <p className="text-[10px] text-slate-400 font-mono">
              Agentic Orchestration & Latency Profile
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs font-mono">
          <div className="px-2.5 py-1 rounded-md bg-[#040911] border border-[#153245] flex items-center gap-1.5 text-slate-300">
            <Clock className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-slate-400">Total:</span>
            <span className="text-cyan-300 font-bold">{Number(totalTime).toFixed(1)} ms</span>
          </div>
          <span className="px-2 py-1 rounded-md bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 text-[10px] font-semibold">
            {conf == null ? "—" : `${(conf * 100).toFixed(1)}% Conf`}
          </span>
        </div>
      </div>

      {/* Sequential Pipeline Flow Diagram */}
      <div className="p-3 rounded-xl bg-[#040911]/90 border border-[#153245] space-y-2">
        <span className="text-[10px] font-mono uppercase tracking-widest text-slate-400 block">
          Planetary Reasoning Flow:
        </span>
        <div className="flex items-center justify-between gap-1 overflow-x-auto py-1">
          {pipelineFlow.map((stage, idx) => {
            const Icon = stage.icon;
            const isCompleted = idx < steps.length || steps.length > 0;
            return (
              <React.Fragment key={idx}>
                <div
                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[11px] font-mono whitespace-nowrap transition-all ${
                    isCompleted
                      ? 'bg-cyan-950/40 border-cyan-700/60 text-cyan-300'
                      : 'bg-slate-900/40 border-slate-800 text-slate-500'
                  }`}
                >
                  <Icon className="w-3 h-3 text-cyan-400" />
                  <span>{stage.label}</span>
                </div>
                {idx < pipelineFlow.length - 1 && (
                  <ArrowRight className="w-3 h-3 text-slate-600 shrink-0" />
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* Answer Preview Box */}
      {verifiedAnswer && (
        <div className="p-3.5 rounded-xl bg-gradient-to-r from-cyan-950/20 via-[#081420] to-slate-950/60 border border-cyan-800/40 space-y-1.5">
          <div className="flex items-center justify-between text-[11px] font-mono">
            <span className="text-cyan-300 font-semibold flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              Grounded Model Synthesis
            </span>
            <span className="text-slate-400 text-[10px]">Task: {task}</span>
          </div>
          <p className="text-xs text-slate-200 leading-relaxed font-sans line-clamp-3">
            {verifiedAnswer}
          </p>
        </div>
      )}

      {/* Sequential Tool Execution Steps */}
      <div className="space-y-2">
        <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 block">
          Tool Steps Telemetry ({steps.length} steps):
        </span>

        <div className="space-y-2">
          {steps.map((step, idx) => {
            const isExpanded = expandedStep === idx;
            const latencyPct = totalTime > 0 ? Math.min(100, Math.round((step.latency_ms / totalTime) * 100)) : 20;

            return (
              <div
                key={idx}
                className="rounded-xl bg-[#040911] border border-[#153245] hover:border-cyan-700/50 transition-all overflow-hidden"
              >
                <div
                  onClick={() => setExpandedStep(isExpanded ? null : idx)}
                  className="p-3 flex items-center justify-between gap-3 cursor-pointer select-none text-xs font-mono"
                >
                  <div className="flex items-center gap-2.5">
                    <div className="w-5 h-5 rounded-full bg-cyan-950 border border-cyan-700 text-cyan-300 flex items-center justify-center font-bold text-[10px]">
                      {step.step}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-100">{step.tool}</span>
                        <span className="text-[10px] text-cyan-400 bg-cyan-950/60 px-1.5 py-0.5 rounded border border-cyan-800/40">
                          {step.version}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    <div className="hidden sm:flex flex-col items-end text-[10px] text-slate-400">
                      <span>{Number(step.latency_ms).toFixed(1)} ms</span>
                      <div className="w-16 h-1 rounded-full bg-slate-800 overflow-hidden mt-0.5">
                        <div
                          className="h-full bg-cyan-400 rounded-full"
                          style={{ width: `${latencyPct}%` }}
                        />
                      </div>
                    </div>
                    <span className="px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-400 text-[10px] border border-emerald-800/40">
                      {step.status}
                    </span>
                    {isExpanded ? (
                      <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
                    )}
                  </div>
                </div>

                {/* Collapsible Tool Parameters & Diagnostic Inspector */}
                {isExpanded && (
                  <div className="p-3 border-t border-[#153245] bg-slate-950/70 text-xs font-mono space-y-2">
                    <div className="flex items-center gap-1.5 text-slate-400 text-[11px]">
                      <Terminal className="w-3 h-3 text-cyan-400" />
                      <span>Step {step.step} Parameters & Payload:</span>
                    </div>
                    <pre className="p-2.5 rounded-lg bg-[#040911] border border-slate-800 text-[11px] text-cyan-300 overflow-x-auto leading-relaxed">
                      {JSON.stringify(step.params, null, 2) || '{}'}
                    </pre>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

