'use client';

import React, { useState, useEffect } from 'react';
import { Header } from '@/components/Header';
import { UploadModal } from '@/components/UploadModal';
import { MapViewer } from '@/components/MapViewer';
import { ChatConsole } from '@/components/ChatConsole';
import { ExecutionTraceTimeline } from '@/components/ExecutionTraceTimeline';
import { EvidenceDrawer } from '@/components/EvidenceDrawer';
import { ReportModal } from '@/components/ReportModal';
import { RasterMetadata, ExecutionTrace, InputMode } from '@/types';

export default function DashboardPage() {
  const [sessionId, setSessionId] = useState<string>('');
  const [images, setImages] = useState<RasterMetadata[]>([]);
  const [detectedMode, setDetectedMode] = useState<InputMode | null>(null);
  const [currentTrace, setCurrentTrace] = useState<ExecutionTrace | null>(null);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isReportOpen, setIsReportOpen] = useState(false);

  // Initialize session on mount
  useEffect(() => {
    const initSession = async () => {
      try {
        const res = await fetch('/api/v1/sessions', { method: 'POST' });
        if (res.ok) {
          const data = await res.json();
          setSessionId(data.session_id);
        }
      } catch (err) {
        console.error('Failed to init session:', err);
      }
    };
    initSession();
  }, []);

  const handleUploadSuccess = (uploadedImages: RasterMetadata[], mode: InputMode) => {
    setImages(uploadedImages);
    setDetectedMode(mode);
  };

  const handleQueryExecuted = (trace: ExecutionTrace) => {
    setCurrentTrace(trace);
  };

  return (
    <div className="flex flex-col min-h-screen bg-[#070b13] text-slate-100">
      <Header
        detectedMode={detectedMode}
        onOpenUpload={() => setIsUploadOpen(true)}
        onOpenReport={() => setIsReportOpen(true)}
        hasTrace={!!currentTrace}
      />

      <main className="flex-1 p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 max-w-[1800px] w-full mx-auto">
        {/* Left / Center Section: Map & Chat (7 Cols) */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          <div className="h-[520px] w-full">
            <MapViewer images={images} evidence={currentTrace?.evidence || null} />
          </div>

          <ChatConsole
            sessionId={sessionId}
            detectedMode={detectedMode}
            hasImages={images.length > 0}
            onQueryExecuted={handleQueryExecuted}
          />
        </div>

        {/* Right Section: Trace & Evidence (5 Cols) */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          <ExecutionTraceTimeline trace={currentTrace} />
          <EvidenceDrawer evidence={currentTrace?.evidence || null} />
        </div>
      </main>

      {/* Modals */}
      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        sessionId={sessionId}
        onUploadSuccess={handleUploadSuccess}
      />

      <ReportModal
        isOpen={isReportOpen}
        onClose={() => setIsReportOpen(false)}
        sessionId={sessionId}
        trace={currentTrace}
      />
    </div>
  );
}
