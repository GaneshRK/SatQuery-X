'use client';

import React, { useState } from 'react';
import { ConversationContext } from '@/types';
import {
  MapPin,
  Target,
  Calendar,
  RotateCcw,
  Sliders,
  Sparkles,
  ChevronDown,
  Layers,
  Info
} from 'lucide-react';

interface ContextBarProps {
  context: ConversationContext | null;
  onResetContext: () => Promise<void>;
  onSelectPrompt?: (prompt: string) => void;
  isExpertMode?: boolean;
  onToggleExpertMode?: (expert: boolean) => void;
  className?: string;
}

export const ContextBar: React.FC<ContextBarProps> = ({
  context,
  onResetContext,
  onSelectPrompt,
  isExpertMode = false,
  onToggleExpertMode,
  className = '',
}) => {
  const [isResetting, setIsResetting] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  const aoiName = context?.active_region?.name || 'Global Earth View';
  const focusTarget = context?.active_focus || 'Multi-Spectral Ground';
  const t1 = context?.active_observation_pair?.t1_date;
  const t2 = context?.active_observation_pair?.t2_date;
  const timelineLabel = t1 && t2 ? `${t1} → ${t2}` : t1 || 'Latest Pass';
  const entitiesCount = context?.active_entities?.length || 0;
  const turnCount = context?.conversation_history?.length || 0;

  const handleReset = async () => {
    setIsResetting(true);
    try {
      await onResetContext();
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <div className={`relative bg-gradient-to-r from-[#09111e]/90 via-[#0d1728]/90 to-[#09111e]/90 backdrop-blur-md border border-slate-800/80 rounded-xl px-4 py-2.5 shadow-lg shadow-black/20 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Left: Active Context Pills */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5 text-xs font-mono font-semibold text-cyan-400 uppercase tracking-wider bg-cyan-950/60 border border-cyan-800/50 px-2 py-0.5 rounded-md">
            <Sparkles className="w-3 h-3 text-cyan-400 animate-pulse" />
            <span>AI Memory</span>
          </div>

          {/* AOI Pill */}
          <div
            className="flex items-center gap-1.5 bg-slate-900/80 hover:bg-slate-800 border border-slate-800 px-2.5 py-1 rounded-lg text-xs cursor-pointer transition-colors"
            title="Active Geographic Region of Interest"
            onClick={() => onSelectPrompt?.(`Focus on ${aoiName} and summarize observed conditions.`)}
          >
            <MapPin className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-slate-400 font-mono text-[11px]">AOI:</span>
            <span className="text-slate-200 font-medium truncate max-w-[140px]">{aoiName}</span>
          </div>

          {/* Focus Target Pill */}
          <div
            className="flex items-center gap-1.5 bg-slate-900/80 hover:bg-slate-800 border border-slate-800 px-2.5 py-1 rounded-lg text-xs cursor-pointer transition-colors"
            title="Current Subject Matter Focus"
            onClick={() => onSelectPrompt?.(`What is the current status of ${focusTarget} here?`)}
          >
            <Target className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-slate-400 font-mono text-[11px]">Focus:</span>
            <span className="text-slate-200 font-medium capitalize">{focusTarget.replace('_', ' ')}</span>
          </div>

          {/* Timeline Pill */}
          <div
            className="flex items-center gap-1.5 bg-slate-900/80 hover:bg-slate-800 border border-slate-800 px-2.5 py-1 rounded-lg text-xs cursor-pointer transition-colors"
            title="Active Temporal Observation Window"
            onClick={() => onSelectPrompt?.(`Show observation comparison for ${timelineLabel}.`)}
          >
            <Calendar className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-slate-400 font-mono text-[11px]">Time:</span>
            <span className="text-slate-200 font-medium font-mono text-[11px]">{timelineLabel}</span>
          </div>

          {/* Layers Pill */}
          {context?.active_layers && context.active_layers.length > 0 && (
            <div className="hidden xl:flex items-center gap-1.5 bg-slate-900/80 border border-slate-800 px-2.5 py-1 rounded-lg text-xs">
              <Layers className="w-3.5 h-3.5 text-purple-400" />
              <span className="text-slate-400 font-mono text-[11px]">Layers:</span>
              <span className="text-slate-300 font-mono text-[11px]">{context.active_layers.join(', ')}</span>
            </div>
          )}
        </div>

        {/* Right: Controls & Context Reset */}
        <div className="flex items-center gap-2">
          {/* Simple vs Expert Toggle */}
          {onToggleExpertMode && (
            <div className="flex items-center bg-slate-900/90 border border-slate-800 rounded-lg p-0.5 text-xs font-mono">
              <button
                type="button"
                onClick={() => onToggleExpertMode(false)}
                className={`px-2.5 py-1 rounded-md transition-all ${
                  !isExpertMode
                    ? 'bg-slate-800 text-slate-100 font-medium shadow-xs'
                    : 'text-slate-400 hover:text-slate-300'
                }`}
              >
                Simple
              </button>
              <button
                type="button"
                onClick={() => onToggleExpertMode(true)}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-md transition-all ${
                  isExpertMode
                    ? 'bg-cyan-950 text-cyan-300 border border-cyan-800 font-medium shadow-xs'
                    : 'text-slate-400 hover:text-slate-300'
                }`}
              >
                <Sliders className="w-3 h-3" />
                <span>Expert</span>
              </button>
            </div>
          )}

          {/* Memory Details Toggle */}
          <button
            type="button"
            onClick={() => setShowDetails(!showDetails)}
            className="flex items-center gap-1 px-2 py-1 bg-slate-900/80 hover:bg-slate-800 border border-slate-800 rounded-lg text-xs text-slate-300 transition-colors"
            title="Inspect full conversation state and history"
          >
            <Info className="w-3.5 h-3.5 text-slate-400" />
            <span className="font-mono text-[11px]">{turnCount} Turns</span>
            <ChevronDown className={`w-3 h-3 transition-transform ${showDetails ? 'rotate-180' : ''}`} />
          </button>

          {/* Reset Context Button */}
          <button
            type="button"
            onClick={handleReset}
            disabled={isResetting}
            className="flex items-center gap-1.5 px-2.5 py-1 bg-rose-950/40 hover:bg-rose-900/60 border border-rose-800/60 text-rose-300 rounded-lg text-xs font-medium transition-all disabled:opacity-50 shadow-xs"
            title="Reset conversation context memory while preserving imagery"
          >
            <RotateCcw className={`w-3 h-3 ${isResetting ? 'animate-spin' : ''}`} />
            <span className="font-mono text-[11px]">Reset Memory</span>
          </button>
        </div>
      </div>

      {/* Expanded Details Drawer */}
      {showDetails && (
        <div className="mt-3 pt-3 border-t border-slate-800/80 text-xs text-slate-300 grid grid-cols-1 md:grid-cols-3 gap-4 font-mono bg-slate-950/60 p-3 rounded-lg border border-slate-800/50">
          <div>
            <span className="text-slate-500 font-semibold uppercase text-[10px] block mb-1">Tracked Entities</span>
            {entitiesCount > 0 ? (
              <ul className="space-y-1">
                {context?.active_entities?.map((ent, idx) => (
                  <li key={idx} className="flex justify-between items-center text-slate-300">
                    <span className="capitalize">{ent.class_name.replace('_', ' ')}</span>
                    <span className="text-slate-400 text-[11px]">
                      {ent.area_ha ? `${ent.area_ha.toFixed(1)} ha` : ''} {ent.confidence ? `(${(ent.confidence * 100).toFixed(0)}%)` : ''}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <span className="text-slate-600 italic">No localized entities pinned yet.</span>
            )}
          </div>

          <div>
            <span className="text-slate-500 font-semibold uppercase text-[10px] block mb-1">Visual Coordinates</span>
            {context?.current_visual_state?.center ? (
              <p className="text-slate-300 text-[11px]">
                Center: [{context.current_visual_state.center[0].toFixed(4)}, {context.current_visual_state.center[1].toFixed(4)}]
                <br />
                Zoom: {context.current_visual_state.zoom || 'auto'}
              </p>
            ) : (
              <span className="text-slate-600 italic">Viewport in initial position.</span>
            )}
          </div>

          <div>
            <span className="text-slate-500 font-semibold uppercase text-[10px] block mb-1">Recent Context Thread</span>
            {turnCount > 0 ? (
              <div className="space-y-1 max-h-20 overflow-y-auto pr-1">
                {context?.conversation_history?.slice(-3).map((item, idx) => (
                  <div key={idx} className="text-[11px] truncate text-slate-300">
                    <span className="text-cyan-400 font-bold">#{item.turn}:</span> {item.user_query}
                  </div>
                ))}
              </div>
            ) : (
              <span className="text-slate-600 italic">Fresh conversation thread.</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
