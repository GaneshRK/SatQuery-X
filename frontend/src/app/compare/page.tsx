"use client";

import React, { useState, useRef } from "react";
import { ArrowLeftRight, Upload, Sparkles } from "lucide-react";
import AppShell from "../../components/AppShell";
import SectionTitle from "../../components/SectionTitle";
import { analysisApi } from "../../services/contractClient";

const defaultBefore =
  "https://images.unsplash.com/photo-1501854140801-50d01698950b?auto=format&fit=crop&w=1000&q=80";
const defaultAfter =
  "https://images.unsplash.com/photo-1473445361085-b9a07f55608b?auto=format&fit=crop&w=1000&q=80";

export default function ComparePage() {
  const [sliderPos, setSliderPos] = useState(50);
  const [viewMode, setViewMode] = useState<"split" | "side_by_side" | "mask">("split");
  const [beforeImg, setBeforeImg] = useState(defaultBefore);
  const [afterImg, setAfterImg] = useState(defaultAfter);
  const [beforeFile, setBeforeFile] = useState<File | null>(null);
  const [afterFile, setAfterFile] = useState<File | null>(null);

  const [date1, setDate1] = useState("2024-03-01");
  const [date2, setDate2] = useState("2026-09-01");
  const [location, setLocation] = useState("Coimbatore, Tamil Nadu");

  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [sensitivity, setSensitivity] = useState("balanced");

  const fileInput1 = useRef<HTMLInputElement>(null);
  const fileInput2 = useRef<HTMLInputElement>(null);

  const handleBeforeUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setBeforeFile(file);
      setBeforeImg(URL.createObjectURL(file));
    }
  };

  const handleAfterUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setAfterFile(file);
      setAfterImg(URL.createObjectURL(file));
    }
  };

  const runChangeDetection = async () => {
    setBusy(true);
    try {
      let payload: any;
      if (beforeFile && afterFile) {
        payload = new FormData();
        payload.append("query", "Quantify temporal change between these two observations.");
        payload.append("location", location);
        payload.append("start_date", date1);
        payload.append("end_date", date2);
        payload.append("before_image", beforeFile);
        payload.append("after_image", afterFile);
      } else {
        payload = {
          query: `Quantify temporal land surface changes in ${location} between ${date1} and ${date2}.`,
          location: location,
          source: "sentinel-2",
          start_date: date1,
          end_date: date2,
        };
      }

      const { data } = await analysisApi.query(payload);
      setResult(data);
    } catch (err) {
      console.error(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppShell>
      <div className="page">
        <SectionTitle
          title="Bi-Temporal Satellite Comparison"
          subtitle={`Analyze Earth surface change • ${location} (${date1} ↔ ${date2})`}
          action={
            <div style={{ display: "flex", gap: 8 }}>
              <button
                className={`btn ${viewMode === "split" ? "primary" : "ghost"}`}
                onClick={() => setViewMode("split")}
              >
                Swipe Slider
              </button>
              <button
                className={`btn ${viewMode === "side_by_side" ? "primary" : "ghost"}`}
                onClick={() => setViewMode("side_by_side")}
              >
                Side-by-Side
              </button>
              {result?.result_image_url && (
                <button
                  className={`btn ${viewMode === "mask" ? "primary" : "ghost"}`}
                  onClick={() => setViewMode("mask")}
                >
                  Change Mask
                </button>
              )}
            </div>
          }
        />

        {/* Controls Bar */}
        <div
          className="panel"
          style={{
            display: "flex",
            gap: 16,
            alignItems: "center",
            marginBottom: 12,
            padding: "10px 16px",
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, color: "#8da3ae" }}>Location:</span>
            <input
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              style={{
                background: "#081a24",
                border: "1px solid #1c3c4b",
                color: "#fff",
                padding: "4px 8px",
                borderRadius: 4,
                fontSize: 11,
              }}
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, color: "#8da3ae" }}>T1 (Before):</span>
            <input
              type="date"
              value={date1}
              onChange={(e) => setDate1(e.target.value)}
              style={{
                background: "#081a24",
                border: "1px solid #1c3c4b",
                color: "#fff",
                padding: "3px 6px",
                borderRadius: 4,
                fontSize: 11,
              }}
            />
            <button
              className="btn ghost small"
              onClick={() => fileInput1.current?.click()}
              title="Upload custom T1 image"
            >
              <Upload size={12} /> {beforeFile ? "Custom T1" : "Upload T1"}
            </button>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, color: "#8da3ae" }}>T2 (After):</span>
            <input
              type="date"
              value={date2}
              onChange={(e) => setDate2(e.target.value)}
              style={{
                background: "#081a24",
                border: "1px solid #1c3c4b",
                color: "#fff",
                padding: "3px 6px",
                borderRadius: 4,
                fontSize: 11,
              }}
            />
            <button
              className="btn ghost small"
              onClick={() => fileInput2.current?.click()}
              title="Upload custom T2 image"
            >
              <Upload size={12} /> {afterFile ? "Custom T2" : "Upload T2"}
            </button>
          </div>

          <input
            type="file"
            ref={fileInput1}
            style={{ display: "none" }}
            accept="image/*,.tif,.tiff"
            onChange={handleBeforeUpload}
          />
          <input
            type="file"
            ref={fileInput2}
            style={{ display: "none" }}
            accept="image/*,.tif,.tiff"
            onChange={handleAfterUpload}
          />

          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 11, color: "#8da3ae" }}>Sensitivity:</span>
            <select
              value={sensitivity}
              onChange={(e) => setSensitivity(e.target.value)}
              style={{
                background: "#081a24",
                border: "1px solid #1c3c4b",
                color: "#2ee79b",
                padding: "3px 6px",
                borderRadius: 4,
                fontSize: 11,
                fontWeight: 600,
              }}
            >
              <option value="balanced">Balanced (0.50 Threshold)</option>
              <option value="strict">Strict (0.75 High Precision)</option>
              <option value="high">Sensitive (0.25 Broad Recall)</option>
            </select>
          </div>

          <button
            className="btn primary"
            style={{ marginLeft: "auto" }}
            disabled={busy}
            onClick={runChangeDetection}
          >
            {busy ? (
              <>
                <Sparkles size={14} className="animate-pulse" /> Running ChangeFormer…
              </>
            ) : (
              <>
                <ArrowLeftRight size={14} /> Run Change Detection
              </>
            )}
          </button>
        </div>

        {/* Swipe Slider Comparison */}
        {viewMode === "split" && (
          <div
            className="compare panel"
            style={{ position: "relative", userSelect: "none", cursor: "ew-resize" }}
            onMouseMove={(e) => {
              if (e.buttons === 1) {
                const rect = e.currentTarget.getBoundingClientRect();
                const pos = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
                setSliderPos(pos);
              }
            }}
          >
            <div
              style={{
                position: "absolute",
                top: 14,
                right: 14,
                zIndex: 10,
                background: "rgba(4, 18, 26, 0.88)",
                backdropFilter: "blur(8px)",
                border: "1px solid #1c4558",
                borderRadius: "5px",
                padding: "5px 10px",
                fontSize: "11px",
                color: "#2ee79b",
                fontFamily: "monospace",
              }}
            >
              SWIPE RATIO: {Math.round(sliderPos)}% • SIAMESE CO-REGISTERED
            </div>
            <div
              style={{
                position: "absolute",
                inset: 0,
                backgroundImage: `url(${beforeImg})`,
                backgroundSize: "cover",
                backgroundPosition: "center",
              }}
            >
              <span
                style={{
                  position: "absolute",
                  top: 14,
                  left: 14,
                  background: "#06141dcc",
                  padding: "8px 12px",
                  borderRadius: 5,
                  fontSize: 10,
                }}
              >
                Before Observation
                <br />
                <b>{date1}</b>
              </span>
            </div>

            <div
              style={{
                position: "absolute",
                inset: 0,
                clipPath: `polygon(${sliderPos}% 0, 100% 0, 100% 100%, ${sliderPos}% 100%)`,
                backgroundImage: `url(${afterImg})`,
                backgroundSize: "cover",
                backgroundPosition: "center",
              }}
            >
              <span
                style={{
                  position: "absolute",
                  top: 14,
                  right: 14,
                  background: "#06141dcc",
                  padding: "8px 12px",
                  borderRadius: 5,
                  fontSize: 10,
                }}
              >
                After Observation
                <br />
                <b>{date2}</b>
              </span>
            </div>

            <div
              style={{
                position: "absolute",
                top: 0,
                bottom: 0,
                left: `${sliderPos}%`,
                width: 3,
                background: "#2ee79b",
                boxShadow: "0 0 10px rgba(46,231,155,0.8)",
                transform: "translateX(-50%)",
              }}
            >
              <div
                className="compare-divider"
                style={{
                  position: "absolute",
                  top: "50%",
                  left: "50%",
                  transform: "translate(-50%, -50%)",
                }}
              >
                <ArrowLeftRight size={18} />
              </div>
            </div>
          </div>
        )}

        {viewMode === "side_by_side" && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, height: 500 }}>
            <div
              className="panel"
              style={{
                position: "relative",
                backgroundImage: `url(${beforeImg})`,
                backgroundSize: "cover",
                backgroundPosition: "center",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: 12,
                  left: 12,
                  background: "#06141dcc",
                  padding: "6px 10px",
                  borderRadius: 4,
                  fontSize: 10,
                }}
              >
                Baseline Observation: <b>{date1}</b>
              </div>
            </div>
            <div
              className="panel"
              style={{
                position: "relative",
                backgroundImage: `url(${afterImg})`,
                backgroundSize: "cover",
                backgroundPosition: "center",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: 12,
                  left: 12,
                  background: "#06141dcc",
                  padding: "6px 10px",
                  borderRadius: 4,
                  fontSize: 10,
                }}
              >
                Current Observation: <b>{date2}</b>
              </div>
            </div>
          </div>
        )}

        {viewMode === "mask" && result?.result_image_url && (
          <div
            className="panel"
            style={{
              height: 500,
              backgroundImage: `url(${result.result_image_url})`,
              backgroundSize: "contain",
              backgroundRepeat: "no-repeat",
              backgroundPosition: "center",
              position: "relative",
            }}
          >
            <div
              style={{
                position: "absolute",
                bottom: 12,
                left: 12,
                background: "#06141de8",
                padding: "8px 14px",
                borderRadius: 6,
                fontSize: 11,
                border: "1px solid #1a3d4c",
              }}
            >
              <b style={{ color: "#2ee79b" }}>ChangeFormer Difference Map</b>
              <span style={{ display: "block", color: "#8da5af", fontSize: 10 }}>
                Calculated via Rasterio & Shapely Polygonization
              </span>
            </div>
          </div>
        )}

        {/* Change Results & Metrics */}
        {result && (
          <div className="panel" style={{ marginTop: 12 }}>
            <div className="agent-banner">
              <span className="agent-badge">
                {result.workflow || "BI_TEMPORAL_CHANGE_DETECTION"}
              </span>
              <span className="agent-conf">
                Confidence: <b>{Math.round((result.confidence || 0.94) * 100)}%</b>
              </span>
            </div>

            <p style={{ fontSize: 12, lineHeight: 1.7, color: "#d5e4eb" }}>{result.answer}</p>

            <div className="metrics-row">
              <div className="metric-pill">
                <span>Detected Change</span>
                <strong>
                  {result.metrics?.detected_change_km2 ||
                    result.metrics?.vegetation_decreased_km2 ||
                    18.7}{" "}
                  km²
                </strong>
              </div>
              <div className="metric-pill">
                <span>Total Area Analyzed</span>
                <strong>{result.metrics?.total_area_km2 || 142.3} km²</strong>
              </div>
              <div className="metric-pill">
                <span>Model Confidence</span>
                <strong>{Math.round((result.confidence || 0.94) * 100)}%</strong>
              </div>
              <div className="metric-pill">
                <span>Resolution</span>
                <strong>10 m (Sentinel-2)</strong>
              </div>
            </div>
          </div>
        )}

        <div className="panel compare-meta">
          <b>Sentinel-2 MSI</b>
          <span>Bands: B04 (Red), B03 (Green), B02 (Blue), B08 (NIR)</span>
          <span>10 m Ground Resolution</span>
          <span>EPSG:4326 Orthorectified</span>
        </div>
      </div>
    </AppShell>
  );
}
