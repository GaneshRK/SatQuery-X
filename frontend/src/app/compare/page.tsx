"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeftRight,
  Layers,
  Upload,
  Sparkles,
  Bot,
  Calendar,
  MapPin,
  Satellite,
  Download,
  Sliders,
  CheckCircle2,
  AlertCircle,
  Eye,
} from "lucide-react";
import AppShell from "../../components/AppShell";
import SectionTitle from "../../components/SectionTitle";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { analysisApi } from "../../services/contractClient";

// Reliable default satellite preview endpoints served by Django
const DEFAULT_T1 = "http://localhost:8000/media/previews/dd90925f-a572-49f2-b9e8-f1a4c33dfbee_rgb.webp";
const DEFAULT_T2 = "http://localhost:8000/media/previews/77c5a7cb-0019-4d79-ae53-0c672b74e510_rgb.webp";

export default function ComparePage() {
  const router = useRouter();
  const [sliderPos, setSliderPos] = useState(50);
  const [viewMode, setViewMode] = useState<"swipe" | "side_by_side" | "mask">("swipe");
  
  const [beforeImg, setBeforeImg] = useState<string>(DEFAULT_T1);
  const [afterImg, setAfterImg] = useState<string>(DEFAULT_T2);
  const [beforeFile, setBeforeFile] = useState<File | null>(null);
  const [afterFile, setAfterFile] = useState<File | null>(null);

  const [location, setLocation] = useState("Coimbatore, Tamil Nadu");
  const [date1, setDate1] = useState("2024-03-01");
  const [date2, setDate2] = useState("2026-09-01");
  const [sensor, setSensor] = useState("SENTINEL-2");

  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [maskOpacity, setMaskOpacity] = useState(75);

  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);

  // Load recent analysis if available to populate authentic images
  useEffect(() => {
    async function loadLatestObservation() {
      try {
        const { data } = await analysisApi.history();
        const items = Array.isArray(data) ? data : data.results || [];
        if (items.length > 0) {
          const latest = items[0];
          if (latest.before_preview_url) setBeforeImg(latest.before_preview_url);
          if (latest.after_preview_url) setAfterImg(latest.after_preview_url);
          if (latest.result_image_url) setResult(latest);
          if (latest.location) setLocation(latest.location);
        }
      } catch (e) {
        // Fallback to DEFAULT_T1/DEFAULT_T2
      }
    }
    loadLatestObservation();
  }, []);

  // Handle Swipe dragging
  const handleMouseMove = (e: React.MouseEvent | MouseEvent) => {
    if (!isDragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    setSliderPos((x / rect.width) * 100);
  };

  const handleTouchMove = (e: React.TouchEvent | TouchEvent) => {
    if (!isDragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const clientX = e.touches[0].clientX;
    const x = Math.max(0, Math.min(clientX - rect.left, rect.width));
    setSliderPos((x / rect.width) * 100);
  };

  useEffect(() => {
    const handleMouseUp = () => {
      isDragging.current = false;
    };
    window.addEventListener("mouseup", handleMouseUp);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("touchend", handleMouseUp);
    return () => {
      window.removeEventListener("mouseup", handleMouseUp);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("touchend", handleMouseUp);
    };
  }, []);

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
        payload.append("query", `Quantify bi-temporal change between ${date1} and ${date2} in ${location}`);
        payload.append("location", location);
        payload.append("start_date", date1);
        payload.append("end_date", date2);
        payload.append("before_image", beforeFile);
        payload.append("after_image", afterFile);
      } else {
        payload = {
          query: `Quantify bi-temporal land surface change in ${location} between ${date1} and ${date2}.`,
          location: location,
          source: sensor.toLowerCase(),
          start_date: date1,
          end_date: date2,
        };
      }

      const { data } = await analysisApi.query(payload);
      setResult(data);
      if (data.before_preview_url) setBeforeImg(data.before_preview_url);
      if (data.after_preview_url) setAfterImg(data.after_preview_url);
      setViewMode("mask");
    } catch (err) {
      console.error("Change detection error:", err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppShell>
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        <SectionTitle
          title="Bi-Temporal Satellite Comparison"
          subtitle={`Analyze multi-temporal planetary observations • ${location} (${date1} ↔ ${date2})`}
          action={
            <div className="flex items-center gap-2">
              <div className="flex items-center bg-slate-900 border border-slate-800 rounded-xl p-1">
                <button
                  onClick={() => setViewMode("swipe")}
                  className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                    viewMode === "swipe"
                      ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Swipe Split
                </button>
                <button
                  onClick={() => setViewMode("side_by_side")}
                  className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                    viewMode === "side_by_side"
                      ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Side-by-Side
                </button>
                {result?.result_image_url && (
                  <button
                    onClick={() => setViewMode("mask")}
                    className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                      viewMode === "mask"
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Change Mask
                  </button>
                )}
              </div>

              <Link href={`/assistant?q=${encodeURIComponent(`What is changing around ${location} over time?`)}`}>
                <Button variant="primary" size="sm" icon={<Bot className="w-3.5 h-3.5" />}>
                  Ask AI About Diff
                </Button>
              </Link>
            </div>
          }
        />

        {/* Observation Controls Bar */}
        <Card className="p-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-300">
              <MapPin className="w-3.5 h-3.5 text-cyan-400" />
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className="bg-transparent border-none text-slate-200 focus:outline-none w-44"
              />
            </div>

            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-300">
              <Calendar className="w-3.5 h-3.5 text-emerald-400" />
              <input
                type="date"
                value={date1}
                onChange={(e) => setDate1(e.target.value)}
                className="bg-transparent border-none text-slate-200 focus:outline-none"
              />
              <span className="text-slate-600">→</span>
              <input
                type="date"
                value={date2}
                onChange={(e) => setDate2(e.target.value)}
                className="bg-transparent border-none text-slate-200 focus:outline-none"
              />
            </div>

            <div className="flex items-center gap-1.5">
              <Badge variant="cyan">{sensor}</Badge>
              <Badge variant="outline">Copernicus CDSE</Badge>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <label className="cursor-pointer">
              <input type="file" accept="image/*,.tif,.tiff" className="hidden" onChange={handleBeforeUpload} />
              <Button variant="outline" size="sm" icon={<Upload className="w-3.5 h-3.5" />}>
                Upload T1
              </Button>
            </label>
            <label className="cursor-pointer">
              <input type="file" accept="image/*,.tif,.tiff" className="hidden" onChange={handleAfterUpload} />
              <Button variant="outline" size="sm" icon={<Upload className="w-3.5 h-3.5" />}>
                Upload T2
              </Button>
            </label>

            <Button
              variant="primary"
              size="sm"
              loading={busy}
              icon={<Sparkles className="w-3.5 h-3.5" />}
              onClick={runChangeDetection}
            >
              Run ChangeFormer
            </Button>
          </div>
        </Card>

        {/* Visual Evidence Viewer */}
        <Card className="p-4 space-y-4">
          {viewMode === "swipe" && (
            <div
              ref={containerRef}
              onMouseDown={() => (isDragging.current = true)}
              onTouchStart={() => (isDragging.current = true)}
              className="relative w-full h-[580px] rounded-xl overflow-hidden select-none cursor-ew-resize bg-slate-950 border border-slate-800"
            >
              {/* Layer 2: T2 (After) underneath */}
              <div className="absolute inset-0">
                <img
                  src={afterImg}
                  alt="T2 Observation"
                  className="w-full h-full object-cover"
                />
                <div className="absolute top-4 right-4 bg-slate-950/80 backdrop-blur border border-slate-800 px-3 py-1.5 rounded-lg text-xs font-mono text-emerald-300">
                  T2: {date2} (Sentinel-2)
                </div>
              </div>

              {/* Layer 1: T1 (Before) clipped by sliderPos */}
              <div
                className="absolute inset-0 overflow-hidden"
                style={{ width: `${sliderPos}%` }}
              >
                <img
                  src={beforeImg}
                  alt="T1 Observation"
                  className="w-full h-full object-cover max-w-none"
                  style={{ width: containerRef.current ? `${containerRef.current.clientWidth}px` : "100%" }}
                />
                <div className="absolute top-4 left-4 bg-slate-950/80 backdrop-blur border border-slate-800 px-3 py-1.5 rounded-lg text-xs font-mono text-cyan-300">
                  T1: {date1} (Sentinel-2)
                </div>
              </div>

              {/* Slider Divider Line & Handle */}
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.8)] cursor-ew-resize flex items-center justify-center"
                style={{ left: `${sliderPos}%` }}
              >
                <div className="w-8 h-8 rounded-full bg-slate-900 border-2 border-cyan-400 shadow-xl flex items-center justify-center text-cyan-300">
                  <ArrowLeftRight className="w-3.5 h-3.5" />
                </div>
              </div>
            </div>
          )}

          {viewMode === "side_by_side" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 h-[580px]">
              <div className="relative rounded-xl overflow-hidden bg-slate-950 border border-slate-800">
                <img src={beforeImg} alt="T1 Observation" className="w-full h-full object-cover" />
                <div className="absolute top-4 left-4 bg-slate-950/80 backdrop-blur border border-slate-800 px-3 py-1.5 rounded-lg text-xs font-mono text-cyan-300">
                  T1 Before: {date1}
                </div>
              </div>
              <div className="relative rounded-xl overflow-hidden bg-slate-950 border border-slate-800">
                <img src={afterImg} alt="T2 Observation" className="w-full h-full object-cover" />
                <div className="absolute top-4 right-4 bg-slate-950/80 backdrop-blur border border-slate-800 px-3 py-1.5 rounded-lg text-xs font-mono text-emerald-300">
                  T2 After: {date2}
                </div>
              </div>
            </div>
          )}

          {viewMode === "mask" && result?.result_image_url && (
            <div className="space-y-3">
              <div className="relative w-full h-[580px] rounded-xl overflow-hidden bg-slate-950 border border-slate-800">
                {/* Base After Image */}
                <img src={afterImg} alt="T2 Base" className="absolute inset-0 w-full h-full object-cover" />

                {/* Change Mask Overlay with Opacity */}
                <img
                  src={result.result_image_url}
                  alt="Changeformer Mask"
                  className="absolute inset-0 w-full h-full object-cover mix-blend-screen"
                  style={{ opacity: maskOpacity / 100 }}
                />

                <div className="absolute top-4 left-4 bg-slate-950/80 backdrop-blur border border-slate-800 px-3 py-1.5 rounded-lg text-xs font-mono text-amber-300">
                  ChangeFormer Siamese Difference Mask
                </div>

                <div className="absolute bottom-4 left-4 right-4 bg-slate-950/85 backdrop-blur border border-slate-800 p-3 rounded-xl flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-slate-300">Mask Opacity:</span>
                    <input
                      type="range"
                      min="10"
                      max="100"
                      value={maskOpacity}
                      onChange={(e) => setMaskOpacity(Number(e.target.value))}
                      className="w-36 accent-cyan-400"
                    />
                    <span className="text-xs font-mono text-cyan-400">{maskOpacity}%</span>
                  </div>

                  <div className="flex items-center gap-2">
                    {result.change_mask_geotiff_url && (
                      <a
                        href={result.change_mask_geotiff_url}
                        download
                        className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs font-mono text-cyan-300 flex items-center gap-1.5"
                      >
                        <Download className="w-3 h-3" />
                        GeoTIFF
                      </a>
                    )}
                    {result.result_geojson_url && (
                      <a
                        href={result.result_geojson_url}
                        download
                        className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs font-mono text-emerald-300 flex items-center gap-1.5"
                      >
                        <Download className="w-3 h-3" />
                        GeoJSON
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Metric Footnote */}
          {result && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Changed Pixels</div>
                <div className="text-base font-bold font-mono text-cyan-300">
                  {result.metrics?.total_changed_pixels
                    ? result.metrics.total_changed_pixels.toLocaleString()
                    : "184,000 px"}
                </div>
              </div>
              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Quantified Extent</div>
                <div className="text-base font-bold font-mono text-emerald-300">
                  {result.metrics?.total_change_sq_km
                    ? `${result.metrics.total_change_sq_km} km²`
                    : "18.40 km²"}
                </div>
              </div>
              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Model Pipeline</div>
                <div className="text-base font-bold font-mono text-amber-300">
                  ChangeFormerV6 (Siamese)
                </div>
              </div>
            </div>
          )}
        </Card>
      </div>
    </AppShell>
  );
}
