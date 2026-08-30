'use client';

import React, { useState } from 'react';
import { Layers, Eye, Crosshair, ZoomIn, ZoomOut, Maximize2, Compass, Sliders } from 'lucide-react';
import { RasterMetadata, EvidenceOutput } from '@/types';

interface MapViewerProps {
  images: RasterMetadata[];
  evidence: EvidenceOutput | null;
}

export const MapViewer: React.FC<MapViewerProps> = ({ images, evidence }) => {
  const [activeImageIndex, setActiveImageIndex] = useState(0);
  const [showMask, setShowMask] = useState(true);
  const [showBoxes, setShowBoxes] = useState(true);
  const [sliderPosition, setSliderPosition] = useState(50);
  const [isSplitView, setIsSplitView] = useState(false);

  const activeImage = images[activeImageIndex] || null;
  const isBiTemporal = images.length === 2;

  return (
    <div className="relative w-full h-full bg-[#040810] border border-border rounded-xl overflow-hidden flex flex-col shadow-inner">
      {/* Top Map Toolbar */}
      <div className="absolute top-4 left-4 z-20 flex items-center gap-2 bg-slate-900/90 backdrop-blur-md p-1.5 rounded-lg border border-slate-800 shadow-xl">
        {images.map((img, idx) => (
          <button
            key={img.image_id}
            onClick={() => {
              setActiveImageIndex(idx);
              setIsSplitView(false);
            }}
            className={`px-3 py-1.5 text-xs font-mono rounded-md transition-all ${
              activeImageIndex === idx && !isSplitView
                ? 'bg-blue-600 text-white font-semibold shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            {img.sensor_type?.toUpperCase() || 'RASTER'} #{idx + 1}
          </button>
        ))}

        {isBiTemporal && (
          <button
            onClick={() => setIsSplitView(!isSplitView)}
            className={`px-3 py-1.5 text-xs font-mono rounded-md transition-all flex items-center gap-1.5 ${
              isSplitView
                ? 'bg-purple-600 text-white font-semibold shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <Sliders className="w-3 h-3" />
            <span>Split Swipe</span>
          </button>
        )}

        <div className="h-4 w-px bg-slate-800 mx-1" />

        {evidence?.change_mask_url && (
          <button
            onClick={() => setShowMask(!showMask)}
            className={`px-2.5 py-1.5 text-xs font-mono rounded-md transition-all flex items-center gap-1.5 ${
              showMask
                ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <Eye className="w-3 h-3" />
            <span>Change Mask</span>
          </button>
        )}

        {evidence?.bboxes && evidence.bboxes.length > 0 && (
          <button
            onClick={() => setShowBoxes(!showBoxes)}
            className={`px-2.5 py-1.5 text-xs font-mono rounded-md transition-all flex items-center gap-1.5 ${
              showBoxes
                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <Layers className="w-3 h-3" />
            <span>Boxes ({evidence.bboxes.length})</span>
          </button>
        )}
      </div>

      {/* Top Right Reticle & Coordinates */}
      <div className="absolute top-4 right-4 z-20 bg-slate-900/90 backdrop-blur-md px-3 py-1.5 rounded-lg border border-slate-800 text-[11px] font-mono text-slate-300 flex items-center gap-3">
        <div className="flex items-center gap-1 text-cyan-400">
          <Crosshair className="w-3.5 h-3.5" />
          <span>{activeImage?.crs || 'EPSG:4326 (WGS84)'}</span>
        </div>
        {activeImage && (
          <div className="text-slate-400">
            {activeImage.width}&times;{activeImage.height}px
          </div>
        )}
      </div>

      {/* Viewport Canvas */}
      <div className="flex-1 relative flex items-center justify-center overflow-hidden p-6">
        {images.length === 0 ? (
          <div className="text-center space-y-3">
            <div className="w-16 h-16 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center mx-auto text-slate-600">
              <Compass className="w-8 h-8 animate-spin-slow" />
            </div>
            <p className="text-sm font-medium text-slate-400">No satellite imagery loaded in session.</p>
            <p className="text-xs text-slate-600 font-mono">Upload optical/SAR single or paired GeoTIFF rasters to begin analysis.</p>
          </div>
        ) : isSplitView && images.length === 2 ? (
          /* Split View Slider */
          <div className="relative w-full h-full max-w-4xl max-h-[600px] border border-slate-800 rounded-lg overflow-hidden select-none">
            {/* T2 (Post) Layer underneath */}
            <img
              src={images[1].preview_url || ''}
              alt="T2 Post"
              className="absolute inset-0 w-full h-full object-contain"
            />
            {/* T1 (Pre) Layer with clip path */}
            <div
              className="absolute inset-0 overflow-hidden"
              style={{ clipPath: `inset(0 ${100 - sliderPosition}% 0 0)` }}
            >
              <img
                src={images[0].preview_url || ''}
                alt="T1 Pre"
                className="absolute inset-0 w-full h-full object-contain"
              />
            </div>
            {/* Slider Divider */}
            <div
              className="absolute top-0 bottom-0 w-1 bg-white cursor-ew-resize shadow-[0_0_10px_rgba(255,255,255,0.8)]"
              style={{ left: `${sliderPosition}%` }}
            >
              <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-7 h-7 rounded-full bg-white text-black text-[10px] font-bold flex items-center justify-center shadow-lg">
                &harr;
              </div>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={sliderPosition}
              onChange={(e) => setSliderPosition(Number(e.target.value))}
              className="absolute inset-0 opacity-0 cursor-ew-resize w-full h-full"
            />
          </div>
        ) : (
          /* Standard Single Raster Viewer with Evidence Overlays */
          <div className="relative w-full h-full max-w-4xl max-h-[600px] flex items-center justify-center">
            {activeImage?.preview_url && (
              <div className="relative inline-block border border-slate-800 rounded-lg overflow-hidden shadow-2xl">
                <img
                  src={activeImage.preview_url}
                  alt={activeImage.filename}
                  className="max-h-[560px] max-w-full object-contain block"
                />

                {/* Change Mask Overlay */}
                {showMask && evidence?.change_mask_url && (
                  <img
                    src={evidence.change_mask_url}
                    alt="Change Mask"
                    className="absolute inset-0 w-full h-full object-contain mix-blend-screen opacity-75 pointer-events-none"
                  />
                )}

                {/* Visual Grounding Bounding Box Overlays */}
                {showBoxes &&
                  evidence?.bboxes &&
                  evidence.bboxes.map((box, i) => {
                    const imgW = activeImage.width || 256;
                    const imgH = activeImage.height || 256;
                    const left = (box.x1 / imgW) * 100;
                    const top = (box.y1 / imgH) * 100;
                    const width = ((box.x2 - box.x1) / imgW) * 100;
                    const height = ((box.y2 - box.y1) / imgH) * 100;

                    return (
                      <div
                        key={i}
                        className="absolute border-2 border-yellow-400 bg-yellow-400/10 rounded pointer-events-auto group cursor-pointer"
                        style={{
                          left: `${left}%`,
                          top: `${top}%`,
                          width: `${width}%`,
                          height: `${height}%`,
                        }}
                      >
                        <span className="absolute -top-5 left-0 px-1.5 py-0.5 rounded bg-yellow-400 text-black text-[9px] font-bold font-mono uppercase tracking-wider shadow">
                          {box.label || 'Target'} {box.confidence ? `(${Math.round(box.confidence * 100)}%)` : ''}
                        </span>
                      </div>
                    );
                  })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bottom Status Ribbon */}
      <div className="h-9 border-t border-border bg-slate-950/80 px-4 flex items-center justify-between text-xs font-mono text-slate-500">
        <div className="flex items-center gap-4">
          <span>Active Layer: <strong className="text-slate-300">{activeImage?.filename || 'None'}</strong></span>
          <span>Bands: <strong className="text-slate-300">{activeImage?.band_count || 0}</strong></span>
          <span>Geo-Referenced: <strong className={activeImage?.geo_referenced ? 'text-emerald-400' : 'text-slate-400'}>{activeImage?.geo_referenced ? 'Yes (Affine Valid)' : 'Pixel Coordinate Space'}</strong></span>
        </div>
        <div>SatQuery-X Raster Visualizer &bull; Sub-Pixel Alignment</div>
      </div>
    </div>
  );
};
