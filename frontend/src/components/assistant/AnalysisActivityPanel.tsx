"use client";

import React from "react";
import { Loader2, CheckCircle2, Zap } from "lucide-react";
import { Card } from "../ui/Card";

export interface AnalysisActivityPanelProps {
  currentStage?: string;
  stagesCompleted?: string[];
  isLoading?: boolean;
}

const DEFAULT_STAGES = [
  "Understanding natural language geospatial intent",
  "Resolving target entity coordinates and bounding box",
  "Querying Copernicus Sentinel STAC archive",
  "Ingesting calibrated surface reflectance rasters",
  "Executing ChangeFormer bi-temporal feature differencing",
  "Delineating change boundaries and computing cluster centroids",
  "Projecting metric integration to EPSG:6933 Equal-Area CRS",
  "Synthesizing scientific proof chain and generating response",
];

export const AnalysisActivityPanel: React.FC<AnalysisActivityPanelProps> = ({
  currentStage,
  stagesCompleted = [],
  isLoading = true,
}) => {
  return (
    <Card variant="glass" padding="md" className="border-cyan-500/30 animate-in fade-in duration-200">
      <div className="flex items-center gap-2 mb-3 pb-2 border-b border-slate-800">
        <Zap className="w-4 h-4 text-cyan-400 animate-pulse" />
        <h4 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
          AI Analysis Activity
        </h4>
      </div>

      <div className="space-y-2 text-xs font-mono">
        {DEFAULT_STAGES.map((stage, idx) => {
          const isDone = stagesCompleted.includes(stage) || (!isLoading && idx < 6);
          const isCurrent = isLoading && (currentStage === stage || (!currentStage && idx === 3));

          return (
            <div
              key={idx}
              className={`flex items-center gap-2.5 p-1.5 rounded-lg transition-colors ${
                isCurrent
                  ? "bg-cyan-950/40 text-cyan-200 border border-cyan-800/50"
                  : isDone
                  ? "text-slate-300"
                  : "text-slate-600"
              }`}
            >
              {isDone ? (
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              ) : isCurrent ? (
                <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin shrink-0" />
              ) : (
                <div className="w-3.5 h-3.5 rounded-full border border-slate-700 shrink-0" />
              )}
              <span className="truncate">{stage}</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
};
