'use client';

import React, { useState } from 'react';
import { X, Search, Satellite, Calendar, Cloud, Check, Loader2, MapPin, Layers } from 'lucide-react';
import {
  searchSatelliteCandidates,
  getCandidates,
  selectCandidate,
  CandidateData,
} from '@/services/satellite';

interface SatelliteSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string;
  onSceneIngested: () => void;
}

const REGION_PRESETS = [
  {
    name: 'Brahmaputra Basin, Assam',
    aoi: {
      type: 'Polygon',
      coordinates: [
        [
          [93.0, 26.5],
          [93.25, 26.5],
          [93.25, 26.75],
          [93.0, 26.75],
          [93.0, 26.5],
        ],
      ],
    },
  },
  {
    name: 'New Delhi National Capital Region',
    aoi: {
      type: 'Polygon',
      coordinates: [
        [
          [77.0, 28.5],
          [77.3, 28.5],
          [77.3, 28.8],
          [77.0, 28.8],
          [77.0, 28.5],
        ],
      ],
    },
  },
  {
    name: 'Pollachi Agricultural Belt, Tamil Nadu',
    aoi: {
      type: 'Polygon',
      coordinates: [
        [
          [76.9, 10.6],
          [77.1, 10.6],
          [77.1, 10.8],
          [76.9, 10.8],
          [76.9, 10.6],
        ],
      ],
    },
  },
];

