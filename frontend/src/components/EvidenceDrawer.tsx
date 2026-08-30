'use client';

import React from 'react';
import { Layers, MapPin, BarChart3, Code, Maximize, Check } from 'lucide-react';
import { EvidenceOutput } from '@/types';

interface EvidenceDrawerProps {
  evidence: EvidenceOutput | null;
}

export const EvidenceDrawer: React.FC<EvidenceDrawerProps> = ({ evidence }) => {
  if (!evidence) {
    return (
      <div className="bg-surface border border-border rounded-xl p-6 text-center space-y-2">
        <Layers className="w-6 h-6 text-slate-600 mx-auto" />
        <h4 className="text-sm font-medium text-slate-400">Evidence Panel</h4>
        <p className="text-xs text-slate-600 font-mono">No evidence artifacts generated yet.</p>
      </div>
    );
  }

  const hasArea = evidence.quantified_area_km2 !== undefined && evidence.quantified_area_km2 !== null;

  return (
    <div className="bg-surface border border-border rounded-xl p-5 space-y-4 shadow-xl">
      <div className="flex items-center justify-between border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-cyan-400" />
          <h3 className="font-semibold text-sm text-white">Geospatial Evidence & Quantification</h3>
        </div>
        <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-800/40">
          GeoJSON Grounded
        </span>
      </div>

      {/* Metric Cards (Quantified Area km² / ha / %) */}
      {hasArea && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-slate-950/80 p-3 rounded-lg border border-slate-800 space-y-1">
            <span className="text-[10px] font-mono uppercase text-slate-400">Changed Area</span>
            <p className="text-base font-bold text-white">{evidence.quantified_area_km2} <span className="text-xs font-normal text-slate-400">km²</span></p>
          </div>
          <div className="bg-slate-950/80 p-3 rounded-lg border border-slate-800 space-y-1">
            <span className="text-[10px] font-mono uppercase text-slate-400">Hectares</span>
            <p className="text-base font-bold text-white">{evidence.quantified_area_hectares} <span className="text-xs font-normal text-slate-400">ha</span></p>
          </div>
          <div className="bg-slate-950/80 p-3 rounded-lg border border-slate-800 space-y-1">
            <span className="text-[10px] font-mono uppercase text-slate-400">Coverage</span>
            <p className="text-base font-bold text-emerald-400">{evidence.change_percentage}%</p>
          </div>
        </div>
      )}

      {/* Detected Bounding Box Coordinates List */}
      {evidence.bboxes && evidence.bboxes.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-mono text-slate-400 uppercase tracking-wider">
            Grounded Region Coordinates ({evidence.bboxes.length}):
          </p>
          <div className="max-h-40 overflow-y-auto space-y-1.5 pr-1">
            {evidence.bboxes.map((box, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between p-2 rounded bg-slate-950/60 border border-slate-800 text-[11px] font-mono"
              >
                <div className="flex items-center gap-2">
                  <MapPin className="w-3 h-3 text-yellow-400" />
                  <span className="text-yellow-400 font-semibold">{box.label || 'region'}</span>
                  <span className="text-slate-400">
                    [{box.x1.toFixed(0)}, {box.y1.toFixed(0)}, {box.x2.toFixed(0)}, {box.y2.toFixed(0)}]
                  </span>
                </div>
                <span className="text-emerald-400 font-semibold">
                  {box.confidence ? `${Math.round(box.confidence * 100)}%` : '75%'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* GeoJSON Polygon Excerpt */}
      {evidence.geojson && evidence.geojson.length > 0 && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-mono text-slate-400 flex items-center gap-1.5">
              <Code className="w-3 h-3 text-blue-400" />
              GeoJSON Vector Export (SRID: 4326)
            </span>
            <span className="text-[10px] font-mono text-slate-500">{evidence.geojson.length} Feature(s)</span>
          </div>
          <pre className="bg-slate-950 p-2.5 rounded text-[10px] font-mono text-slate-400 overflow-x-auto border border-slate-900 max-h-24">
            {JSON.stringify(evidence.geojson[0], null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};
