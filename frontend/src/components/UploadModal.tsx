'use client';

import React, { useState } from 'react';
import { X, UploadCloud, CheckCircle2, AlertCircle, FileImage, Layers, Loader2 } from 'lucide-react';
import { RasterMetadata, InputMode } from '@/types';
import { uploadImage, createPair, listImages } from '@/services/images';

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

    if (!sessionId) {
      setError('Session is not initialized. Please refresh the page.');
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const uploadedAssets = [];
      for (const file of files) {
        const { asset } = await uploadImage(sessionId, file);
        uploadedAssets.push(asset);
      }

      let mode: InputMode = 'single_image';
      if (uploadedAssets.length === 2) {
        const imgA = uploadedAssets[0];
        const imgB = uploadedAssets[1];
        const isCrossModal =
          (imgA.modality === 'SAR' && imgB.modality !== 'SAR') ||
          (imgB.modality === 'SAR' && imgA.modality !== 'SAR');
        const pairType = isCrossModal ? 'CROSS_MODAL' : 'BI_TEMPORAL';
        try {
          await createPair(sessionId, imgA.id, imgB.id, pairType);
        } catch (pairErr) {
          console.warn('Pair creation info:', pairErr);
        }
        mode = isCrossModal ? 'cross_modal_pair' : 'bi_temporal';
      }

      // Small delay to allow Celery / background validator to set previews and bounds
      await new Promise((r) => setTimeout(r, 600));

      const allImages = await listImages(sessionId);
      const mapped: RasterMetadata[] = allImages.map((img) => ({
        image_id: img.id,
        filename: img.original_filename,
        content_type: img.file_format,
        width: img.width,
        height: img.height,
        band_count: img.band_count,
        geo_referenced: !!(img.is_georeferenced ?? img.bounds_wgs84),
        crs: img.crs,
        bounds_wgs84: img.bounds_wgs84,
        sensor_type: img.sensor,
        preview_url: img.preview_url
          ? img.preview_url.startsWith('http')
            ? img.preview_url
            : `http://localhost:8000${img.preview_url}`
          : undefined,
      }));

      onUploadSuccess(mapped, mode);
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
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          <div className="border-2 border-dashed border-slate-800 hover:border-blue-500/50 rounded-xl p-8 text-center bg-slate-950/40 transition-colors relative cursor-pointer group">
            <input
              type="file"
              multiple
              accept=".tif,.tiff,.geotiff,.png,.jpg,.jpeg"
              onChange={handleFileChange}
              className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
            />
            <div className="flex flex-col items-center gap-2">
              <div className="w-12 h-12 rounded-full bg-blue-600/10 border border-blue-500/20 flex items-center justify-center text-blue-400 group-hover:scale-110 transition-transform">
                <FileImage className="w-6 h-6" />
              </div>
              <p className="text-sm font-medium text-white">Drop GeoTIFF rasters or click to browse</p>
              <p className="text-xs text-slate-500 font-mono">
                Supports single optical (Mode 1), optical+SAR pair (Mode 2), or bi-temporal pair (Mode 3)
              </p>
            </div>
          </div>

          {files.length > 0 && (
            <div className="space-y-2">
              <span className="text-xs font-mono uppercase text-slate-400">Selected Files ({files.length}/2):</span>
              <div className="space-y-1.5">
                {files.map((file, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-mono"
                  >
                    <div className="flex items-center gap-2 text-slate-300">
                      <Layers className="w-4 h-4 text-blue-400" />
                      <span className="truncate max-w-[320px]">{file.name}</span>
                    </div>
                    <span className="text-slate-500">{(file.size / (1024 * 1024)).toFixed(2)} MB</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-red-950/40 border border-red-800/40 text-red-300 text-xs font-mono">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-xs font-mono text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleUpload}
              disabled={uploading || files.length === 0}
              className="flex items-center gap-2 px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 text-white text-xs font-medium font-mono transition-all shadow-md shadow-blue-600/20 active:scale-95"
            >
              {uploading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Ingesting & Validating...</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Ingest Imagery</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
