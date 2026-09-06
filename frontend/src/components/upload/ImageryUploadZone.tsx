"use client";

import React, { useState, useRef } from "react";
import {
  Upload,
  Image as ImageIcon,
  FileCode,
  X,
  CheckCircle2,
  Sparkles,
  Layers,
  ArrowLeftRight,
} from "lucide-react";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";

export type UploadMode = "single" | "bitemporal" | "crossmodal";

export interface ImageryUploadZoneProps {
  onFilesSelected: (files: {
    mode: UploadMode;
    single?: File | null;
    before?: File | null;
    after?: File | null;
    optical?: File | null;
    sar?: File | null;
  }) => void;
  onClose?: () => void;
}

export const ImageryUploadZone: React.FC<ImageryUploadZoneProps> = ({
  onFilesSelected,
  onClose,
}) => {
  const [mode, setMode] = useState<UploadMode>("bitemporal");
  const [singleFile, setSingleFile] = useState<File | null>(null);
  const [beforeFile, setBeforeFile] = useState<File | null>(null);
  const [afterFile, setAfterFile] = useState<File | null>(null);
  const [opticalFile, setOpticalFile] = useState<File | null>(null);
  const [sarFile, setSarFile] = useState<File | null>(null);

  const singleRef = useRef<HTMLInputElement>(null);
  const beforeRef = useRef<HTMLInputElement>(null);
  const afterRef = useRef<HTMLInputElement>(null);
  const opticalRef = useRef<HTMLInputElement>(null);
  const sarRef = useRef<HTMLInputElement>(null);

  const handleApply = () => {
    onFilesSelected({
      mode,
      single: singleFile,
      before: beforeFile,
      after: afterFile,
      optical: opticalFile,
      sar: sarFile,
    });
    if (onClose) onClose();
  };

  const handleClearAll = () => {
    setSingleFile(null);
    setBeforeFile(null);
    setAfterFile(null);
    setOpticalFile(null);
    setSarFile(null);
  };

  return (
    <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-2xl text-xs space-y-4">
      {/* Mode Selector Tabs */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="font-semibold text-slate-200">Select Modality Context</span>
          <span className="text-[10px] text-slate-400">GeoTIFF, TIFF, PNG, JPEG</span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <button
            type="button"
            onClick={() => setMode("bitemporal")}
            className={`py-2 px-3 rounded-lg border text-center font-medium transition-all ${
              mode === "bitemporal"
                ? "bg-cyan-950/60 border-cyan-500 text-cyan-300 shadow-md shadow-cyan-500/10"
                : "bg-slate-950/60 border-slate-800 text-slate-400 hover:text-slate-200"
            }`}
          >
            <div className="flex items-center justify-center gap-1 mb-0.5">
              <ArrowLeftRight className="w-3.5 h-3.5" />
              <span>Bi-Temporal Pair</span>
            </div>
            <span className="text-[10px] opacity-70 block">Change Detection (T1 / T2)</span>
          </button>

          <button
            type="button"
            onClick={() => setMode("crossmodal")}
            className={`py-2 px-3 rounded-lg border text-center font-medium transition-all ${
              mode === "crossmodal"
                ? "bg-cyan-950/60 border-cyan-500 text-cyan-300 shadow-md shadow-cyan-500/10"
                : "bg-slate-950/60 border-slate-800 text-slate-400 hover:text-slate-200"
            }`}
          >
            <div className="flex items-center justify-center gap-1 mb-0.5">
              <Layers className="w-3.5 h-3.5" />
              <span>Optical + SAR</span>
            </div>
            <span className="text-[10px] opacity-70 block">Radar & Multi-Spectral Fusion</span>
          </button>

          <button
            type="button"
            onClick={() => setMode("single")}
            className={`py-2 px-3 rounded-lg border text-center font-medium transition-all ${
              mode === "single"
                ? "bg-cyan-950/60 border-cyan-500 text-cyan-300 shadow-md shadow-cyan-500/10"
                : "bg-slate-950/60 border-slate-800 text-slate-400 hover:text-slate-200"
            }`}
          >
            <div className="flex items-center justify-center gap-1 mb-0.5">
              <ImageIcon className="w-3.5 h-3.5" />
              <span>Single Image</span>
            </div>
            <span className="text-[10px] opacity-70 block">Visual Q&A / Captioning</span>
          </button>
        </div>
      </div>

      {/* Upload Dropzones based on mode */}
      {mode === "bitemporal" && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Before T1 */}
          <div
            onClick={() => beforeRef.current?.click()}
            className="p-4 rounded-xl border border-dashed border-slate-700 hover:border-cyan-500/60 bg-slate-950/50 flex flex-col items-center justify-center text-center cursor-pointer transition-all min-h-[120px]"
          >
            <input
              ref={beforeRef}
              type="file"
              accept=".tif,.tiff,.png,.jpg,.jpeg,.webp"
              className="hidden"
              onChange={(e) => setBeforeFile(e.target.files?.[0] || null)}
            />
            {beforeFile ? (
              <div className="space-y-1">
                <CheckCircle2 className="w-5 h-5 text-emerald-400 mx-auto" />
                <span className="font-mono text-slate-200 block truncate max-w-[140px]">
                  {beforeFile.name}
                </span>
                <span className="text-[10px] text-slate-400 block">T1 Baseline Attached</span>
              </div>
            ) : (
              <div className="space-y-1">
                <Upload className="w-5 h-5 text-slate-500 mx-auto" />
                <span className="text-slate-300 font-medium block">Upload T1 Baseline</span>
                <span className="text-[10px] text-slate-500 block">Earlier observation</span>
              </div>
            )}
          </div>

          {/* After T2 */}
          <div
            onClick={() => afterRef.current?.click()}
            className="p-4 rounded-xl border border-dashed border-slate-700 hover:border-cyan-500/60 bg-slate-950/50 flex flex-col items-center justify-center text-center cursor-pointer transition-all min-h-[120px]"
          >
            <input
              ref={afterRef}
              type="file"
              accept=".tif,.tiff,.png,.jpg,.jpeg,.webp"
              className="hidden"
              onChange={(e) => setAfterFile(e.target.files?.[0] || null)}
            />
            {afterFile ? (
              <div className="space-y-1">
                <CheckCircle2 className="w-5 h-5 text-emerald-400 mx-auto" />
                <span className="font-mono text-slate-200 block truncate max-w-[140px]">
                  {afterFile.name}
                </span>
                <span className="text-[10px] text-slate-400 block">T2 Comparison Attached</span>
              </div>
            ) : (
              <div className="space-y-1">
                <Upload className="w-5 h-5 text-slate-500 mx-auto" />
                <span className="text-slate-300 font-medium block">Upload T2 Comparison</span>
                <span className="text-[10px] text-slate-500 block">Later observation</span>
              </div>
            )}
          </div>
        </div>
      )}

      {mode === "crossmodal" && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Optical */}
          <div
            onClick={() => opticalRef.current?.click()}
            className="p-4 rounded-xl border border-dashed border-slate-700 hover:border-cyan-500/60 bg-slate-950/50 flex flex-col items-center justify-center text-center cursor-pointer transition-all min-h-[120px]"
          >
            <input
              ref={opticalRef}
              type="file"
              accept=".tif,.tiff,.png,.jpg,.jpeg,.webp"
              className="hidden"
              onChange={(e) => setOpticalFile(e.target.files?.[0] || null)}
            />
            {opticalFile ? (
              <div className="space-y-1">
                <CheckCircle2 className="w-5 h-5 text-emerald-400 mx-auto" />
                <span className="font-mono text-slate-200 block truncate max-w-[140px]">
                  {opticalFile.name}
                </span>
                <span className="text-[10px] text-slate-400 block">Optical Sentinel-2</span>
              </div>
            ) : (
              <div className="space-y-1">
                <Upload className="w-5 h-5 text-slate-500 mx-auto" />
                <span className="text-slate-300 font-medium block">Upload Optical Raster</span>
                <span className="text-[10px] text-slate-500 block">VNIR Multi-spectral</span>
              </div>
            )}
          </div>

          {/* SAR */}
          <div
            onClick={() => sarRef.current?.click()}
            className="p-4 rounded-xl border border-dashed border-slate-700 hover:border-cyan-500/60 bg-slate-950/50 flex flex-col items-center justify-center text-center cursor-pointer transition-all min-h-[120px]"
          >
            <input
              ref={sarRef}
              type="file"
              accept=".tif,.tiff,.png,.jpg,.jpeg,.webp"
              className="hidden"
              onChange={(e) => setSarFile(e.target.files?.[0] || null)}
            />
            {sarFile ? (
              <div className="space-y-1">
                <CheckCircle2 className="w-5 h-5 text-emerald-400 mx-auto" />
                <span className="font-mono text-slate-200 block truncate max-w-[140px]">
                  {sarFile.name}
                </span>
                <span className="text-[10px] text-slate-400 block">SAR Sentinel-1</span>
              </div>
            ) : (
              <div className="space-y-1">
                <Upload className="w-5 h-5 text-slate-500 mx-auto" />
                <span className="text-slate-300 font-medium block">Upload SAR Radar Raster</span>
                <span className="text-[10px] text-slate-500 block">C-Band Co-Polarized Backscatter</span>
              </div>
            )}
          </div>
        </div>
      )}

      {mode === "single" && (
        <div
          onClick={() => singleRef.current?.click()}
          className="p-6 rounded-xl border border-dashed border-slate-700 hover:border-cyan-500/60 bg-slate-950/50 flex flex-col items-center justify-center text-center cursor-pointer transition-all min-h-[130px]"
        >
          <input
            ref={singleRef}
            type="file"
            accept=".tif,.tiff,.png,.jpg,.jpeg,.webp"
            className="hidden"
            onChange={(e) => setSingleFile(e.target.files?.[0] || null)}
          />
          {singleFile ? (
            <div className="space-y-1">
              <CheckCircle2 className="w-6 h-6 text-emerald-400 mx-auto" />
              <span className="font-mono text-slate-200 block">{singleFile.name}</span>
              <span className="text-[10px] text-slate-400 block">Ready for Remote Sensing VQA</span>
            </div>
          ) : (
            <div className="space-y-1">
              <Upload className="w-6 h-6 text-slate-500 mx-auto" />
              <span className="text-slate-200 font-medium block">
                Drop custom satellite imagery here or click to browse
              </span>
              <span className="text-[10px] text-slate-500 block">
                Supports GeoTIFF, TIFF, PNG, JPEG
              </span>
            </div>
          )}
        </div>
      )}

      {/* Action Footer */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-800">
        <button
          type="button"
          onClick={handleClearAll}
          className="text-xs text-slate-400 hover:text-rose-400 transition-colors"
        >
          Clear uploads
        </button>

        <div className="flex items-center gap-2">
          {onClose && (
            <Button variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
          )}
          <Button variant="primary" size="sm" onClick={handleApply}>
            Attach to Analysis
          </Button>
        </div>
      </div>
    </div>
  );
};
