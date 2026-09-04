'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Header } from '@/components/Header';
import { UploadModal } from '@/components/UploadModal';
import { MapViewer } from '@/components/MapViewer';
import { EarthObservatory } from '@/components/EarthObservatory';
import { ChatConsole, formatQueryToTrace } from '@/components/ChatConsole';
import { ExecutionTraceTimeline } from '@/components/ExecutionTraceTimeline';
import { EvidenceDrawer } from '@/components/EvidenceDrawer';
import { ReportModal } from '@/components/ReportModal';
import { SatelliteSearchModal } from '@/components/SatelliteSearchModal';
import { ContextBar } from '@/components/ContextBar';
import { ClickToExplainModal, ExplainFeatureData } from '@/components/ClickToExplainModal';
import { RasterMetadata, ExecutionTrace, InputMode, ConversationContext, UIAction } from '@/types';
import { login } from '@/services/auth';
import { listSessions, createSession, SessionData } from '@/services/sessions';
import { listImages } from '@/services/images';
import { listQueries } from '@/services/queries';
import { getSessionContext, resetSessionContext } from '@/services/context';
import { Globe, Compass } from 'lucide-react';

export default function DashboardPage() {
  const [sessions, setSessions] = useState<SessionData[]>([]);
  const [sessionId, setSessionId] = useState<string>('');
  const [images, setImages] = useState<RasterMetadata[]>([]);
  const [detectedMode, setDetectedMode] = useState<InputMode | null>(null);
  const [currentTrace, setCurrentTrace] = useState<ExecutionTrace | null>(null);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isSatelliteSearchOpen, setIsSatelliteSearchOpen] = useState(false);
  const [isReportOpen, setIsReportOpen] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [viewMode, setViewMode] = useState<'3d_earth' | '2d_gis'>('3d_earth');

  // Multi-turn interaction states
  const [conversationContext, setConversationContext] = useState<ConversationContext | null>(null);
  const [selectedFeatureForExplain, setSelectedFeatureForExplain] = useState<ExplainFeatureData | null>(null);
  const [isExplainModalOpen, setIsExplainModalOpen] = useState(false);
  const [isExpertMode, setIsExpertMode] = useState(false);
  const [uiActions, setUiActions] = useState<UIAction[]>([]);

  // Helper to load all assets and queries for a given session
  const loadSessionData = useCallback(async (sid: string) => {
    try {
      setSessionId(sid);

      // Fetch conversation memory context
      try {
        const ctxRes = await getSessionContext(sid);
        setConversationContext(ctxRes.conversation_context);
      } catch (ctxErr) {
        console.warn('Could not load session conversation context:', ctxErr);
      }

      // 1. Fetch images for session
      const assets = await listImages(sid);
      const mappedImages: RasterMetadata[] = assets.map((a) => ({
        image_id: a.id,
        filename: a.original_filename,
        content_type: a.file_format,
        width: a.width,
        height: a.height,
        band_count: a.band_count,
        geo_referenced: !!(a.is_georeferenced ?? a.bounds_wgs84),
        crs: a.crs,
        bounds_wgs84: a.bounds_wgs84,
        sensor_type: a.sensor,
        preview_url: a.preview_url || undefined,
      }));
      setImages(mappedImages);

      // Determine mode from loaded images
      if (mappedImages.length === 2) {
        const isCrossModal =
          assets.some((img) => img.modality === 'SAR') &&
          assets.some((img) => img.modality !== 'SAR');
        setDetectedMode(isCrossModal ? 'cross_modal_pair' : 'bi_temporal');
      } else if (mappedImages.length === 1) {
        setDetectedMode('single_image');
      } else {
        setDetectedMode(null);
      }

      // 2. Fetch queries and load latest execution trace
      const queries = await listQueries(sid);
      if (queries && queries.length > 0) {
        const completedQuery =
          queries.find((q) => q.status === 'COMPLETED') || queries[0];
        if (completedQuery) {
          const trace = formatQueryToTrace(completedQuery, sid);
          setCurrentTrace(trace);
        }
      } else {
        setCurrentTrace(null);
      }
    } catch (err) {
      console.error('Failed to load session data:', err);
    }
  }, []);

  // Initialize session and auth on mount
  useEffect(() => {
    const init = async () => {
      try {
        // Ensure authentication token exists
        let token = typeof window !== 'undefined' ? localStorage.getItem('satquery_access_token') : null;
        if (!token) {
          await login('analyst', 'satquery2026');
        }

        // Fetch user sessions
        const res = await listSessions();
        const sessionList = res.results || (Array.isArray(res) ? res : []);
        setSessions(sessionList);

        if (sessionList.length > 0) {
          // Select the first session (showcase flood assessment session)
          await loadSessionData(sessionList[0].id);
        } else {
          // Create an initial default session if none exist
          const newSession = await createSession('Kaziranga & Brahmaputra Basin Assessment');
          setSessions([newSession]);
          await loadSessionData(newSession.id);
        }
      } catch (err) {
        console.error('Initialization error:', err);
      } finally {
        setInitialLoading(false);
      }
    };

    init();
  }, [loadSessionData]);

  const handleSelectSession = (sid: string) => {
    loadSessionData(sid);
  };

  const handleNewSession = async () => {
    try {
      const name = prompt('Enter a name for the new session:', `Session #${sessions.length + 1}`);
      if (!name) return;
      const newSession = await createSession(name);
      setSessions((prev) => [newSession, ...prev]);
      await loadSessionData(newSession.id);
    } catch (err) {
      console.error('Failed to create new session:', err);
    }
  };

  const handleUploadSuccess = (uploadedImages: RasterMetadata[], mode: InputMode) => {
    setImages(uploadedImages);
    setDetectedMode(mode);
    if (sessionId) {
      // Reload session queries & images to ensure full synchronization
      loadSessionData(sessionId);
    }
  };

  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);

  const handleAskThisArea = (aoi: any, promptText?: string) => {
    setPendingPrompt(promptText || 'Analyze what is happening in this designated Area of Interest.');
  };

  const handleResetContext = async () => {
    if (!sessionId) return;
    try {
      const res = await resetSessionContext(sessionId);
      setConversationContext(res.conversation_context);
    } catch (err) {
      console.error('Failed to reset conversation context:', err);
    }
  };

  const handleQueryExecuted = (trace: ExecutionTrace) => {
    setCurrentTrace(trace);
    if (trace.ui_actions && trace.ui_actions.length > 0) {
      setUiActions(trace.ui_actions);
    }
    // Refresh conversation context memory
    if (sessionId) {
      getSessionContext(sessionId)
        .then((res) => setConversationContext(res.conversation_context))
        .catch((err) => console.warn('Could not refresh conversation context:', err));
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-[#070b13] text-slate-100">
      <Header
        detectedMode={detectedMode}
        onOpenUpload={() => setIsUploadOpen(true)}
        onOpenReport={() => setIsReportOpen(true)}
        hasTrace={!!currentTrace}
        sessions={sessions}
        activeSessionId={sessionId}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        onOpenSatelliteSearch={() => setIsSatelliteSearchOpen(true)}
      />

      <main className="flex-1 p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 max-w-[1800px] w-full mx-auto">
        {/* Left / Center Section: Map & Chat (7 Cols) */}
        <div className="lg:col-span-7 flex flex-col gap-5">
          {/* Multi-Turn AI Conversation Context Bar */}
          <ContextBar
            context={conversationContext}
            onResetContext={handleResetContext}
            onSelectPrompt={(prompt) => setPendingPrompt(prompt)}
            isExpertMode={isExpertMode}
            onToggleExpertMode={(expert) => setIsExpertMode(expert)}
          />

          {/* Earth Observatory & 2D Scientific View Switcher */}
          <div className="flex items-center justify-between bg-[#0b1322] border border-slate-800 px-4 py-2.5 rounded-xl">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-300 font-mono tracking-wider">
                VIEWPORT MODE:
              </span>
              <div className="flex items-center bg-slate-900 p-1 rounded-lg border border-slate-800 text-xs">
                <button
                  onClick={() => setViewMode('3d_earth')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition-all font-mono font-medium ${
                    viewMode === '3d_earth'
                      ? 'bg-cyan-950 text-cyan-300 border border-cyan-700 shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Globe className="w-3.5 h-3.5 text-cyan-400" />
                  <span>3D Earth from Orbit</span>
                </button>
                <button
                  onClick={() => setViewMode('2d_gis')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition-all font-mono font-medium ${
                    viewMode === '2d_gis'
                      ? 'bg-indigo-950 text-indigo-300 border border-indigo-700 shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Compass className="w-3.5 h-3.5 text-indigo-400" />
                  <span>2D Scientific GIS Tiles</span>
                </button>
              </div>
            </div>
            <span className="text-[11px] text-slate-500 font-mono hidden sm:inline">
              Copernicus Sentinel-1/2 Real-Time Pipeline
            </span>
          </div>

          <div className="h-[560px] w-full">
            {viewMode === '3d_earth' ? (
              <EarthObservatory
                onAskAI={(prompt) => setPendingPrompt(prompt)}
              />
            ) : (
              <MapViewer
                images={images}
                evidence={currentTrace?.evidence || null}
                onAskThisArea={handleAskThisArea}
                onExplainFeature={(feature) => {
                  setSelectedFeatureForExplain(feature);
                  setIsExplainModalOpen(true);
                }}
                uiActions={uiActions}
              />
            )}
          </div>

          <ChatConsole
            sessionId={sessionId}
            detectedMode={detectedMode}
            hasImages={images.length > 0}
            pendingPrompt={pendingPrompt}
            onClearPendingPrompt={() => setPendingPrompt(null)}
            onQueryExecuted={handleQueryExecuted}
          />
        </div>

        {/* Right Section: Trace & Evidence (5 Cols) */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          <ExecutionTraceTimeline trace={currentTrace} />
          <EvidenceDrawer
            evidence={currentTrace?.evidence || null}
            externalEvidence={currentTrace?.external_evidence || null}
            trace={currentTrace}
          />
        </div>
      </main>

      {/* Modals */}
      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        sessionId={sessionId}
        onUploadSuccess={handleUploadSuccess}
      />

      <SatelliteSearchModal
        isOpen={isSatelliteSearchOpen}
        onClose={() => setIsSatelliteSearchOpen(false)}
        sessionId={sessionId}
        onSceneIngested={() => loadSessionData(sessionId)}
      />

      <ReportModal
        isOpen={isReportOpen}
        onClose={() => setIsReportOpen(false)}
        sessionId={sessionId}
        trace={currentTrace}
      />

      <ClickToExplainModal
        isOpen={isExplainModalOpen}
        onClose={() => setIsExplainModalOpen(false)}
        feature={selectedFeatureForExplain}
        onAskFollowUp={(prompt) => setPendingPrompt(prompt)}
      />
    </div>
  );
}
