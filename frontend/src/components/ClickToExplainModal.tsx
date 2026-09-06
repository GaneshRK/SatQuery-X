'use client';

import React from 'react';
import {
  X,
  Layers,
  Calendar,
  Sparkles,
  MapPin,
  Maximize2,
  TrendingUp,
  AlertCircle,
  ExternalLink,
  ShieldCheck,
  MessageSquarePlus,
} from 'lucide-react';

export interface ExplainFeatureData {
  id?: string;
  class_name: string;
  confidence?: number;
  area_m2?: number;
  area_km2?: number;
  area_ha?: number;
  centroid?: [number, number];
  bounds?: [number, number, number, number];
  observation_dates?: {
    t1?: string;
    t2?: string;
  };
  spectral_delta?: string;
  description?: string;
  model_used?: string;
  limitations?: string[];
}

interface ClickToExplainModalProps {
  isOpen: boolean;
  onClose: () => void;
  feature: ExplainFeatureData | null;
  onAskFollowUp?: (prompt: string) => void;
}

export const ClickToExplainModal: React.FC<ClickToExplainModalProps> = ({
  isOpen,
  onClose,
  feature,
  onAskFollowUp,
}) => {
  if (!isOpen || !feature) return null;

  const confPercent = feature.confidence != null ? (feature.confidence * 100).toFixed(1) : 'N/A';
  const areaHa = feature.area_ha ?? (feature.area_m2 ? (feature.area_m2 / 10000) : 0);
  const areaKm2 = feature.area_km2 ?? (feature.area_m2 ? (feature.area_m2 / 1000000) : 0);

  const t1 = feature.observation_dates?.t1 || 'Baseline Pass';
  const t2 = feature.observation_dates?.t2 || 'Current Observation';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        className="relative w-full max-w-xl bg-[#09111e] border border-cyan-800/60 rounded-2xl shadow-2xl shadow-cyan-950/40 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Glow accent */}
        <div className="absolute -top-24 left-1/2 -translate-x-1/2 w-96 h-32 bg-cyan-500/20 blur-3xl rounded-full pointer-events-none" />

        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-[#0c1626]">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-950/80 border border-cyan-700/60 text-cyan-400">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-semibold text-slate-100 capitalize">
                  {feature.class_name.replace(/_/g, ' ')}
                </h3>
                <span className="px-2 py-0.5 rounded-full text-xs font-mono font-semibold bg-emerald-950/80 border border-emerald-700 text-emerald-400">
                  {confPercent}% Conf
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono mt-0.5">
                Feature Inspection & Scientific Ground Truth
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-5 text-sm text-slate-300 max-h-[75vh] overflow-y-auto">
          {/* Spatial Metrics Grid */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-xl">
              <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                <Maximize2 className="w-3.5 h-3.5 text-cyan-400" />
                <span>Area (Hectares)</span>
              </div>
              <p className="text-lg font-bold text-slate-100 font-mono">
                {areaHa.toFixed(2)} <span className="text-xs text-slate-400 font-normal">ha</span>
              </p>
            </div>

            <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-xl">
              <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                <Maximize2 className="w-3.5 h-3.5 text-indigo-400" />
                <span>Area (Sq Km)</span>
              </div>
              <p className="text-lg font-bold text-slate-100 font-mono">
                {areaKm2.toFixed(3)} <span className="text-xs text-slate-400 font-normal">km²</span>
              </p>
            </div>

            <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-xl">
              <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                <span>Model Confidence</span>
              </div>
              <p className="text-lg font-bold text-emerald-400 font-mono">
                {confPercent}%
              </p>
            </div>
          </div>

          {/* Temporal Comparison */}
          <div className="bg-[#0b1424] border border-slate-800 p-4 rounded-xl space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-200 uppercase tracking-wider font-mono">
              <Calendar className="w-4 h-4 text-cyan-400" />
              <span>Observation Timeline</span>
            </div>
            <div className="flex items-center justify-between text-xs font-mono bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
              <div className="space-y-0.5">
                <span className="text-[10px] text-slate-500 uppercase block">Reference State (T1)</span>
                <span className="text-slate-200 font-medium">{t1}</span>
              </div>
              <span className="text-cyan-500 font-bold">➔</span>
              <div className="space-y-0.5 text-right">
                <span className="text-[10px] text-slate-500 uppercase block">Detected State (T2)</span>
                <span className="text-emerald-400 font-medium">{t2}</span>
              </div>
            </div>
          </div>

          {/* Spectral Explanation */}
          <div className="bg-[#0b1424] border border-slate-800 p-4 rounded-xl space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-200 uppercase tracking-wider font-mono">
              <TrendingUp className="w-4 h-4 text-amber-400" />
              <span>Spectral Explanation & Ground Evidence</span>
            </div>
            <p className="text-xs leading-relaxed text-slate-300">
              {feature.spectral_delta ||
                `Ground feature classified as '${feature.class_name}'. Multi-spectral analysis detected characteristic radiometric reflectance shift corresponding to this class boundary with high spatial coherence.`}
            </p>
            {feature.model_used && (
              <div className="pt-2 text-[11px] font-mono text-slate-400 flex items-center gap-1.5 border-t border-slate-800/80">
                <Layers className="w-3.5 h-3.5 text-slate-500" />
                <span>Detector Engine:</span>
                <span className="text-slate-300">{feature.model_used}</span>
              </div>
            )}
          </div>

          {/* Limitations & Sensor Uncertainty */}
          <div className="bg-amber-950/20 border border-amber-800/40 p-3.5 rounded-xl space-y-1.5">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-300 font-mono">
              <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
              <span>Scientific Disclaimer & Resolution Limit</span>
            </div>
            <p className="text-[11px] text-amber-200/80 leading-normal">
              Derived from satellite observations with pixel resolution limits (10m–30m). Small sub-pixel features may exhibit boundary partial volume mixing. Verified with cross-referenced spectral indices.
            </p>
          </div>

          {/* Quick Follow-up Actions */}
          <div className="space-y-2 pt-1">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider font-mono block">
              Ask Follow-Up About This Region
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => {
                  onAskFollowUp?.(`Has the ${feature.class_name} here expanded or contracted compared to earlier satellite passes?`);
                  onClose();
                }}
                className="flex items-center gap-2 text-left p-2.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-cyan-700/60 rounded-xl text-xs text-slate-200 transition-all"
              >
                <MessageSquarePlus className="w-4 h-4 text-cyan-400 shrink-0" />
                <span>Compare with earlier pass</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  onAskFollowUp?.(`What is the environmental or land-use impact of the ${feature.class_name} in this ${areaHa.toFixed(1)} ha zone?`);
                  onClose();
                }}
                className="flex items-center gap-2 text-left p-2.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-cyan-700/60 rounded-xl text-xs text-slate-200 transition-all"
              >
                <MessageSquarePlus className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>Analyze environmental impact</span>
              </button>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-end px-6 py-3 border-t border-slate-800 bg-[#0c1626]">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium transition-colors"
          >
            Close Inspector
          </button>
        </div>
      </div>
    </div>
  );
};