export const SatelliteSearchModal: React.FC<SatelliteSearchModalProps> = ({
  isOpen,
  onClose,
  sessionId,
  onSceneIngested,
}) => {
  const [selectedRegion, setSelectedRegion] = useState(REGION_PRESETS[0]);
  const [sensor, setSensor] = useState('SENTINEL-2');
  const [dateStart, setDateStart] = useState('2024-07-01');
  const [dateEnd, setDateEnd] = useState('2024-07-31');
  const [maxCloud, setMaxCloud] = useState(20);
  const [loading, setLoading] = useState(false);
  const [candidates, setCandidates] = useState<CandidateData[]>([]);
  const [selectedStacId, setSelectedStacId] = useState<string | null>(null);
  const [ingesting, setIngesting] = useState(false);
  const [searchRequestId, setSearchRequestId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSearch = async () => {
    setLoading(true);
    setError(null);
    setCandidates([]);

    try {
      const res = await searchSatelliteCandidates({
        sessionId,
        aoi_geometry: selectedRegion.aoi,
        sensor,
        date_start: dateStart,
        date_end: dateEnd,
        max_cloud_cover: maxCloud,
      });

      setSearchRequestId(res.request_id);
      const items = await getCandidates(res.request_id);
      setCandidates(items);
    } catch (err: any) {
      setError(err.message || 'Failed to search Copernicus satellite catalog.');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectAndIngest = async (stacItemId: string) => {
    if (!searchRequestId) return;
    setIngesting(true);
    setSelectedStacId(stacItemId);

    try {
      await selectCandidate(searchRequestId, stacItemId);
      onSceneIngested();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to ingest satellite scene.');
    } finally {
      setIngesting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl bg-surface border border-border-light rounded-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200 flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-slate-900/60">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-blue-600/10 text-blue-400 border border-blue-500/20">
              <Satellite className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-white">Copernicus Satellite Search & Retrieval</h3>
              <p className="text-xs text-slate-400 font-mono">
                Query Sentinel-1 SAR & Sentinel-2 Optical via CDSE STAC
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Search Parameters Form */}
        <div className="p-6 space-y-4 overflow-y-auto flex-1">
          {/* Region Preset */}
          <div className="space-y-1.5">
            <label className="text-xs font-mono uppercase text-slate-400 flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5 text-blue-400" />
              Area of Interest (AOI)
            </label>
            <select
              value={selectedRegion.name}
              onChange={(e) => {
                const found = REGION_PRESETS.find((r) => r.name === e.target.value);
                if (found) setSelectedRegion(found);
              }}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-white focus:border-blue-500 focus:outline-none"
            >
              {REGION_PRESETS.map((r) => (
                <option key={r.name} value={r.name}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Sensor Selection */}
            <div className="space-y-1.5">
              <label className="text-xs font-mono uppercase text-slate-400 flex items-center gap-1.5">
                <Satellite className="w-3.5 h-3.5 text-purple-400" />
                Satellite Constellation
              </label>
              <select
                value={sensor}
                onChange={(e) => setSensor(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-white focus:border-blue-500 focus:outline-none"
              >
                <option value="SENTINEL-2">Sentinel-2 (Multispectral Optical)</option>
                <option value="SENTINEL-1">Sentinel-1 (C-Band SAR Radar)</option>
              </select>
            </div>

            {/* Date Range Start */}
            <div className="space-y-1.5">
              <label className="text-xs font-mono uppercase text-slate-400 flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-emerald-400" />
                Acquisition From
              </label>
              <input
                type="date"
                value={dateStart}
                onChange={(e) => setDateStart(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs font-mono text-white focus:border-blue-500 focus:outline-none"
              />
            </div>

            {/* Date Range End */}
            <div className="space-y-1.5">
              <label className="text-xs font-mono uppercase text-slate-400 flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-emerald-400" />
                Acquisition To
              </label>
              <input
                type="date"
                value={dateEnd}
                onChange={(e) => setDateEnd(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs font-mono text-white focus:border-blue-500 focus:outline-none"
              />
            </div>
          </div>

          {/* Cloud Cover Slider for Optical */}
          {sensor === 'SENTINEL-2' && (
            <div className="space-y-1.5 pt-1">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-slate-400 flex items-center gap-1.5">
                  <Cloud className="w-3.5 h-3.5 text-cyan-400" />
                  Max Permissible Cloud Cover:
                </span>
                <span className="text-cyan-400 font-bold">{maxCloud}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="80"
                step="5"
                value={maxCloud}
                onChange={(e) => setMaxCloud(parseInt(e.target.value))}
                className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
              />
            </div>
          )}

          {/* Search Action Button */}
          <div className="pt-2">
            <button
              onClick={handleSearch}
              disabled={loading}
              className="w-full py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 text-white text-xs font-medium font-mono flex items-center justify-center gap-2 transition-all shadow-md shadow-blue-600/20 active:scale-[0.99]"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Querying Copernicus STAC Catalog...</span>
                </>
              ) : (
                <>
                  <Search className="w-4 h-4" />
                  <span>Search Satellite Scenes</span>
                </>
              )}
            </button>
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-red-950/40 border border-red-800/40 text-red-300 text-xs font-mono">
              {error}
            </div>
          )}

          {/* Results Candidate List */}
          {candidates.length > 0 && (
            <div className="space-y-2.5 pt-3 border-t border-slate-800">
              <div className="flex items-center justify-between text-xs font-mono text-slate-400">
                <span>Available STAC Candidate Scenes ({candidates.length}):</span>
                <span className="text-[10px] text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800">
                  CDSE Verified
                </span>
              </div>

              <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                {candidates.map((cand) => (
                  <div
                    key={cand.id || cand.stac_item_id}
                    className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 hover:border-slate-700 transition-colors flex items-center justify-between gap-3 text-xs font-mono"
                  >
                    <div className="space-y-1 truncate">
                      <div className="flex items-center gap-2">
                        <Layers className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                        <span className="text-white font-semibold truncate max-w-[340px]">
                          {cand.stac_item_id}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-[11px] text-slate-400">
                        <span>Date: {cand.acquisition_date}</span>
                        {cand.cloud_cover_pct !== undefined && (
                          <span
                            className={
                              cand.cloud_cover_pct < 10
                                ? 'text-emerald-400'
                                : 'text-amber-400'
                            }
                          >
                            Cloud: {cand.cloud_cover_pct.toFixed(1)}%
                          </span>
                        )}
                        <span className="text-slate-500 uppercase">{cand.collection}</span>
                      </div>
                    </div>

                    <button
                      onClick={() => handleSelectAndIngest(cand.stac_item_id)}
                      disabled={ingesting}
                      className="px-3 py-1.5 rounded bg-slate-900 hover:bg-blue-600 text-slate-300 hover:text-white border border-slate-700 hover:border-blue-500 transition-all text-xs font-medium shrink-0 flex items-center gap-1.5"
                    >
                      {ingesting && selectedStacId === cand.stac_item_id ? (
                        <>
                          <Loader2 className="w-3 h-3 animate-spin" />
                          <span>Ingesting...</span>
                        </>
                      ) : (
                        <>
                          <Check className="w-3 h-3" />
                          <span>Ingest Scene</span>
                        </>
                      )}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
