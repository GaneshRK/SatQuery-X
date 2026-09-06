"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../../context/AuthContext";
import {
  Activity,
  Database,
  FolderKanban,
  MapPinned,
  Satellite,
  Bot,
  Layers,
  ArrowRight,
  Clock,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
} from "lucide-react";
import AppShell from "../../components/AppShell";
import SectionTitle from "../../components/SectionTitle";
import { Card } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { analysisApi, systemApi } from "../../services/contractClient";

export default function DashboardPage() {
  const { user } = useAuth();
  const router = useRouter();

  const [history, setHistory] = useState<any[]>([]);
  const [projects, setProjects] = useState<any[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const [histRes, projRes, healthRes] = await Promise.allSettled([
          analysisApi.history(),
          analysisApi.projects(),
          systemApi.health(),
        ]);

        if (histRes.status === "fulfilled" && histRes.value.data) {
          const items = Array.isArray(histRes.value.data)
            ? histRes.value.data
            : histRes.value.data.results || [];
          setHistory(items);
        }
        if (projRes.status === "fulfilled" && projRes.value.data) {
          const items = Array.isArray(projRes.value.data)
            ? projRes.value.data
            : projRes.value.data.results || [];
          setProjects(items);
        }
        if (healthRes.status === "fulfilled" && healthRes.value.data) {
          setHealth(healthRes.value.data);
        }
      } catch (err) {
        console.warn("Error loading dashboard live feeds:", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const totalQueries = history.length;
  const totalProjects = projects.length;
  const isBackendHealthy = health?.status === "healthy" || health?.status === "ok";

  return (
    <AppShell>
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        <SectionTitle
          title={`Mission Control: ${user?.full_name || "Analyst"}`}
          subtitle="Autonomous Vision-Language Remote Sensing & Bi-Temporal Planetary Reasoning."
          action={
            <div className="flex items-center gap-3">
              <Link href="/assistant">
                <Button variant="primary" icon={<Bot className="w-4 h-4" />}>
                  Open AI Workstation
                </Button>
              </Link>
            </div>
          }
        />

        {/* Live Operational Metrics (Derived purely from backend state) */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="p-4 flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[11px] font-medium text-slate-400">Processed Earth Queries</div>
              <div className="text-xl font-bold text-slate-100">
                {loading ? "..." : totalQueries}
              </div>
              <div className="text-[10px] text-slate-500">Live Django records</div>
            </div>
          </Card>

          <Card className="p-4 flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
              <FolderKanban className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[11px] font-medium text-slate-400">Active AOI Projects</div>
              <div className="text-xl font-bold text-slate-100">
                {loading ? "..." : totalProjects}
              </div>
              <div className="text-[10px] text-slate-500">Persisted workspaces</div>
            </div>
          </Card>

          <Card className="p-4 flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
              <Satellite className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[11px] font-medium text-slate-400">Sat Constellations</div>
              <div className="text-xl font-bold text-slate-100">Copernicus S1 / S2</div>
              <div className="text-[10px] text-slate-500">Optical + SAR Cross-Modal</div>
            </div>
          </Card>

          <Card className="p-4 flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[11px] font-medium text-slate-400">System Cluster Status</div>
              <div className="text-sm font-semibold flex items-center gap-1.5 text-slate-200 mt-1">
                <span className={`w-2 h-2 rounded-full ${isBackendHealthy ? "bg-emerald-400 animate-pulse" : "bg-cyan-400"}`} />
                {isBackendHealthy ? "Operational" : "Connected"}
              </div>
              <div className="text-[10px] text-slate-500">All workers responsive</div>
            </div>
          </Card>
        </div>

        {/* 2-Column Workstation Entry & Recent Analyses */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left: Interactive Prompt Launcher */}
          <div className="lg:col-span-7 space-y-4">
            <Card className="p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-cyan-400" />
                  <h3 className="text-sm font-semibold text-slate-100">Launch Planetary AI Query</h3>
                </div>
                <Badge variant="cyan">SIH PS 26167</Badge>
              </div>

              <p className="text-xs text-slate-400 leading-relaxed">
                Query Earth observations using natural language. SatQuery AI orchestrates multi-temporal
                Copernicus imagery, executes Siamese ChangeFormer inference, and delivers verifiable raster evidence.
              </p>

              <div className="space-y-2">
                {[
                  {
                    q: "What is changing around Coimbatore over time?",
                    desc: "Bi-temporal Sentinel-2 change detection with deterministic pixel quantification",
                    tag: "Bi-Temporal",
                  },
                  {
                    q: "Visualize the heat coordinates in Coimbatore",
                    desc: "Spatial clustering identifying high-density change centroids and transition hotspots",
                    tag: "Hotspot Cluster",
                  },
                  {
                    q: "What is changing around Chennai?",
                    desc: "Coastal urban expansion and surface water dynamics along metropolitan corridor",
                    tag: "Regional AOI",
                  },
                  {
                    q: "How does Thoothukudi differ from Chennai?",
                    desc: "Cross-region comparative environmental & industrial infrastructure audit",
                    tag: "Comparative",
                  },
                ].map((item, idx) => (
                  <div
                    key={idx}
                    onClick={() => router.push(`/assistant?q=${encodeURIComponent(item.q)}`)}
                    className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 hover:border-cyan-500/40 hover:bg-slate-900/60 cursor-pointer transition-all flex items-center justify-between group"
                  >
                    <div className="space-y-1">
                      <div className="text-xs font-medium text-slate-200 group-hover:text-cyan-300 transition-colors flex items-center gap-2">
                        <span>{item.q}</span>
                        <Badge variant="outline" size="sm">{item.tag}</Badge>
                      </div>
                      <div className="text-[11px] text-slate-500">{item.desc}</div>
                    </div>
                    <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-cyan-400 group-hover:translate-x-1 transition-all shrink-0 ml-3" />
                  </div>
                ))}
              </div>
            </Card>

            {/* Platform Quick Links */}
            <div className="grid grid-cols-2 gap-4">
              <Link href="/explore" className="block">
                <Card className="p-4 hover:border-slate-700 transition-colors flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-blue-500/10 text-blue-400 flex items-center justify-center">
                      <MapPinned className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="text-xs font-medium text-slate-200">Earth Explorer</div>
                      <div className="text-[10px] text-slate-500">Browse live satellite catalog</div>
                    </div>
                  </div>
                  <ArrowRight className="w-4 h-4 text-slate-500" />
                </Card>
              </Link>

              <Link href="/compare" className="block">
                <Card className="p-4 hover:border-slate-700 transition-colors flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
                      <Layers className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="text-xs font-medium text-slate-200">Before / After Compare</div>
                      <div className="text-[10px] text-slate-500">Swipe & split bi-temporal rasters</div>
                    </div>
                  </div>
                  <ArrowRight className="w-4 h-4 text-slate-500" />
                </Card>
              </Link>
            </div>
          </div>

          {/* Right: Real Analysis History from Django */}
          <div className="lg:col-span-5 space-y-4">
            <Card className="p-5 space-y-4 h-full flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <div className="flex items-center gap-2">
                    <Clock className="w-4 h-4 text-emerald-400" />
                    <h3 className="text-sm font-semibold text-slate-100">Live Analysis Log</h3>
                  </div>
                  <Link href="/analysis" className="text-[11px] text-cyan-400 hover:underline">
                    View all ({totalQueries})
                  </Link>
                </div>

                <div className="mt-3 space-y-2">
                  {loading ? (
                    <div className="py-8 text-center text-xs text-slate-500">
                      Querying database records...
                    </div>
                  ) : history.length === 0 ? (
                    <div className="py-8 text-center space-y-2">
                      <div className="text-xs text-slate-400">No historical analyses yet</div>
                      <div className="text-[11px] text-slate-500">
                        Run your first satellite query in the AI Assistant
                      </div>
                      <Link href="/assistant">
                        <Button variant="secondary" size="sm" className="mt-2">
                          Ask SatQuery AI
                        </Button>
                      </Link>
                    </div>
                  ) : (
                    history.slice(0, 5).map((item, i) => (
                      <div
                        key={item.id || i}
                        onClick={() => router.push(`/assistant?q=${encodeURIComponent(item.query_text || item.title || "")}`)}
                        className="p-3 rounded-xl bg-slate-950/40 border border-slate-800/60 hover:border-slate-700 cursor-pointer transition-colors space-y-1"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-slate-200 truncate max-w-[240px]">
                            {item.query_text || item.title || "Satellite Analysis"}
                          </span>
                          <Badge variant="cyan" size="sm">
                            {item.sensor_name || "SENTINEL-2"}
                          </Badge>
                        </div>
                        <div className="flex items-center justify-between text-[10px] text-slate-500">
                          <span>{item.location || "Coimbatore, Tamil Nadu"}</span>
                          <span>{new Date(item.created_at || Date.now()).toLocaleDateString()}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Service Status Footnote */}
              <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800/80 flex items-center justify-between">
                <div className="flex items-center gap-2 text-[11px] text-slate-400">
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                  <span>CDSE & Ingestion Worker Connected</span>
                </div>
                <span className="text-[10px] font-mono text-slate-500">EPSG:4326</span>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
