'use client';

import React from 'react';
import { Activity, Clock, Cpu, CheckCircle2, AlertTriangle, ShieldCheck, ChevronRight } from 'lucide-react';
import { ExecutionTrace } from '@/types';

interface ExecutionTraceTimelineProps {
  trace: ExecutionTrace | null;
}

export const ExecutionTraceTimeline: React.FC<ExecutionTraceTimelineProps> = ({ trace }) => {
  if (!trace) {
    return (
      <div className="bg-surface border border-border rounded-xl p-6 text-center space-y-2">
        <Activity className="w-6 h-6 text-slate-600 mx-auto" />
        <h4 className="text-sm font-medium text-slate-400">Execution Trace Awaiting Dispatch</h4>
        <p className="text-xs text-slate-600 font-mono">Submit a query to inspect agentic tool orchestration & latency profile.</p>
      </div>
    );
  }

  return (
    <div className="bg-surface border border-border rounded-xl p-5 space-y-4 shadow-xl">
      <div className="flex items-center justify-between border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-blue-400" />
          <h3 className="font-semibold text-sm text-white">Auditable Execution Trace (§5 Contract)</h3>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono">
          <span className="text-slate-400">Total Latency:</span>
          <span className="text-blue-400 font-bold">{trace.timings_ms.total?.toFixed(1) || 0} ms</span>
        </div>
      </div>

      {/* Answer & Grounded Response Box */}
      <div className="p-4 rounded-lg bg-gradient-to-r from-blue-950/40 to-slate-900/80 border border-blue-500/30 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-mono uppercase text-blue-400 font-semibold tracking-wider flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            Verified Answer (Confidence: {(trace.confidence * 100).toFixed(1)}%)
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
            Task: {trace.task_classification}
          </span>
        </div>
        <p className="text-sm font-medium text-white leading-relaxed">{trace.answer}</p>
      </div>

      {/* Sequential Tool Steps Timeline */}
      <div className="space-y-2.5">
        <p className="text-xs font-mono text-slate-400 uppercase tracking-wider">Planned & Executed Tool Sequence:</p>
        <div className="grid gap-2">
          {trace.plan.map((step, idx) => {
            const stepLatency = trace.timings_ms[`step${step.step}`] || 0;
            return (
              <div
                key={idx}
                className="flex items-center justify-between p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-xs font-mono hover:border-slate-700 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="w-5 h-5 rounded-full bg-blue-600/20 border border-blue-500/40 text-blue-400 flex items-center justify-center font-bold text-[10px]">
                    {step.step}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-white">{step.tool}</span>
                      <span className="text-[10px] text-slate-400 bg-slate-900 px-1.5 py-0.2 rounded border border-slate-800">
                        {step.version}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-500 truncate max-w-md mt-0.5">
                      Params: {JSON.stringify(step.params)}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-slate-400 flex items-center gap-1 text-[11px]">
                    <Clock className="w-3 h-3 text-slate-500" />
                    {stepLatency.toFixed(1)} ms
                  </span>
                  <span className="px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-400 text-[10px] border border-emerald-800/40">
                    STATUS_OK
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
