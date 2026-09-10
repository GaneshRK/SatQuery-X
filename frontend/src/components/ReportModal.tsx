'use client';

import React, { useState } from 'react';
import { X, FileText, Download, ExternalLink, Loader2, CheckCircle2, ShieldCheck } from 'lucide-react';
import { ExecutionTrace } from '@/types';

interface ReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string;
  trace: ExecutionTrace | null;
}

export const ReportModal: React.FC<ReportModalProps> = ({
  isOpen,
  onClose,
  sessionId,
  trace,
}) => {
  const [generating, setGenerating] = useState(false);
  const [reportUrl, setReportUrl] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen || !trace) return null;

  const handleGenerate = async (fmt: 'html' | 'pdf') => {
    setGenerating(true);
    setError(null);

    try {
      const res = await fetch(`/api/v1/sessions/${sessionId}/report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query_id: trace.query_id,
          title: 'SatQuery-X Geospatial Intelligence Analysis Report',
          format: fmt,
          analyst_notes: 'All multimodal specialist outputs, geospatial bounds, and execution traces certified.',
        }),
      });

      if (!res.ok) {
        throw new Error(`Report generation failed: ${res.statusText}`);
      }

      const data = await res.json();
      setReportUrl(data.html_preview_url);
      setDownloadUrl(data.download_url);
    } catch (err: any) {
      setError(err.message || 'Failed to compile intelligence report.');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="w-full max-w-4xl max-h-[90vh] bg-surface border border-border-light rounded-xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-slate-900/60">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-blue-400" />
            <h3 className="font-semibold text-white">Geospatial Intelligence Report Generator</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          <div className="flex items-center justify-between bg-slate-950 p-4 rounded-lg border border-slate-800 font-mono text-xs text-slate-300">
            <div>
              <p>Query ID: <strong className="text-white">{trace.query_id}</strong></p>
              <p className="text-slate-400 mt-0.5">Mode: <strong className="text-blue-400">{trace.detected_mode}</strong> &bull; Confidence: <strong className="text-emerald-400">{trace.confidence == null ? "—" : `${(trace.confidence * 100).toFixed(1)}%`}</strong></p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleGenerate('html')}
                disabled={generating}
                className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-all shadow-md shadow-blue-600/20 active:scale-95 disabled:opacity-50"
              >
                {generating ? 'Compiling...' : 'Generate HTML Report'}
              </button>
              {downloadUrl && (
                <a
                  href={downloadUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition-all flex items-center gap-1.5"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download</span>
                </a>
              )}
            </div>
          </div>

          {error && (
            <div className="p-3 rounded bg-red-950/40 border border-red-800/50 text-red-300 text-xs font-mono">
              {error}
            </div>
          )}

          {reportUrl ? (
            <div className="border border-slate-800 rounded-lg overflow-hidden h-[500px] bg-slate-950">
              <iframe src={reportUrl} className="w-full h-full border-none" title="Report Preview" />
            </div>
          ) : (
            <div className="border border-dashed border-slate-800 rounded-lg p-12 text-center text-slate-500 font-mono text-xs">
              Click &quot;Generate HTML Report&quot; to compile auditable intelligence report with maps, metrics, and trace tables.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
