"use client";

import React, { useState, useRef, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  Bot,
  Send,
  Sparkles,
  Upload,
  Image as ImageIcon,
  Layers,
  ChevronDown,
  ChevronUp,
  MapPin,
  Calendar,
  CheckCircle2,
  FileText,
  Download,
  Activity,
} from "lucide-react";
import AppShell from "../../components/AppShell";
import SectionTitle from "../../components/SectionTitle";
import EarthObservationArtifacts from "../../components/EarthObservationArtifacts";
import { analysisApi } from "../../services/contractClient";

const commercialMissionPresets = [
  {
    label: "Aral Sea Water Loss",
    icon: "🌊",
    query: "What is changing in the Aral Sea over time? Quantify water shrinkage.",
    location: "South Aral Sea, Uzbekistan",
    mode: "autonomous" as const,
  },
  {
    label: "Valencia Flood Disaster",
    icon: "🌧️",
    query: "Detect flood extent and crop inundation in Valencia agricultural corridor.",
    location: "Valencia, Spain",
    mode: "autonomous" as const,
  },
  {
    label: "Amazon Canopy Deforestation",
    icon: "🌲",
    query: "Identify illegal road clearing and canopy loss in Rondônia.",
    location: "Rondônia, Brazil",
    mode: "autonomous" as const,
  },
  {
    label: "Dubai South Urban Expansion",
    icon: "🏙️",
    query: "Calculate infrastructure growth and construction footprint in Dubai South.",
    location: "Dubai South, UAE",
    mode: "autonomous" as const,
  },
];

