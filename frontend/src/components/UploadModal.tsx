'use client';

import React, { useState } from 'react';
import { X, UploadCloud, CheckCircle2, AlertCircle, FileImage, Layers } from 'lucide-react';
import { RasterMetadata, InputMode } from '@/types';

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string;
  onUploadSuccess: (images: RasterMetadata[], detectedMode: InputMode) => void;
}

export const UploadModal: React.FC<UploadModalProps> = ({
  isOpen,
  onClose,
  sessionId,
  onUploadSuccess,
}) => {
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selected = Array.from(e.target.files).slice(0, 2);
      setFiles(selected);
      setError(null);
    }
  };

  const handleUpload = async () => {
    if (files.length === 0) {
      setError('Please select at least 1 satellite raster file.');
      return;
    }

    setUploading(true);
    setError(null);

    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });

    try {
      const res = await fetch(`/api/v1/sessions/${sessionId}/images`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Upload failed with status ${res.status}`);
      }

      const data = await res.json();
      onUploadSuccess(data.images, data.detected_mode);
      onClose();
    } catch (err: any) {
      setError(err.message || 'An error occurred during ingestion.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-xl bg-surface border border-border-light rounded-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-slate-900/50">
          <div className="flex items-center gap-2">
            <UploadCloud className="w-5 h-5 text-blue-400" />
            <h3 className="font-semibold text-white">Ingest Satellite Imagery</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          <div className="border-2 border-dashed border-slate-700 hover:border-blue-500/50 rounded-xl p-8 text-center transition-colors bg-slate-950/40">
            <input
              type="file"
              id="file-upload"
              multiple
              accept=".tif,.tiff,.png,.jpg,.jpeg"
              onChange={handleFileChange}
              className="hidden"
            />
            <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-blue-500/10 flex items-center justify-center text-blue-400 border border-blue-500/20">
                <Layers className="w-6 h-6" />
              </div>
              <div>
                <p className="text-sm font-medium text-white">Click or drag GeoTIFF / PNG rasters here</p>
                <p className="text-xs text-slate-400 mt-1 font-mono">Supports GeoTIFF (EPSG:4326/3857/UTM), Cartosat, RISAT, Sentinel-1/2, PNG (Max 2)</p>
              </div>
            </label>
          </div>

          {files.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-mono text-slate-400 uppercase tracking-wider">Selected Rasters ({files.length}/2):</p>
              <div className="grid gap-2">
                {files.map((f, i) => (
                  <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-slate-900/80 border border-slate-800 text-xs font-mono">
                    <div className="flex items-center gap-2.5">
                      <FileImage className="w-4 h-4 text-blue-400" />
                      <span className="text-white truncate max-w-[280px]">{f.name}</span>
                    </div>
                    <span className="text-slate-400">{(f.size / (1024 * 1024)).toFixed(2)} MB</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2.5 p-3.5 rounded-lg bg-red-950/40 border border-red-800/50 text-red-300 text-xs">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <div>{error}</div>
            </div>
          )}

          <div className="bg-slate-900/40 p-3.5 rounded-lg border border-slate-800 text-xs text-slate-400 space-y-1.5 font-mono">
            <p className="text-blue-400 font-semibold uppercase tracking-wider text-[10px]">Modality Auto-Detection:</p>
            <p>&bull; 1 Image: Mode 1 (RS-VQA / Caption / Grounding)</p>
            <p>&bull; Optical + SAR Pair: Mode 2 (Cross-Modal Fusion)</p>
            <p>&bull; 2 Optical Dates: Mode 3 & 4 (Bi-Temporal Change & Change-VQA)</p>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border bg-slate-900/50">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-xs font-medium text-slate-300 hover:bg-slate-800 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleUpload}
            disabled={uploading || files.length === 0}
            className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-medium transition-all shadow-md shadow-blue-600/20 active:scale-95"
          >
            {uploading ? 'Ingesting & Reprojecting...' : 'Ingest Imagery'}
          </button>
        </div>
      </div>
    </div>
  );
};
