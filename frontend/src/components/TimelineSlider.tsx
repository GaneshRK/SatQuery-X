'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  ChevronLeft,
  ChevronRight,
  Calendar,
  Cloud,
  Layers,
  Sparkles,
  RefreshCw,
  GitCompare,
  TrendingDown,
  Info,
} from 'lucide-react';
import { TemporalObservationData, AOITimelineResponse } from '@/services/satellite';

interface TimelineSliderProps {
  timeline: AOITimelineResponse | null;
  selectedObsIndex: number;
  onSelectObservation: (index: number) => void;
  onCompare: (beforeIndex: number, afterIndex: number) => void;
  onRunChangeDetection: () => void;
  isAnalyzing?: boolean;
}

export const TimelineSlider: React.FC<TimelineSliderProps> = ({
  timeline,
  selectedObsIndex,
  onSelectObservation,
  onCompare,
  onRunChangeDetection,
  isAnalyzing = false,
}) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1200); // ms per step
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const observations = timeline?.observations || [];
  const currentObs = observations[selectedObsIndex] || null;

  // Auto-playback loop
  useEffect(() => {
    if (isPlaying && observations.length > 0) {
      timerRef.current = setInterval(() => {
        onSelectObservation((selectedObsIndex + 1) % observations.length);
      }, playbackSpeed);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPlaying, selectedObsIndex, observations.length, playbackSpeed, onSelectObservation]);

  if (!timeline || observations.length === 0) {
    return (
      <div className="bg-[#0b1322]/90 border border-slate-800 rounded-xl p-4 text-center backdrop-blur-md">
        <div className="flex items-center justify-center gap-2 text-slate-400 text-xs">
          <RefreshCw className="w-3.5 h-3.5 animate-spin text-cyan-400" />
          <span>Synchronizing multi-decadal satellite observation timeline (2016–2026)...</span>
        </div>
      </div>
    );
  }

  const handlePrev = () => {
    if (selectedObsIndex > 0) {
      onSelectObservation(selectedObsIndex - 1);
    }
  };

  const handleNext = () => {
    if (selectedObsIndex < observations.length - 1) {
      onSelectObservation(selectedObsIndex + 1);
    }
  };

  return (
    <div className="bg-[#091120]/95 border border-slate-800/80 rounded-xl p-4 backdrop-blur-md shadow-2xl flex flex-col gap-3">
      {/* Header / Active Observation Metadata */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs border-b border-slate-800/60 pb-2.5">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
          </span>
          <span className="font-semibold text-slate-200 tracking-wide uppercase text-[11px]">
            Temporal Earth Timeline
          </span>
          <span className="bg-cyan-950/80 text-cyan-400 border border-cyan-800/50 px-2 py-0.5 rounded text-[10px] font-mono">
            {timeline.aoi_name}
          </span>
          <span className="text-slate-500 font-mono text-[10px]">
            {observations.length} Observations Indexed
          </span>
        </div>

        {/* Selected observation badge */}
        {currentObs && (
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 bg-slate-900/90 border border-slate-700/60 px-2.5 py-1 rounded-md">
              <Calendar className="w-3 h-3 text-cyan-400" />
              <span className="text-cyan-300 font-mono font-medium">{currentObs.observation_date}</span>
            </div>
            <div className="flex items-center gap-1 bg-slate-900/90 border border-slate-700/60 px-2 py-1 rounded-md text-slate-300 font-mono">
              <Cloud className="w-3 h-3 text-amber-400" />
              <span>{currentObs.cloud_cover !== null ? `${currentObs.cloud_cover.toFixed(1)}%` : '0.0%'}</span>
            </div>
            <span className="bg-indigo-950/80 text-indigo-300 border border-indigo-800/50 px-2 py-0.5 rounded text-[10px] font-mono">
              {currentObs.platform}
            </span>
            <span className="bg-emerald-950/80 text-emerald-400 border border-emerald-800/50 px-2 py-0.5 rounded text-[10px] font-mono">
              Q: {(currentObs.quality_score * 100).toFixed(0)}%
            </span>
          </div>
        )}
      </div>

      {/* Interactive Timeline Track */}
      <div className="relative w-full py-1">
        {/* Track Line */}
        <div className="h-1.5 w-full bg-slate-800/80 rounded-full relative overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-cyan-500 via-indigo-500 to-emerald-400 transition-all duration-300 rounded-full"
            style={{
              width: `${((selectedObsIndex + 1) / observations.length) * 100}%`,
            }}
          />
        </div>

        {/* Observation Markers */}
        <div className="flex justify-between items-center mt-2 px-1">
          {observations.map((obs, idx) => {
            const isSelected = idx === selectedObsIndex;
            return (
              <button
                key={obs.id || idx}
                onClick={() => onSelectObservation(idx)}
                title={`${obs.observation_date} - ${obs.platform} (${obs.cloud_cover?.toFixed(1) || 0}% cloud)`}
                className={`group flex flex-col items-center focus:outline-none transition-transform ${
                  isSelected ? 'scale-110 z-10' : 'opacity-70 hover:opacity-100'
                }`}
              >
                <div
                  className={`w-3.5 h-3.5 rounded-full border-2 transition-all ${
                    isSelected
                      ? 'bg-cyan-400 border-white shadow-[0_0_10px_rgba(6,182,212,0.8)]'
                      : 'bg-slate-700 border-slate-900 group-hover:bg-slate-500'
                  }`}
                />
                <span
                  className={`text-[9px] font-mono mt-1 ${
                    isSelected ? 'text-cyan-300 font-bold' : 'text-slate-500 group-hover:text-slate-300'
                  }`}
                >
                  {obs.year}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Control Actions Row */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
        {/* Playback Controls */}
        <div className="flex items-center gap-1.5 bg-slate-900/80 border border-slate-800 px-2 py-1 rounded-lg">
          <button
            onClick={() => onSelectObservation(0)}
            title="Earliest Observation"
            className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded transition-colors"
          >
            <SkipBack className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handlePrev}
            disabled={selectedObsIndex === 0}
            title="Previous Observation"
            className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-200 disabled:opacity-30 rounded transition-colors"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            title={isPlaying ? 'Pause Playback' : 'Play Timeline Time-Lapse'}
            className="px-2.5 py-1 bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold rounded flex items-center gap-1.5 transition-colors text-xs"
          >
            {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
            <span>{isPlaying ? 'Pause' : 'Play'}</span>
          </button>
          <button
            onClick={handleNext}
            disabled={selectedObsIndex === observations.length - 1}
            title="Next Observation"
            className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-200 disabled:opacity-30 rounded transition-colors"
          >
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => onSelectObservation(observations.length - 1)}
            title="Latest Observation"
            className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded transition-colors"
          >
            <SkipForward className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Playback Speed selector */}
        <div className="flex items-center gap-1 text-[11px] text-slate-400">
          <span>Speed:</span>
          {[2000, 1200, 600].map((speed) => (
            <button
              key={speed}
              onClick={() => setPlaybackSpeed(speed)}
              className={`px-1.5 py-0.5 rounded font-mono text-[10px] ${
                playbackSpeed === speed
                  ? 'bg-slate-700 text-cyan-300 font-semibold'
                  : 'hover:bg-slate-800 text-slate-500'
              }`}
            >
              {speed === 2000 ? '0.5x' : speed === 1200 ? '1x' : '2x'}
            </button>
          ))}
        </div>

        {/* Intelligence Actions: Compare & Detect Change */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              if (observations.length >= 2) {
                onCompare(0, observations.length - 1);
              }
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs rounded-lg transition-colors"
          >
            <GitCompare className="w-3.5 h-3.5 text-indigo-400" />
            <span>Compare (Earliest vs Latest)</span>
          </button>

          <button
            onClick={onRunChangeDetection}
            disabled={isAnalyzing}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-slate-950 font-semibold text-xs rounded-lg shadow-lg shadow-emerald-950/30 transition-all disabled:opacity-50"
          >
            {isAnalyzing ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5" />
            )}
            <span>What Changed?</span>
          </button>
        </div>
      </div>

      {/* Transparent Data Gap & Scientific Honesty Warning */}
      {timeline.data_gaps && timeline.data_gaps.length > 0 && (
        <div className="flex items-center gap-1.5 text-[10px] text-amber-400/80 bg-amber-950/20 border border-amber-900/30 px-2 py-1 rounded">
          <Info className="w-3 h-3 text-amber-400 shrink-0" />
          <span>
            Observation notice: No cloud-free satellite overpasses catalogued for years [
            {timeline.data_gaps.join(', ')}]. Satellite data is never interpolated or simulated.
          </span>
        </div>
      )}
    </div>
  );
};
