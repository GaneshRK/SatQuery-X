"use client";

import { useState, useEffect } from "react";
import { Download, Save, Sprout, Droplets, Building2, Trees, History } from "lucide-react";
import AppShell from "../../components/AppShell";
import SectionTitle from "../../components/SectionTitle";
import { analysisApi } from "../../services/contractClient";

const defaultResultImg =
  "https://images.unsplash.com/photo-1531058020387-3be344556be6?auto=format&fit=crop&w=1100&q=80";

export default function AnalysisPage() {
  const [history, setHistory] = useState<any[]>([]);
  const [selectedAnalysis, setSelectedAnalysis] = useState<any>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    analysisApi
      .history()
      .then(({ data }) => {
        if (data && data.length > 0) {
          setHistory(data);
          setSelectedAnalysis(data[0]);
        }
      })
      .catch((err) => {
        console.warn("Unable to fetch history:", err);
      });
  }, []);

  const handleSaveToProject = async () => {
    try {
      await analysisApi.createProject({
        name: selectedAnalysis?.query
          ? `Analysis: ${selectedAnalysis.query.slice(0, 30)}...`
          : "Coimbatore Vegetation Assessment",
        description: selectedAnalysis?.answer || "Remote Sensing Observation",
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      console.error(err);
    }
  };

  const handleDownloadReport = () => {
    const content = `SATQUERY-X GEOSPATIAL INTELLIGENCE REPORT
-----------------------------------------
Query: ${selectedAnalysis?.query || "Vegetation Change Analysis"}
Date: ${selectedAnalysis?.created_at || new Date().toISOString()}
Confidence: ${Math.round((selectedAnalysis?.confidence || 0.94) * 100)}%

FINDINGS & REASONING:
${selectedAnalysis?.answer || "Vegetation decreased across selected sub-regions."}

METRICS:
- Vegetation Decreased: 18.7 km²
- Total Area Analyzed: 142.3 km²
- Geometric Projection: EPSG:4326
- Sensor: Sentinel-2 L2A (10m ground sample distance)
`;
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `SatQuery_Report_${selectedAnalysis?.analysis_id || "export"}.txt`;
    a.click();
  };

  return (
    <AppShell>
      <div className="page">
        <SectionTitle
          title="Vegetation & Surface Change Analysis"
          subtitle={
            selectedAnalysis?.query
              ? `Query: "${selectedAnalysis.query}"`
              : "Coimbatore, Tamil Nadu • Mar 2024 → Sep 2026"
          }
          action={
            <button className="btn ghost" onClick={handleDownloadReport}>
              <Download size={16} /> Download Report
            </button>
          }
        />

        {history.length > 0 && (
          <div
            className="panel"
            style={{
              display: "flex",
              gap: 8,
              alignItems: "center",
              marginBottom: 12,
              overflowX: "auto",
              padding: "8px 14px",
            }}
          >
            <History size={14} color="#2ee79b" />
            <span style={{ fontSize: 10, color: "#8da5af", whiteSpace: "nowrap" }}>
              Recent Analyses:
            </span>
            {history.map((h) => (
              <button
                key={h.analysis_id}
                onClick={() => setSelectedAnalysis(h)}
                className="mode-tab"
                style={{
                  borderColor:
                    selectedAnalysis?.analysis_id === h.analysis_id ? "#2ee79b" : "#173644",
                  color: selectedAnalysis?.analysis_id === h.analysis_id ? "#2ee79b" : "#91a8b1",
                  whiteSpace: "nowrap",
                  fontSize: 10,
                }}
              >
                {h.query.length > 25 ? h.query.slice(0, 25) + "…" : h.query}
              </button>
            ))}
          </div>
        )}

        <div className="analysis-grid">
          <div className="panel result-image">
            <img src={defaultResultImg} alt="analysis visualization" />
            <div className="legend">
              <span>■ Vegetation Decrease (18.7 km²)</span>
              <span>■ Stable Canopy / Urban Cover</span>
              <span>■ Water Reservoirs</span>
            </div>
          </div>

          <div className="panel summary">
            <div className="agent-banner">
              <span className="agent-badge">
                {selectedAnalysis?.analysis_id ? "LIVE ANALYSIS RECORD" : "BASE OBSERVATION"}
              </span>
              <span className="agent-conf">
                Confidence: <b>{Math.round((selectedAnalysis?.confidence || 0.94) * 100)}%</b>
              </span>
            </div>

            <h3>Analysis Summary</h3>
            <p style={{ fontSize: 11, color: "#9db4be", lineHeight: 1.6 }}>
              {selectedAnalysis?.answer ||
                "Vegetation decreased in several northern and eastern parts of the selected AOI over the monitored temporal window."}
            </p>

            <div className="big-number">
              18.7 km²<small>Vegetation Decreased</small>
            </div>
            <div className="big-number">
              142.3 km²<small>Total Area Analyzed</small>
            </div>
            <div className="big-number">
              {Math.round((selectedAnalysis?.confidence || 0.94) * 100)}%
              <small>Model Confidence</small>
            </div>

            <div className="summary-actions">
              <button
                className="btn primary full"
                onClick={handleSaveToProject}
                disabled={saved}
              >
                <Save size={16} /> {saved ? "Saved to Projects ✓" : "Save to Project"}
              </button>
            </div>
          </div>
        </div>

        <div className="panel" style={{ marginTop: 12 }}>
          <h3>Geospatial Indicators & Biophysical Indices</h3>
          <div className="insight-grid">
            {[
              [Sprout, "NDVI (Mean)", "0.42", "↓ 12.4% vs baseline"],
              [Droplets, "Water Bodies", "24.8 km²", "↑ 3.1% reservoir fill"],
              [Building2, "Built-up Surface", "186.3 km²", "↑ 8.7% expansion"],
              [Trees, "Agricultural Cover", "542.1 km²", "↓ 5.2% harvest cycle"],
            ].map(([Icon, label, val, diff]: any) => (
              <div className="insight" key={label}>
                <Icon size={20} />
                <span>{label}</span>
                <strong>{val}</strong>
                <small>{diff}</small>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
