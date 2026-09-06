"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../../context/AuthContext";
import {
  Activity,
  Database,
  FolderKanban,
  MapPinned,
  Sprout,
  Droplets,
  Building2,
  Trees,
} from "lucide-react";
import AppShell from "../../components/AppShell";
import SectionTitle from "../../components/SectionTitle";
import StatCard from "../../components/StatCard";
import MapPanel from "../../components/MapPanel";

export default function DashboardPage() {
  const { user } = useAuth();
  const router = useRouter();

  return (
    <AppShell>
      <div className="page">
        <SectionTitle
          title={`Good day, ${(user?.full_name || "Analyst").split(" ")[0]} 👋`}
          subtitle="Autonomous Vision-Language Remote Sensing & Bi-Temporal Planetary Reasoning."
          action={
            <Link href="/assistant" className="btn primary">
              Ask SatQuery AI
            </Link>
          }
        />

        <div className="stats-grid">
          <StatCard
            icon={<Activity />}
            label="Total Analyses"
            value="1,248"
            meta="+18% this month"
          />
          <StatCard
            icon={<Database />}
            label="Areas Explored"
            value="532"
            meta="Across 24 regions"
          />
          <StatCard
            icon={<FolderKanban />}
            label="Saved Projects"
            value="24"
            meta="6 updated recently"
          />
          <StatCard
            icon={<MapPinned />}
            label="Sensor Constellations"
            value="4"
            meta="Sentinel-1/2 • Landsat"
          />
        </div>

        <div className="dashboard-grid">
          <div className="panel map-panel">
            <div className="panel-head">
              <div>
                <h3>Explore your Earth</h3>
                <span>Coimbatore, Tamil Nadu (Sentinel-2 AOI)</span>
              </div>
              <Link href="/explore">Open interactive map →</Link>
            </div>
            <MapPanel height={420} />
          </div>

          <div className="panel">
            <div className="panel-head">
              <div>
                <h3>Ask anything about this region</h3>
                <span>Natural-language multi-agent reasoning</span>
              </div>
            </div>
            <div className="ask-box">
              How has vegetation and water changed around Coimbatore in the last 6 months?
              <button onClick={() => router.push("/assistant")}>→</button>
            </div>
            {[
              "Show areas where vegetation has decreased around Coimbatore",
              "Which locations show signs of water stress?",
              "Compare urban expansion between 2024 and 2026",
              "Detect industrial storage tanks in this region",
            ].map((query) => (
              <Link
                className="suggestion"
                href={`/assistant?q=${encodeURIComponent(query)}`}
                key={query}
              >
                <span>◈ {query}</span>
                <span>›</span>
              </Link>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <div>
              <h3>Quick Biophysical Insights</h3>
              <span>Latest verified radiometric indices</span>
            </div>
            <Link href="/analysis">View all insights →</Link>
          </div>
          <div className="insight-grid">
            {[
              [Sprout, "Vegetation", "NDVI 0.42", "-12.4% vs baseline"],
              [Droplets, "Water Bodies", "24.8 km²", "+3.1% reservoir fill"],
              [Building2, "Urban Built-up", "186.3 km²", "+8.7% expansion"],
              [Trees, "Agricultural Land", "542.1 km²", "-5.2% harvest cycle"],
            ].map(([Icon, label, value, meta]: any) => (
              <div className="insight" key={label}>
                <Icon size={22} />
                <span>{label}</span>
                <strong>{value}</strong>
                <small>{meta}</small>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
