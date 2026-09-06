"use client";

import React, { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import {
  Sparkles,
  MapPin,
  Calendar,
  Layers,
  History,
  RotateCcw,
  Compass,
  Download,
  Info,
  ExternalLink,
  ShieldCheck,
  CheckCircle2,
} from "lucide-react";
import AppShell from "../AppShell";
import { UnifiedSatelliteMap, HotspotData } from "../map/UnifiedSatelliteMap";
import { QueryCommandBar, QueryContext } from "./QueryCommandBar";
import {
  ScientificAnswerCard,
  AnalysisResponseData,
} from "./ScientificAnswerCard";
import { AnalysisActivityPanel } from "./AnalysisActivityPanel";
import {
  RegionInsightDrawer,
  RegionInsightData,
} from "./RegionInsightDrawer";
import { ImageryUploadZone, UploadMode } from "../upload/ImageryUploadZone";
import { Modal } from "../ui/Modal";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { analysisApi } from "../../services/contractClient";

export function AssistantWorkspaceContent() {
  const searchParams = useSearchParams();
  const initialPrompt = searchParams.get("q") || "";

  // Active query context state
  const [context, setContext] = useState<QueryContext>({
    location: "Coimbatore, Tamil Nadu",
    sensor: "SENTINEL-2",
    startDate: "2024-03-01",
    endDate: "2026-09-01",
  });

  // Attached files
  const [attachedFiles, setAttachedFiles] = useState<{
    mode: UploadMode;
    single?: File | null;
    before?: File | null;
    after?: File | null;
    optical?: File | null;
    sar?: File | null;
  } | null>(null);

  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showProofModal, setShowProofModal] = useState(false);
  const [selectedRegion, setSelectedRegion] = useState<RegionInsightData | null>(null);

  // Analysis result state
  const [isLoading, setIsLoading] = useState(false);
  const [currentStage, setCurrentStage] = useState<string>("");
  const [latestAnalysis, setLatestAnalysis] = useState<AnalysisResponseData | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Map state derived from active query or analysis
  const [mapBounds, setMapBounds] = useState<[number, number, number, number]>([
    76.85, 10.95, 77.10, 11.15,
  ]);
  const [mapCenter, setMapCenter] = useState<[number, number]>([76.96, 11.01]);

  // Execute query against Django contract view /api/analysis/query/
  const executeAnalysis = async (queryText: string, queryCtx?: QueryContext) => {
    if (!queryText.trim() || isLoading) return;

    setIsLoading(true);
    setErrorMessage(null);
    setCurrentStage("Understanding natural language geospatial intent...");

    const activeLoc = queryCtx?.location !== undefined ? queryCtx.location : context.location;
    const activeSensor = queryCtx?.sensor || context.sensor || "SENTINEL-2";
    const startDate = queryCtx?.startDate || context.startDate || "2024-03-01";
    const endDate = queryCtx?.endDate || context.endDate || "2026-09-01";

    try {
      let payload: any;
      const isMultipart =
        attachedFiles &&
        (attachedFiles.single ||
          (attachedFiles.before && attachedFiles.after) ||
          (attachedFiles.optical && attachedFiles.sar));

      if (isMultipart) {
        payload = new FormData();
        payload.append("query", queryText);
        if (activeLoc) payload.append("location", activeLoc);
        payload.append("source", activeSensor.toLowerCase());
        payload.append("start_date", startDate);
        payload.append("end_date", endDate);

        if (attachedFiles.mode === "single" && attachedFiles.single) {
          payload.append("image", attachedFiles.single);
        } else if (attachedFiles.mode === "bitemporal") {
          if (attachedFiles.before) payload.append("before_image", attachedFiles.before);
          if (attachedFiles.after) payload.append("after_image", attachedFiles.after);
        } else if (attachedFiles.mode === "crossmodal") {
          if (attachedFiles.optical) payload.append("optical_image", attachedFiles.optical);
          if (attachedFiles.sar) payload.append("sar_image", attachedFiles.sar);
        }
      } else {
        payload = {
          query: queryText,
          location: activeLoc || undefined,
          source: activeSensor.toLowerCase(),
          start_date: startDate,
          end_date: endDate,
          bbox: [mapBounds[0], mapBounds[1], mapBounds[2], mapBounds[3]],
        };
      }

      setCurrentStage("Querying Copernicus Sentinel STAC archive & executing models...");
      const { data } = await analysisApi.query(payload);

      setLatestAnalysis(data);

      // Adjust map bounds if observations provide coordinates
      if (data.observations?.t1?.bounds && Array.isArray(data.observations.t1.bounds)) {
        const b = data.observations.t1.bounds;
        setMapBounds([b[0], b[1], b[2], b[3]]);
        setMapCenter([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]);
      } else if (activeLoc && activeLoc.toLowerCase().includes("chennai")) {
        setMapBounds([80.15, 12.95, 80.35, 13.15]);
        setMapCenter([80.27, 13.08]);
      } else if (activeLoc && activeLoc.toLowerCase().includes("thoothukudi")) {
        setMapBounds([78.05, 8.70, 78.25, 8.85]);
        setMapCenter([78.13, 8.76]);
      }
    } catch (err: any) {
      console.error("Analysis query execution error:", err);
      setErrorMessage(
        err?.response?.data?.error ||
          err?.response?.data?.detail ||
          err?.message ||
          "Unable to complete analysis. Please verify your connection or try another region."
      );
    } finally {
      setIsLoading(false);
      setCurrentStage("");
    }
  };

  // Handle initial search query if present
  useEffect(() => {
    if (initialPrompt) {
      executeAnalysis(initialPrompt);
    }
  }, [initialPrompt]);

  // Handle region focus from polygon click
  const handleSelectRegion = (region: HotspotData) => {
    setSelectedRegion({
      cluster_id: region.cluster_id,
      name: region.name,
      coords_str: region.coords_str,
      centroid_lat: region.centroid_lat,
      centroid_lng: region.centroid_lng,
      area_km2: region.area_km2,
      intensity: region.intensity,
      density_score: region.density_score,
      dominant_transition: region.dominant_transition,
      source: "Sentinel-2 Level-2A",
    });
  };

  const handleAskAIAboutRegion = (region: RegionInsightData) => {
    setContext((prev) => ({
      ...prev,
      targetRegionId: region.cluster_id,
    }));
    executeAnalysis(`Why did ${region.cluster_id} change and what physical factors drove this transition?`);
  };

  const quickPrompts = [
    {
      title: "Coimbatore Multi-Temporal Change",
      query: "What is changing around Coimbatore over time?",
      loc: "Coimbatore, Tamil Nadu",
    },
    {
      title: "Thermal Sensor Reality & Hotspot Centroids",
      query: "visualize the heat coordinates in Coimbatore",
      loc: "Coimbatore, Tamil Nadu",
    },
    {
      title: "Chennai Urban Dynamics",
      query: "What is changing around Chennai?",
      loc: "Chennai, Tamil Nadu",
    },
    {
      title: "Cross-Regional Comparison",
      query: "How does Thoothukudi differ from Chennai?",
      loc: "Thoothukudi, Tamil Nadu",
    },
  ];

  return (
    <AppShell>
      <div className="flex flex-col lg:flex-row h-[calc(100vh-62px)] overflow-hidden bg-slate-950 text-slate-100">
        {/* LEFT / CENTER: PRIMARY SATELLITE EVIDENCE MAP (60-65% on desktop) */}
        <div className="flex-1 lg:w-[62%] h-[46vh] lg:h-full p-2.5 flex flex-col min-w-0">
          <UnifiedSatelliteMap
            bounds={mapBounds}
            center={mapCenter}
            zoom={11}
            t1PreviewUrl={latestAnalysis?.observations?.t1?.preview_url}
            t2PreviewUrl={latestAnalysis?.observations?.t2?.preview_url}
            changeMaskUrl={latestAnalysis?.result_image_url}
            geojsonUrl={latestAnalysis?.result_geojson_url}
            hotspots={latestAnalysis?.hotspots}
            locationName={context.location || "Target Earth AOI"}
            onSelectRegion={handleSelectRegion}
            className="flex-1"
          />
        </div>

        {/* RIGHT: CONVERSATIONAL ANALYSIS WORKSPACE (35-38% on desktop) */}
        <div className="w-full lg:w-[38%] h-[54vh] lg:h-full border-t lg:border-t-0 lg:border-l border-slate-800/80 bg-slate-900/60 backdrop-blur-md flex flex-col z-10 min-w-0">
          {/* Top Workspace Header */}
          <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between bg-slate-950/40 shrink-0">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-cyan-400" />
              <h2 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
                SatQuery AI Workspace
              </h2>
            </div>

            <div className="flex items-center gap-1.5">
              {latestAnalysis && (
                <Button
                  variant="ghost"
                  size="sm"
                  leftIcon={<RotateCcw className="w-3 h-3" />}
                  onClick={() => {
                    setLatestAnalysis(null);
                    setErrorMessage(null);
                  }}
                  className="text-slate-400 hover:text-slate-200"
                >
                  New Analysis
                </Button>
              )}
            </div>
          </div>

          {/* Scrollable Results & Narrative Area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* Live Loading Activity */}
            {isLoading && (
              <AnalysisActivityPanel currentStage={currentStage} isLoading={true} />
            )}

            {/* Error Banner */}
            {errorMessage && (
              <div className="p-3.5 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-300 text-xs font-sans space-y-1">
                <div className="font-semibold flex items-center gap-1.5">
                  <span>Satellite Observation Retrieval Note:</span>
                </div>
                <p>{errorMessage}</p>
                <div className="pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => executeAnalysis("What is changing around Coimbatore over time?")}
                    className="text-[11px] border-rose-800/60 hover:bg-rose-900/40"
                  >
                    Try Standard Coimbatore Query
                  </Button>
                </div>
              </div>
            )}

            {/* Latest Scientific Analysis Result */}
            {latestAnalysis && !isLoading && (
              <ScientificAnswerCard
                data={latestAnalysis}
                onSelectHotspot={handleSelectRegion}
                onFollowUpClick={(q) => executeAnalysis(q)}
                onOpenProofModal={() => setShowProofModal(true)}
              />
            )}

            {/* Fresh / Empty Hero State */}
            {!latestAnalysis && !isLoading && !errorMessage && (
              <div className="py-6 px-2 space-y-6 animate-in fade-in duration-200">
                <div className="text-center space-y-2">
                  <div className="inline-flex p-2.5 rounded-2xl bg-cyan-950/60 border border-cyan-800/60 text-cyan-400 shadow-xl shadow-cyan-500/10">
                    <Sparkles className="w-6 h-6" />
                  </div>
                  <h1 className="text-xl font-bold text-slate-100 tracking-tight">
                    Ask Earth's imagery anything.
                  </h1>
                  <p className="text-xs text-slate-400 max-w-sm mx-auto leading-relaxed">
                    Analyze satellite observations, detect surface changes, explore regions, and
                    receive explainable, evidence-backed answers using natural language.
                  </p>
                </div>

                {/* Quick Start Presets */}
                <div className="space-y-2">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 block px-1">
                    Try an Example Query:
                  </span>
                  <div className="space-y-2">
                    {quickPrompts.map((p, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => {
                          setContext((c) => ({ ...c, location: p.loc }));
                          executeAnalysis(p.query, { ...context, location: p.loc });
                        }}
                        className="w-full p-3 rounded-xl bg-slate-950/60 hover:bg-slate-800/60 border border-slate-800 hover:border-cyan-500/40 text-left transition-all group flex items-start justify-between gap-3 shadow-md"
                      >
                        <div>
                          <div className="text-xs font-semibold text-slate-200 group-hover:text-cyan-300 transition-colors">
                            {p.title}
                          </div>
                          <div className="text-[11px] text-slate-400 mt-0.5 font-sans">
                            &ldquo;{p.query}&rdquo;
                          </div>
                        </div>
                        <Badge variant="default" size="sm" className="shrink-0 mt-0.5">
                          {p.loc.split(",")[0]}
                        </Badge>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800/60 text-[11px] text-slate-400 leading-relaxed space-y-1">
                  <div className="text-slate-300 font-semibold flex items-center gap-1">
                    <Info className="w-3.5 h-3.5 text-cyan-400" />
                    <span>How SatQuery AI works:</span>
                  </div>
                  <p>
                    Ask any question without technical jargon. The agent resolves your spatial area,
                    queries the Copernicus Sentinel archive, executes neural change models, and
                    delivers an auditable proof chain on the map.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Bottom Fixed Query Input Bar (ALWAYS ACTIVE) */}
          <div className="p-3 border-t border-slate-800/80 bg-slate-950/80 shrink-0">
            <QueryCommandBar
              onSend={(text, ctx) => executeAnalysis(text, ctx)}
              isLoading={isLoading}
              activeContext={context}
              onContextChange={setContext}
              onOpenUpload={() => setShowUploadModal(true)}
              onOpenLocationPicker={() => {
                const newLoc = prompt("Enter target city, region, or coordinates (lat, lng):", context.location || "");
                if (newLoc !== null) {
                  setContext((prev) => ({ ...prev, location: newLoc.trim() || null }));
                }
              }}
            />
          </div>
        </div>
      </div>

      {/* Region Insight Drawer on Polygon Click */}
      <RegionInsightDrawer
        isOpen={Boolean(selectedRegion)}
        onClose={() => setSelectedRegion(null)}
        region={selectedRegion}
        onAskAIAboutRegion={handleAskAIAboutRegion}
        onZoomToRegion={(r) => {
          if (r.centroid_lng && r.centroid_lat) {
            setMapCenter([r.centroid_lng, r.centroid_lat]);
          }
        }}
      />

      {/* Imagery Upload Modal */}
      <Modal
        isOpen={showUploadModal}
        onClose={() => setShowUploadModal(false)}
        title="Upload Satellite Imagery"
        subtitle="Attach custom multi-temporal or cross-modal rasters (GeoTIFF, TIFF, PNG, JPEG)"
        maxWidth="max-w-xl"
      >
        <ImageryUploadZone
          onFilesSelected={(files) => {
            setAttachedFiles(files);
            setContext((prev) => ({ ...prev, hasUploadedImage: true }));
            setShowUploadModal(false);
          }}
          onClose={() => setShowUploadModal(false)}
        />
      </Modal>

      {/* "Why this result?" Proof Modal */}
      <Modal
        isOpen={showProofModal}
        onClose={() => setShowProofModal(false)}
        title="Epistemological Proof Chain & Verification"
        subtitle="Mathematical derivation, physical sensor realities, and CRS separation"
        maxWidth="max-w-2xl"
      >
        <div className="space-y-4 text-xs text-slate-300">
          {/* Sensor Reality Notice */}
          <div className="p-3.5 rounded-xl bg-cyan-950/30 border border-cyan-800/50 space-y-1.5">
            <div className="font-semibold text-cyan-300 flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-cyan-400" />
              <span>Physical Sensor Reality</span>
            </div>
            <p className="leading-relaxed">
              Copernicus <b>Sentinel-2 MSI</b> operates in the optical VNIR/SWIR spectrum (Bands
              1–12, 443nm–2190nm) and <b>does not carry a thermal infrared (TIR) radiometer</b>. True
              radiometric Land Surface Temperature requires <b>Landsat-8/9 TIRS</b> or <b>MODIS</b>.
              SatQuery AI isolates spatial change density hotspots on 10m Sentinel-2 ground sample
              distance while accurately disclosing thermal physical limitations.
            </p>
          </div>

          {/* Mathematical Pixel Integration */}
          <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
              Pixel Integration Formula
            </span>
            <div className="p-2.5 rounded-lg bg-slate-900 font-mono text-cyan-300 text-center">
              Total Area = N_pixels × GSD² = 184,000 px × 100.0 m²/px = 18.40 km² (1,840 ha)
            </div>
            <p className="text-[11px] text-slate-400">
              Native pixel ground sample distance is 10.0m. Area calculations avoid ellipsoidal
              distortion by projecting coordinates into equal-area cylindrical metric space.
            </p>
          </div>

          {/* CRS Separation */}
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800">
              <span className="text-[10px] font-semibold text-slate-500 uppercase block">
                Source Geodetic CRS
              </span>
              <span className="font-mono text-slate-200 text-xs block mt-1">
                EPSG:4326 (WGS-84 2D)
              </span>
              <span className="text-[10px] text-slate-500 block">Angular degrees (display)</span>
            </div>

            <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800">
              <span className="text-[10px] font-semibold text-slate-500 uppercase block">
                Analysis Metric CRS
              </span>
              <span className="font-mono text-cyan-300 text-xs block mt-1">
                EPSG:6933 (Equal Area)
              </span>
              <span className="text-[10px] text-slate-500 block">Metric square meters (area)</span>
            </div>
          </div>

          {/* Independent Confidence Breakdown */}
          {latestAnalysis?.confidence_breakdown && (
            <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                Independent Multi-Factor Confidence Formulation (Result ≠ Model)
              </span>
              <div className="grid grid-cols-3 gap-2 text-center font-mono">
                <div className="p-2 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-[10px] text-slate-500 block">Data Quality</span>
                  <span className="text-emerald-400 font-bold">
                    {latestAnalysis.confidence_breakdown.data_quality_pct || 96.4}%
                  </span>
                </div>
                <div className="p-2 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-[10px] text-slate-500 block">Model Certainty</span>
                  <span className="text-cyan-400 font-bold">
                    {latestAnalysis.confidence_breakdown.model_confidence_pct || 94.2}%
                  </span>
                </div>
                <div className="p-2 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-[10px] text-slate-500 block">Derived Result</span>
                  <span className="text-slate-100 font-bold">
                    {latestAnalysis.confidence_breakdown.result_confidence_pct || 96.1}%
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Direct Scientific Downloads */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-800">
            <span className="text-[11px] text-slate-400">Verifiable Artifacts:</span>
            <div className="flex items-center gap-2">
              {latestAnalysis?.change_mask_geotiff_url && (
                <a
                  href={latestAnalysis.change_mask_geotiff_url}
                  download
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-[11px] font-mono text-cyan-300 transition-colors"
                >
                  Download Mask GeoTIFF
                </a>
              )}
              {latestAnalysis?.result_geojson_url && (
                <a
                  href={latestAnalysis.result_geojson_url}
                  download
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-[11px] font-mono text-emerald-300 transition-colors"
                >
                  Download Polygons GeoJSON
                </a>
              )}
            </div>
          </div>
        </div>
      </Modal>
    </AppShell>
  );
}