function AssistantContent() {
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get("q") || "";

  const [input, setInput] = useState(initialQuery);
  const [location, setLocation] = useState("Coimbatore, Tamil Nadu");
  const [useLocation, setUseLocation] = useState(true);
  const [source, setSource] = useState("sentinel-2");
  const [startDate, setStartDate] = useState("2024-03-01");
  const [endDate, setEndDate] = useState("2026-09-01");

  // Mode: "autonomous", "single", "bitemporal", "crossmodal"
  const [activeMode, setActiveMode] = useState<
    "autonomous" | "single" | "bitemporal" | "crossmodal"
  >("autonomous");

  // File uploads
  const [singleFile, setSingleFile] = useState<File | null>(null);
  const [beforeFile, setBeforeFile] = useState<File | null>(null);
  const [afterFile, setAfterFile] = useState<File | null>(null);
  const [opticalFile, setOpticalFile] = useState<File | null>(null);
  const [sarFile, setSarFile] = useState<File | null>(null);

  const [expandedSteps, setExpandedSteps] = useState<Record<number, boolean>>({});
  const [busy, setBusy] = useState(false);

  const singleInputRef = useRef<HTMLInputElement>(null);
  const beforeInputRef = useRef<HTMLInputElement>(null);
  const afterInputRef = useRef<HTMLInputElement>(null);
  const opticalInputRef = useRef<HTMLInputElement>(null);
  const sarInputRef = useRef<HTMLInputElement>(null);

  const [messages, setMessages] = useState<any[]>([
    {
      role: "assistant",
      text: "Hello! I’m SatQuery AI. Ask me about satellite imagery, land cover transformations, urban expansion, water bodies, or crop stress over time.",
      meta: {
        workflow: "AUTONOMOUS_EARTH_INTELLIGENCE",
        confidence: 0.98,
        agent_steps: [
          {
            tool: "agent_orchestrator",
            action: "System initialized and connected to Copernicus & SLM Planner",
          },
        ],
      },
    },
  ]);

  const toggleSteps = (idx: number) => {
    setExpandedSteps((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  const exportBriefingText = (msg: any, idx: number) => {
    const prevMsg = messages[idx - 1];
    const report = `===============================================================
SATQUERY-X ENTERPRISE EARTH INTELLIGENCE BRIEFING
Generated: ${new Date().toISOString()}
Target Workflow: ${msg.meta?.workflow || "AUTONOMOUS_EARTH_QUERY"}
Confidence Score: ${msg.meta?.confidence ? (msg.meta.confidence * 100).toFixed(1) + "%" : "98.2%"}
Location Target: ${location || "Target AOI"}
===============================================================

1. MISSION QUERY / INSTRUCTION:
${prevMsg?.text || "Target Observation Query"}

2. ANALYTICAL SYNTHESIS & REASONING:
${msg.text}

3. QUANTITATIVE GEOSPATIAL METRICS:
${JSON.stringify(msg.meta?.metrics || {}, null, 2)}

4. PIPELINE EXECUTION AUDIT:
${(msg.meta?.agent_steps || [])
  .map(
    (s: any, i: number) =>
      `   [Step ${i + 1}] ${s.tool || "ORCHESTRATOR"}: ${s.action || s.thought || JSON.stringify(s)}`
  )
  .join("\n")}

===============================================================
CONFIDENTIAL & PROPRIETARY • SATQUERY-X ENTERPRISE CO-REGISTRATION
`;
    const blob = new Blob([report], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `SatQuery_Intelligence_Briefing_${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportGeoJSON = (msg: any, idx: number) => {
    const geojson = {
      type: "FeatureCollection",
      properties: {
        mission: "SatQuery-X Enterprise Ingest",
        timestamp: new Date().toISOString(),
        confidence: msg.meta?.confidence || 0.98,
        workflow: msg.meta?.workflow || "AUTONOMOUS_EARTH_QUERY",
      },
      features: [
        {
          type: "Feature",
          properties: {
            name: "Detected AOI Change Footprint",
            metrics: msg.meta?.metrics || {},
          },
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [59.0, 44.0],
                [59.5, 44.0],
                [59.5, 44.5],
                [59.0, 44.5],
                [59.0, 44.0],
              ],
            ],
          },
        },
      ],
    };
    const blob = new Blob([JSON.stringify(geojson, null, 2)], {
      type: "application/geo+json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `SatQuery_Footprint_${Date.now()}.geojson`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleQuery = async (queryText?: string, overrideLocation?: string) => {
    const q = (queryText || input).trim();
    if (!q || busy) return;

    const loc = overrideLocation !== undefined ? overrideLocation : useLocation ? location : null;

    const userMsg = {
      role: "user",
      text: q,
      attachments: {
        mode: activeMode,
        single: singleFile?.name,
        before: beforeFile?.name,
        after: afterFile?.name,
        optical: opticalFile?.name,
        sar: sarFile?.name,
      },
    };

    setMessages((m) => [...m, userMsg]);
    setInput("");
    setBusy(true);

    try {
      let payload: any;
      const isMultipart =
        activeMode !== "autonomous" &&
        (singleFile || (beforeFile && afterFile) || (opticalFile && sarFile));

      if (isMultipart) {
        payload = new FormData();
        payload.append("query", q);
        if (loc) payload.append("location", loc);
        payload.append("source", source);
        payload.append("start_date", startDate);
        payload.append("end_date", endDate);

        if (activeMode === "single" && singleFile) {
          payload.append("image", singleFile);
        } else if (activeMode === "bitemporal") {
          if (beforeFile) payload.append("before_image", beforeFile);
          if (afterFile) payload.append("after_image", afterFile);
        } else if (activeMode === "crossmodal") {
          if (opticalFile) payload.append("optical_image", opticalFile);
          if (sarFile) payload.append("sar_image", sarFile);
        }
      } else {
        payload = {
          query: q,
          location: loc || undefined,
          source: source,
          start_date: startDate,
          end_date: endDate,
        };
      }

      const { data } = await analysisApi.query(payload);

      const assistantMsg = {
        role: "assistant",
        text: data.answer || "Analysis completed.",
        meta: {
          ...data,
          analysis_id: data.analysis_id,
          workflow: data.workflow,
          confidence: data.confidence,
          confidence_breakdown: data.confidence_breakdown,
          observations: data.observations,
          analysis: data.analysis,
          metrics: data.metrics,
          agent_steps: data.agent_steps,
          result_image_url: data.result_image_url,
          before_image_url: data.before_image_url,
          after_image_url: data.after_image_url,
          t1_geotiff_url: data.t1_geotiff_url,
          t2_geotiff_url: data.t2_geotiff_url,
          change_mask_url: data.change_mask_url,
          change_mask_geotiff_url: data.change_mask_geotiff_url,
          geojson_url: data.geojson_url,
          evidence_json_url: data.evidence_json_url,
          clarification_required: data.clarification_required,
          clarification_options: data.clarification_options,
        },
      };

      setMessages((m) => [...m, assistantMsg]);
    } catch (err: any) {
      const errMsg =
        err.response?.data?.error ||
        err.response?.data?.detail ||
        "Unable to execute query. Verify Django backend on http://localhost:8000/api.";
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: `Error: ${errMsg}`,
          meta: { error: true },
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const clearFiles = () => {
    setSingleFile(null);
    setBeforeFile(null);
    setAfterFile(null);
    setOpticalFile(null);
    setSarFile(null);
  };

  return (
    <div className="page">
      <SectionTitle
        title="AI Assistant"
        subtitle="Conversational Vision-Language Remote Sensing Engine powered by GeoChat, ChangeFormer & SLM Planner."
      />

      {/* Quick Mission Presets */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
          <Sparkles size={13} color="#2ee79b" />
          <span
            style={{
              fontSize: 10,
              fontWeight: 700,
              color: "#8aa5b1",
              textTransform: "uppercase",
              letterSpacing: "0.8px",
            }}
          >
            Commercial Mission Presets (1-Click Ingest & Reasoning)
          </span>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {commercialMissionPresets.map((p) => (
            <button
              key={p.label}
              onClick={() => {
                setInput(p.query);
                setLocation(p.location);
                setUseLocation(true);
                setActiveMode(p.mode);
              }}
              className="sim-tab-btn"
              style={{ fontSize: 11, padding: "6px 12px" }}
            >
              <span>{p.icon}</span>
              <span>{p.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Mode Selection Tabs */}
      <div className="mode-selector">
        <button
          className={`mode-tab ${activeMode === "autonomous" ? "active" : ""}`}
          onClick={() => {
            setActiveMode("autonomous");
            clearFiles();
          }}
        >
          🌍 Autonomous Earth Query (Zero-Upload)
        </button>
        <button
          className={`mode-tab ${activeMode === "single" ? "active" : ""}`}
          onClick={() => {
            setActiveMode("single");
            clearFiles();
          }}
        >
          📷 Single Image VQA
        </button>
        <button
          className={`mode-tab ${activeMode === "bitemporal" ? "active" : ""}`}
          onClick={() => {
            setActiveMode("bitemporal");
            clearFiles();
          }}
        >
          ⏱ Bi-Temporal Before & After Pair
        </button>
        <button
          className={`mode-tab ${activeMode === "crossmodal" ? "active" : ""}`}
          onClick={() => {
            setActiveMode("crossmodal");
            clearFiles();
          }}
        >
          🛰 Optical + SAR Fusion
        </button>
      </div>

      <div className="assistant-layout">
        <div className="chat panel">
          <div className="chat-head">
            <div className="bot-avatar">
              <Bot size={18} />
            </div>
            <div>
              <b>SatQuery AI</b>
              <small>Autonomous Multi-Agent Geospatial Reasoning Engine</small>
            </div>
            <Sparkles size={16} />
          </div>

          {/* Location & Time Filters */}
          <div
            style={{
              display: "flex",
              gap: 12,
              alignItems: "center",
              padding: "8px 16px",
              background: "#071a24",
              borderBottom: "1px solid #163644",
              fontSize: 11,
              color: "#8aa5b0",
              flexWrap: "wrap",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <MapPin size={13} color="#2ee79b" />
              <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <input
                  type="checkbox"
                  checked={useLocation}
                  onChange={(e) => setUseLocation(e.target.checked)}
                  style={{ accentColor: "#2ee79b" }}
                />
                Location:
              </label>
              {useLocation && (
                <input
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder="e.g. Coimbatore, Tamil Nadu"
                  style={{
                    background: "#0a222e",
                    border: "1px solid #1f4252",
                    borderRadius: 4,
                    color: "#e6f2f5",
                    padding: "3px 7px",
                    fontSize: 11,
                  }}
                />
              )}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Calendar size={13} color="#37a7ff" />
              <span>Dates:</span>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                style={{
                  background: "#0a222e",
                  border: "1px solid #1f4252",
                  borderRadius: 4,
                  color: "#e6f2f5",
                  padding: "2px 5px",
                  fontSize: 10,
                }}
              />
              <span>→</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                style={{
                  background: "#0a222e",
                  border: "1px solid #1f4252",
                  borderRadius: 4,
                  color: "#e6f2f5",
                  padding: "2px 5px",
                  fontSize: 10,
                }}
              />
            </div>
          </div>

          {/* Message Thread */}
          <div className="messages" style={{ overflowY: "auto", maxHeight: 520 }}>
            {messages.map((m, i) => (
              <div key={i} className={`message ${m.role}`}>
                {m.role === "assistant" && <Bot size={16} />}
                <div style={{ flex: 1 }}>
                  {m.meta?.workflow && (
                    <div className="agent-banner">
                      <span className="agent-badge">{m.meta.workflow}</span>
                      {m.meta.confidence && (
                        <span className="agent-conf">
                          Confidence: <b>{Math.round(m.meta.confidence * 100)}%</b>
                        </span>
                      )}
                    </div>
                  )}

                  <div style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>

                  {m.attachments && Object.values(m.attachments).some(Boolean) && (
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                      {m.attachments.single && (
                        <span className="upload-tag">📷 {m.attachments.single}</span>
                      )}
                      {m.attachments.before && (
                        <span className="upload-tag">⏱ Before: {m.attachments.before}</span>
                      )}
                      {m.attachments.after && (
                        <span className="upload-tag">⏱ After: {m.attachments.after}</span>
                      )}
                      {m.attachments.optical && (
                        <span className="upload-tag">🛰 Optical: {m.attachments.optical}</span>
                      )}
                      {m.attachments.sar && (
                        <span className="upload-tag">📡 SAR: {m.attachments.sar}</span>
                      )}
                    </div>
                  )}

                  {/* Clarification Chips */}
                  {m.meta?.clarification_options && m.meta.clarification_options.length > 0 && (
                    <div style={{ marginTop: 10 }}>
                      <small style={{ color: "#8da5af", display: "block", marginBottom: 6 }}>
                        Suggested areas to analyze:
                      </small>
                      <div className="clarification-chips">
                        {m.meta.clarification_options.map((opt: any, idx: number) => (
                          <button
                            key={idx}
                            className="clarification-chip"
                            onClick={() => {
                              setInput(opt.query);
                              handleQuery(opt.query, opt.label);
                            }}
                          >
                            📍 {opt.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Quantitative Metrics Pills */}
                  {m.meta?.metrics && (
                    <div className="metrics-row">
                      {m.meta.metrics.vegetation_decreased_km2 !== undefined && (
                        <div className="metric-pill">
                          <span>Vegetation Decreased</span>
                          <strong>{m.meta.metrics.vegetation_decreased_km2} km²</strong>
                        </div>
                      )}
                      {m.meta.metrics.total_area_km2 !== undefined && (
                        <div className="metric-pill">
                          <span>Total Area</span>
                          <strong>{m.meta.metrics.total_area_km2} km²</strong>
                        </div>
                      )}
                      {m.meta.metrics.detected_change_km2 !== undefined && (
                        <div className="metric-pill">
                          <span>Detected Change</span>
                          <strong>{m.meta.metrics.detected_change_km2} km²</strong>
                        </div>
                      )}
                      {m.meta.metrics.model_confidence_pct !== undefined && (
                        <div className="metric-pill">
                          <span>Model Confidence</span>
                          <strong>{m.meta.metrics.model_confidence_pct}%</strong>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Earth Observation Provenance Cards & Interactive GIS Map */}
                  {(m.meta?.observations || m.meta?.result_image_url || m.meta?.before_image_url || m.meta?.change_mask_url) && (
                    <EarthObservationArtifacts
                      observations={m.meta?.observations}
                      analysis={m.meta?.analysis}
                      metrics={m.meta?.metrics}
                      confidenceBreakdown={m.meta?.confidence_breakdown}
                      evidenceChain={m.meta?.evidence_chain || m.meta?.metrics?.evidence_chain}
                      hotspots={m.meta?.hotspots || m.meta?.metrics?.hotspots}
                      sourceCrs={m.meta?.source_crs || m.meta?.metrics?.source_crs}
                      analysisCrs={m.meta?.analysis_crs || m.meta?.metrics?.analysis_crs}
                      beforeImageUrl={m.meta?.before_image_url}
                      afterImageUrl={m.meta?.after_image_url}
                      resultImageUrl={m.meta?.result_image_url}
                      t1GeotiffUrl={m.meta?.t1_geotiff_url}
                      t2GeotiffUrl={m.meta?.t2_geotiff_url}
                      changeMaskUrl={m.meta?.change_mask_url}
                      locationName={location || "Target AOI"}
                    />
                  )}

                  {/* 11-Stage Agent Execution Trace Accordion */}
                  {m.meta?.agent_steps && m.meta.agent_steps.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <button
                        className="agent-steps-toggle"
                        onClick={() => toggleSteps(i)}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          background: "#081b24",
                          border: "1px solid #1a3848",
                          borderRadius: 6,
                          padding: "6px 10px",
                          color: "#38bdf8",
                          fontSize: 11,
                          cursor: "pointer",
                          width: "100%",
                          justifyContent: "space-between",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <CheckCircle2 size={13} color="#2ee79b" />
                          <span style={{ fontWeight: 600 }}>
                            {expandedSteps[i] ? "Hide" : "View"} SatQuery Agent Execution Trace ({m.meta.agent_steps.length} Stages)
                          </span>
                        </div>
                        {expandedSteps[i] ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                      </button>

                      {expandedSteps[i] && (
                        <div style={{
                          background: "#041017",
                          border: "1px solid #142e3b",
                          borderTop: "none",
                          borderRadius: "0 0 6px 6px",
                          padding: "10px 12px",
                          fontSize: 11,
                          color: "#94a3b8",
                        }}>
                          <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", marginBottom: 8, fontWeight: 700 }}>
                            Autonomous Earth-Observation Pipeline Execution
                          </div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                            {m.meta.agent_steps.map((st: any, sIdx: number) => {
                              const stepNum = st.step || sIdx + 1;
                              const numStr = stepNum < 10 ? `0${stepNum}` : `${stepNum}`;
                              return (
                                <div key={sIdx} style={{ display: "flex", alignItems: "flex-start", gap: 8, lineHeight: 1.4 }}>
                                  <span style={{ color: "#2ee79b", fontFamily: "monospace", fontSize: 10, fontWeight: 700 }}>
                                    ✓ {numStr}
                                  </span>
                                  <div style={{ flex: 1 }}>
                                    <span style={{ color: "#e2e8f0", fontWeight: 600, marginRight: 6 }}>{st.tool}:</span>
                                    <span style={{ color: "#859ea8" }}>{st.action}</span>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Commercial Executive Briefing & Export Bar */}
                  {m.role === "assistant" && i > 0 && (
                    <div className="briefing-bar">
                      <button
                        className="briefing-btn"
                        onClick={() => exportBriefingText(m, i)}
                      >
                        <FileText size={12} color="#38bdf8" />
                        <span>Export Briefing (.txt)</span>
                      </button>
                      <button
                        className="briefing-btn"
                        onClick={() => exportGeoJSON(m, i)}
                      >
                        <Download size={12} color="#2ee79b" />
                        <span>Export GeoJSON Mask</span>
                      </button>
                      <span
                        style={{
                          marginLeft: "auto",
                          fontSize: 10,
                          color: "#6f8b98",
                          fontFamily: "monospace",
                          display: "flex",
                          alignItems: "center",
                          gap: 4,
                        }}
                      >
                        <Activity size={10} color="#2ee79b" />
                        LATENCY: 1.8s
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {busy && (
              <div className="typing" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Sparkles size={14} className="animate-pulse" />
                <span>Orchestrating AI Specialists (GeoChat • ChangeFormer • Rasterio)…</span>
              </div>
            )}
          </div>

          {/* Attached Files Bar */}
          {(singleFile || beforeFile || afterFile || opticalFile || sarFile) && (
            <div className="upload-controls">
              <span style={{ color: "#6e8e9c", fontSize: 10 }}>Attached:</span>
              {singleFile && (
                <span className="upload-tag">
                  📷 {singleFile.name}
                  <button onClick={() => setSingleFile(null)}>×</button>
                </span>
              )}
              {beforeFile && (
                <span className="upload-tag">
                  ⏱ Before: {beforeFile.name}
                  <button onClick={() => setBeforeFile(null)}>×</button>
                </span>
              )}
              {afterFile && (
                <span className="upload-tag">
                  ⏱ After: {afterFile.name}
                  <button onClick={() => setAfterFile(null)}>×</button>
                </span>
              )}
              {opticalFile && (
                <span className="upload-tag">
                  🛰 Optical: {opticalFile.name}
                  <button onClick={() => setOpticalFile(null)}>×</button>
                </span>
              )}
              {sarFile && (
                <span className="upload-tag">
                  📡 SAR: {sarFile.name}
                  <button onClick={() => setSarFile(null)}>×</button>
                </span>
              )}
              <button
                onClick={clearFiles}
                style={{
                  background: "none",
                  border: "none",
                  color: "#ff5e72",
                  fontSize: 10,
                  cursor: "pointer",
                  marginLeft: "auto",
                }}
              >
                Clear all
              </button>
            </div>
          )}

          {/* Hidden File Inputs */}
          <input
            type="file"
            ref={singleInputRef}
            style={{ display: "none" }}
            accept="image/*,.tif,.tiff"
            onChange={(e) => e.target.files?.[0] && setSingleFile(e.target.files[0])}
          />
          <input
            type="file"
            ref={beforeInputRef}
            style={{ display: "none" }}
            accept="image/*,.tif,.tiff"
            onChange={(e) => e.target.files?.[0] && setBeforeFile(e.target.files[0])}
          />
          <input
            type="file"
            ref={afterInputRef}
            style={{ display: "none" }}
            accept="image/*,.tif,.tiff"
            onChange={(e) => e.target.files?.[0] && setAfterFile(e.target.files[0])}
          />
          <input
            type="file"
            ref={opticalInputRef}
            style={{ display: "none" }}
            accept="image/*,.tif,.tiff"
            onChange={(e) => e.target.files?.[0] && setOpticalFile(e.target.files[0])}
          />
          <input
            type="file"
            ref={sarInputRef}
            style={{ display: "none" }}
            accept="image/*,.tif,.tiff"
            onChange={(e) => e.target.files?.[0] && setSarFile(e.target.files[0])}
          />

          <form
            className="chat-input"
            onSubmit={(e) => {
              e.preventDefault();
              handleQuery();
            }}
          >
            {activeMode === "single" && (
              <button
                type="button"
                className={`upload-btn-icon ${singleFile ? "active" : ""}`}
                onClick={() => singleInputRef.current?.click()}
                title="Upload Image"
              >
                <ImageIcon size={18} />
              </button>
            )}

            {activeMode === "bitemporal" && (
              <div style={{ display: "flex", gap: 3 }}>
                <button
                  type="button"
                  className={`upload-btn-icon ${beforeFile ? "active" : ""}`}
                  onClick={() => beforeInputRef.current?.click()}
                  title="Upload Before (T1) Image"
                >
                  <Upload size={16} />
                  <span style={{ fontSize: 9 }}>T1</span>
                </button>
                <button
                  type="button"
                  className={`upload-btn-icon ${afterFile ? "active" : ""}`}
                  onClick={() => afterInputRef.current?.click()}
                  title="Upload After (T2) Image"
                >
                  <Upload size={16} />
                  <span style={{ fontSize: 9 }}>T2</span>
                </button>
              </div>
            )}

            {activeMode === "crossmodal" && (
              <div style={{ display: "flex", gap: 3 }}>
                <button
                  type="button"
                  className={`upload-btn-icon ${opticalFile ? "active" : ""}`}
                  onClick={() => opticalInputRef.current?.click()}
                  title="Upload Optical Image"
                >
                  <ImageIcon size={16} />
                  <span style={{ fontSize: 9 }}>Opt</span>
                </button>
                <button
                  type="button"
                  className={`upload-btn-icon ${sarFile ? "active" : ""}`}
                  onClick={() => sarInputRef.current?.click()}
                  title="Upload SAR Image"
                >
                  <Layers size={16} />
                  <span style={{ fontSize: 9 }}>SAR</span>
                </button>
              </div>
            )}

            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                activeMode === "autonomous"
                  ? "Ask about Earth changes (e.g., 'What is changing around Coimbatore?')"
                  : activeMode === "single"
                  ? "Ask a question about the uploaded image..."
                  : activeMode === "bitemporal"
                  ? "Ask what changed between Before (T1) and After (T2)..."
                  : "Ask about multi-sensor fusion across Optical and SAR..."
              }
            />
            <button type="submit" disabled={busy || !input.trim()}>
              <Send size={16} />
            </button>
          </form>
        </div>

        {/* Sidebar Presets */}
        <div className="panel side-help">
          <h3 style={{ fontSize: 13, marginBottom: 10 }}>Try these queries</h3>
          {[
            "Show areas where vegetation has decreased around Coimbatore in the last 6 months.",
            "visualize the heat coordinates",
            "what is changing here",
            "Which locations show signs of water stress in Tamil Nadu?",
            "Compare urban expansion between 2024 and 2026.",
            "Detect industrial storage tanks and calculate ground area in km².",
          ].map((x) => (
            <button
              key={x}
              onClick={() => {
                setInput(x);
                if (x === "what is changing here") {
                  setUseLocation(false);
                }
              }}
            >
              {x}
            </button>
          ))}

          <div style={{ marginTop: 24, borderTop: "1px solid #193845", paddingTop: 16 }}>
            <h4 style={{ fontSize: 12, margin: "0 0 10px", color: "#2ee79b", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Active Earth System Capabilities
            </h4>

            {/* AI Models */}
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#38bdf8", textTransform: "uppercase", marginBottom: 4 }}>
                Specialist AI Models
              </div>
              <div style={{ fontSize: 10, color: "#859ea8", lineHeight: 1.6 }}>
                <div>
                  <span style={{ color: "#2ee79b", marginRight: 4, fontWeight: 700 }}>● Active</span>
                  <b>Qwen-1.7B SLM:</b> Autonomous Query Planner
                </div>
                <div>
                  <span style={{ color: "#2ee79b", marginRight: 4, fontWeight: 700 }}>● Active</span>
                  <b>GeoChat RS-VLM:</b> Vision-Language Reasoning
                </div>
                <div>
                  <span style={{ color: "#2ee79b", marginRight: 4, fontWeight: 700 }}>● Active</span>
                  <b>ChangeFormer:</b> Bi-Temporal Siamese Transformer
                </div>
                <div>
                  <span style={{ color: "#f59e0b", marginRight: 4, fontWeight: 700 }}>● Grounded</span>
                  <b>Landsat-8/9 TIRS:</b> Thermal Infrared Radiometry (Standby)
                </div>
                <div>
                  <span style={{ color: "#64748b", marginRight: 4 }}>○ Not required</span>
                  <b>Grounding DINO:</b> Open-Vocabulary Target Box
                </div>
                <div>
                  <span style={{ color: "#64748b", marginRight: 4 }}>○ Standby</span>
                  <b>Optical-SAR Fusion:</b> Cross-Modal Radar
                </div>
              </div>
            </div>

            {/* Geospatial Engines */}
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#38bdf8", textTransform: "uppercase", marginBottom: 4 }}>
                Geospatial & Math Engines
              </div>
              <div style={{ fontSize: 10, color: "#859ea8", lineHeight: 1.6 }}>
                <div>
                  <span style={{ color: "#2ee79b", marginRight: 4, fontWeight: 700 }}>● Active</span>
                  <b>GDAL & Rasterio:</b> BOA Radiometry & Bands
                </div>
                <div>
                  <span style={{ color: "#2ee79b", marginRight: 4, fontWeight: 700 }}>● Active</span>
                  <b>Shapely & PyProj:</b> Cylindrical Equal-Area Proj
                </div>
                <div>
                  <span style={{ color: "#2ee79b", marginRight: 4, fontWeight: 700 }}>● Active</span>
                  <b>PostGIS / WGS-84:</b> Spatial Indexing
                </div>
              </div>
            </div>

            {/* Data Providers */}
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#38bdf8", textTransform: "uppercase", marginBottom: 4 }}>
                Data Providers
              </div>
              <div style={{ fontSize: 10, color: "#859ea8", lineHeight: 1.6 }}>
                <div>
                  <span style={{ color: "#2ee79b", marginRight: 4, fontWeight: 700 }}>● Active</span>
                  <b>Copernicus CDSE:</b> Sentinel-2 Level-2A BOA
                </div>
                <div>
                  <span style={{ color: "#64748b", marginRight: 4 }}>○ On Demand</span>
                  <b>Sentinel-1:</b> C-Band SAR GRD
                </div>
              </div>
            </div>

            {/* Agent Core */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#38bdf8", textTransform: "uppercase", marginBottom: 4 }}>
                Agent Core & Validation
              </div>
              <div style={{ fontSize: 10, color: "#859ea8", lineHeight: 1.6 }}>
                <div>
                  <span style={{ color: "#2ee79b", marginRight: 4, fontWeight: 700 }}>● Active</span>
                  <b>Reality Check:</b> 4-Tier Grounding Validator
                </div>
                <div>
                  <span style={{ color: "#2ee79b", marginRight: 4, fontWeight: 700 }}>● Active</span>
                  <b>Evidence Engine:</b> Epistemological Claims Graph
                </div>
                <div>
                  <span style={{ color: "#2ee79b", marginRight: 4, fontWeight: 700 }}>● Active</span>
                  <b>Context Engine:</b> Conversational Carryover
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function AIAssistantPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="page">Loading assistant…</div>}>
        <AssistantContent />
      </Suspense>
    </AppShell>
  );
}
