"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Satellite,
  Compass,
  Radio,
  Layers,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  Cpu,
  Activity,
  CheckCircle2,
  Sparkles,
  ExternalLink,
  ChevronRight,
  Globe,
  Database,
  BarChart3,
  Clock,
} from "lucide-react";
import PublicNavbar from "../components/PublicNavbar";

const scenarios = [
  {
    id: "aral-sea",
    title: "Aral Sea Desiccation",
    location: "South Aral Basin • 44.5° N, 59.2° E",
    query: "Quantify surface water loss and salt flat expansion over the South Aral Sea",
    sensor: "Sentinel-2 MSI (B3/B8 NDWI)",
    delta: "-2,410.8 km²",
    deltaType: "loss",
    metricLabel: "Water Surface Reduced",
    confidence: "98.4%",
    image: "https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=1200&q=80",
    reasoning:
      "Siamese spectral differencing confirms 68.2% reduction in eastern basin water surface. Exposed seabed exhibits strong evaporite spectral signature with significant NDVI decline in peripheral wetland margins.",
    agentSteps: ["Entity Geocoding: 44.5°N 59.2°E", "STAC Sentinel-2 Cloud-Free Tile Fetch", "MNDWI Difference Tensor Computed", "Geodesic Polygon Quantification: 241,080 ha"],
  },
  {
    id: "valencia-flood",
    title: "Valencia Rapid Inundation",
    location: "Turia River Basin, Spain • 39.4° N, 0.37° W",
    query: "Map flood inundation footprint across agricultural basin following flash flood event",
    sensor: "Sentinel-1 SAR C-Band (VV/VH)",
    delta: "+184.6 km²",
    deltaType: "increase",
    metricLabel: "Active Inundation Area",
    confidence: "96.8%",
    image: "https://images.unsplash.com/photo-1518457607834-6e8d80c183c5?auto=format&fit=crop&w=1200&q=80",
    reasoning:
      "Specular backscatter reflection in SAR C-band isolates floodwaters penetrating dense storm clouds. High-confidence inundation detected across 1,846 hectares of citrus cropland and transport arteries.",
    agentSteps: ["Storm Window SAR Search: 2024-10-29", "Radiometric Terrain Calibration", "Lee Speckle Filtering & Thresholding", "Vector Inundation Overlay Output"],
  },
  {
    id: "amazon-deforest",
    title: "Amazon Canopy Extraction",
    location: "Rondônia, Brazil • 10.8° S, 61.9° W",
    query: "Detect illegal canopy clearing and logging roads inside biological reserve",
    sensor: "Landsat-9 OLI-2 + Sentinel-2",
    delta: "-42.3 km²",
    deltaType: "loss",
    metricLabel: "Primary Canopy Loss",
    confidence: "99.1%",
    image: "https://images.unsplash.com/photo-1511497584788-87676104235f?auto=format&fit=crop&w=1200&q=80",
    reasoning:
      "Fishbone deforestation pattern detected extending 14km south of reserve boundary. Mean NDVI dropped from 0.78 to 0.21, indicating complete canopy removal and exposed soil preparation.",
    agentSteps: ["Multi-Temporal Orthorectification", "Red-Edge / NIR Contrast Ratio", "Morphological Road Extraction", "Damage Footprint Vector Export"],
  },
];

const heroImg =
  "https://images.unsplash.com/photo-1614730321146-b6fa6a46bcb4?auto=format&fit=crop&w=1800&q=85";

export default function HomePage() {
  const [activeScenario, setActiveScenario] = useState(scenarios[0]);

  return (
    <div className="home">
      <PublicNavbar />

      {/* Hero Section */}
      <section
        className="hero"
        style={{
          backgroundImage: `linear-gradient(90deg, rgba(2,12,20,.95), rgba(2,12,20,.65)), url(${heroImg})`,
        }}
      >
        <div className="hero-content">
          <div className="constellation-ticker">
            <span className="pulse-dot"></span>
            <span>
              LIVE MISSION STREAM: <b>SENTINEL-1/2 • LANDSAT-8/9 • PLANETARY COMPUTER</b>
            </span>
          </div>

          <h1>
            Commercial Earth Intelligence <br />
            <span>at the Speed of Thought.</span>
          </h1>
          <p>
            An enterprise vision-language AI engine for multimodal satellite remote sensing.
            Ask open-ended questions, upload imagery, or monitor planetary change with sub-meter
            semantic grounding, bi-temporal Siamese deep learning, and geodesic area verification.
          </p>

          <div className="hero-actions">
            <Link className="btn primary" href="/assistant">
              Launch Mission Control <ArrowRight size={17} />
            </Link>
            <Link className="btn dark-outline" href="/dashboard">
              <Compass size={16} /> Open Dashboard
            </Link>
            <a className="btn ghost" href="#simulator">
              Interactive Simulator ↓
            </a>
          </div>
        </div>

        {/* Real-time Constellation Partner Stream Strip */}
        <div className="use-cases">
          {[
            [Satellite, "Copernicus Sentinel-2", "10m Optical"],
            [Radio, "Copernicus Sentinel-1", "C-Band SAR"],
            [Globe, "USGS Landsat 8/9", "30m Multi-Spectral"],
            [Database, "MS Planetary Computer", "STAC Ingest"],
            [Cpu, "Qwen Agentic SLM", "Strict Validation"],
            [ShieldCheck, "Geodesic Engine", "Zero Hallucination"],
          ].map(([Icon, label, sub]: any) => (
            <div key={label}>
              <Icon size={18} />
              <strong style={{ fontSize: "11px", color: "#e6f4f7" }}>{label}</strong>
              <span style={{ fontSize: "9px", color: "#7796a3" }}>{sub}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Benchmarks Ribbon */}
      <div className="benchmarks-strip">
        <div className="benchmark-item">
          <strong>10<span>m</span></strong>
          <p>Ground Sample Distance (GSD)</p>
        </div>
        <div className="benchmark-item">
          <strong>&lt;2.4<span>s</span></strong>
          <p>Agentic SLM Planning Latency</p>
        </div>
        <div className="benchmark-item">
          <strong>99.8<span>%</span></strong>
          <p>Geodesic Coordinate Accuracy</p>
        </div>
        <div className="benchmark-item">
          <strong>126/126</strong>
          <p>Automated Verification Tests</p>
        </div>
      </div>

      {/* Interactive Live Scenario Simulator */}
      <section id="simulator" style={{ padding: "80px 8%", background: "#05121a" }}>
        <div style={{ textAlign: "center", maxWidth: "680px", margin: "0 auto 30px" }}>
          <span className="eyebrow">LIVE INTERACTIVE TELEMETRY</span>
          <h2 style={{ fontSize: "36px", margin: "10px 0" }}>
            See SatQuery AI in <span>Mission Action</span>
          </h2>
          <p style={{ color: "var(--muted)", fontSize: "14px", lineHeight: "1.7" }}>
            Select a real-world Earth observation challenge below to inspect how the autonomous agent
            coordinates multi-spectral imagery, deep change tensors, and analytical reasoning.
          </p>
        </div>

        <div className="simulator-wrapper">
          <div className="simulator-header">
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <span className="pulse-dot"></span>
              <span style={{ fontSize: "12px", fontWeight: 700, color: "#eaf3f6", letterSpacing: "0.5px" }}>
                MISSION WORKSPACE SIMULATOR
              </span>
              <span className="tier-pill enterprise">ENTERPRISE ACTIVE</span>
            </div>
            <span style={{ fontSize: "11px", color: "#7e9ca9", fontFamily: "monospace" }}>
              COORD: {activeScenario.location}
            </span>
          </div>

          <div className="simulator-tabs">
            {scenarios.map((s) => (
              <button
                key={s.id}
                onClick={() => setActiveScenario(s)}
                className={`sim-tab-btn ${activeScenario.id === s.id ? "active" : ""}`}
              >
                <Activity size={13} />
                {s.title}
              </button>
            ))}
          </div>

          <div className="simulator-body">
            {/* Visual Radar / Satellite viewport */}
            <div className="sim-radar-view">
              <img src={activeScenario.image} alt={activeScenario.title} />
              <div className="sim-radar-scan"></div>
              <div className="sim-radar-hud">
                <div>
                  <b style={{ color: "#2ee79b", display: "block" }}>SENSOR: {activeScenario.sensor}</b>
                  <span>QUERY: &quot;{activeScenario.query}&quot;</span>
                </div>
                <div style={{ textAlign: "right" }}>
                  <b style={{ color: "#38bdf8", display: "block" }}>AI CONFIDENCE: {activeScenario.confidence}</b>
                  <span>STATUS: CO-REGISTERED & VERIFIED</span>
                </div>
              </div>
            </div>

            {/* Telemetry output panel */}
            <div className="sim-telemetry-panel">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <h3>{activeScenario.title}</h3>
                <span style={{ fontSize: "11px", color: "#8da5b0" }}>{activeScenario.location}</span>
              </div>

              <div className="sim-stats-row">
                <div className="sim-metric-card">
                  <span>{activeScenario.metricLabel}</span>
                  <strong style={{ color: activeScenario.deltaType === "loss" ? "#ff5267" : "#2ee79b" }}>
                    {activeScenario.delta}
                  </strong>
                </div>
                <div className="sim-metric-card">
                  <span>Verification Confidence</span>
                  <strong>{activeScenario.confidence}</strong>
                </div>
              </div>

              <div className="sim-reasoning-box">
                <strong style={{ display: "block", color: "#38bdf8", marginBottom: "6px" }}>
                  Autonomous Agent Synthesis:
                </strong>
                {activeScenario.reasoning}
              </div>

              <div>
                <span style={{ fontSize: "10px", color: "#7a95a1", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                  Agent Execution Pipeline Trace:
                </span>
                <ul style={{ margin: "6px 0 0", paddingLeft: "16px", fontSize: "11px", color: "#9eb6c2", lineHeight: "1.6" }}>
                  {activeScenario.agentSteps.map((step, idx) => (
                    <li key={idx}>{step}</li>
                  ))}
                </ul>
              </div>

              <Link
                href="/assistant"
                className="btn primary small"
                style={{ marginTop: "auto", justifyContent: "center" }}
              >
                Run Custom Query on this AOI <ArrowRight size={14} />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Commercial 4-Pillar Showcase */}
      <section className="home-feature">
        <div>
          <span className="eyebrow">FOUR CORE ARCHITECTURAL PILLARS</span>
          <h2>
            Engineered for <span>Mission Critical</span> Decisions.
          </h2>
          <p>
            Whether triaging disaster damage within minutes of a satellite pass, auditing environmental
            compliance, or assessing infrastructure expansion, SatQuery removes manual GIS friction.
          </p>
          <div style={{ marginTop: "30px" }}>
            <Link href="/docs" className="btn dark-outline">
              Read Technical Whitepaper <ExternalLink size={14} />
            </Link>
          </div>
        </div>
        <div className="feature-grid">
          <div className="feature-mini">
            <b>01</b>
            <strong>Zero-Upload Autonomous Retrieval</strong>
            <p>
              Users enter plain language inquiries. SatQuery automatically resolves global bounding boxes,
              queries STAC catalogues, and fetches current Sentinel-2 or Landsat rasters.
            </p>
          </div>
          <div className="feature-mini">
            <b>02</b>
            <strong>Multi-Modal RS-VLM & Grounding</strong>
            <p>
              Deep vision-language specialist models detect infrastructure damage, count vessels, and
              delineate target boundaries with pixel-level coordinate masks.
            </p>
          </div>
          <div className="feature-mini">
            <b>03</b>
            <strong>Siamese ChangeFormer Deep Learning</strong>
            <p>
              Bi-temporal before/after differencing calculates exact geodesic surface modifications in square
              kilometers and hectares, fully resilient to atmospheric haze.
            </p>
          </div>
          <div className="feature-mini">
            <b>04</b>
            <strong>Optical + Synthetic Aperture Radar (SAR)</strong>
            <p>
              Fuses optical spectral reflections with cloud-penetrating Sentinel-1 SAR C-band radar to
              guarantee 24/7 visibility during monsoons and heavy storms.
            </p>
          </div>
        </div>
      </section>

      {/* Commercial Pricing Matrix */}
      <section className="pricing-section">
        <div className="pricing-header">
          <span className="eyebrow">COMMERCIAL LICENSING</span>
          <h2>
            Transparent Plans for <span>Every Planetary Scale</span>
          </h2>
          <p>
            Deploy on cloud, integrate via REST API, or run air-gapped sovereign installations for defense and
            emergency response.
          </p>
        </div>

        <div className="pricing-grid">
          {/* Tier 1 */}
          <div className="pricing-card">
            <h3>Academic & Community</h3>
            <p>For university researchers, open-source developers, and environmental advocates.</p>
            <div className="pricing-price">
              $0 <small>/ month</small>
            </div>
            <ul className="pricing-features">
              <li><CheckCircle2 size={14} /> Open access STAC catalogues (Sentinel-2, Landsat)</li>
              <li><CheckCircle2 size={14} /> Single-image VQA & classification</li>
              <li><CheckCircle2 size={14} /> Standard biophysical indices (NDVI, NDWI)</li>
              <li><CheckCircle2 size={14} /> Community support & public documentation</li>
            </ul>
            <Link href="/signup" className="btn dark-outline">
              Get Started Free
            </Link>
          </div>

          {/* Tier 2: Featured */}
          <div className="pricing-card featured">
            <span className="pricing-popular-badge">MOST POPULAR</span>
            <h3>Enterprise Mission Pro</h3>
            <p>For commercial GIS operations, commodities trading, insurance risk, and forestry.</p>
            <div className="pricing-price">
              $499 <small>/ month</small>
            </div>
            <ul className="pricing-features">
              <li><CheckCircle2 size={14} /> <b>Autonomous Zero-Upload Global Search</b></li>
              <li><CheckCircle2 size={14} /> <b>Siamese Bi-Temporal ChangeFormer engine</b></li>
              <li><CheckCircle2 size={14} /> <b>Optical + SAR Cloud-Penetrating Fusion</b></li>
              <li><CheckCircle2 size={14} /> Sub-meter commercial imagery ingest (Planet/Airbus)</li>
              <li><CheckCircle2 size={14} /> Dedicated GPU reasoning workers (&lt;2s response)</li>
              <li><CheckCircle2 size={14} /> REST API & Python SDK with 99.9% uptime SLA</li>
            </ul>
            <Link href="/signup" className="btn primary">
              Start 14-Day Enterprise Trial <ArrowRight size={15} />
            </Link>
          </div>

          {/* Tier 3 */}
          <div className="pricing-card">
            <h3>Sovereign & Defense</h3>
            <p>For national space agencies, defense ministries, and critical disaster authorities.</p>
            <div className="pricing-price">
              Custom <small>contract</small>
            </div>
            <ul className="pricing-features">
              <li><CheckCircle2 size={14} /> Air-gapped on-premise Kubernetes deployment</li>
              <li><CheckCircle2 size={14} /> Custom SLM fine-tuning on classified satellite feeds</li>
              <li><CheckCircle2 size={14} /> Automated rapid disaster triage notifications</li>
              <li><CheckCircle2 size={14} /> 24/7 dedicated remote sensing engineering team</li>
              <li><CheckCircle2 size={14} /> Zero-trust audit logging & SOC2 / ISO compliance</li>
            </ul>
            <Link href="/contact" className="btn dark-outline">
              Contact Defense Sales
            </Link>
          </div>
        </div>
      </section>

      {/* Commercial Footer */}
      <footer
        style={{
          background: "#040d13",
          borderTop: "1px solid rgba(255, 255, 255, 0.06)",
          padding: "50px 8% 30px",
          fontSize: "12px",
          color: "#839aa5",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "20px",
            marginBottom: "30px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span className="brand-mark">
              <Satellite size={16} />
            </span>
            <strong style={{ color: "#fff", fontSize: "14px" }}>SatQuery AI</strong>
            <span style={{ color: "#2ee79b", fontSize: "11px" }}>• v2.4 Commercial Ready</span>
          </div>

          <div style={{ display: "flex", gap: "24px" }}>
            <Link href="/dashboard" style={{ color: "#bad0da" }}>Dashboard</Link>
            <Link href="/assistant" style={{ color: "#bad0da" }}>AI Assistant</Link>
            <Link href="/compare" style={{ color: "#bad0da" }}>Bi-Temporal Compare</Link>
            <Link href="/docs" style={{ color: "#bad0da" }}>Documentation</Link>
            <Link href="/contact" style={{ color: "#bad0da" }}>Enterprise Support</Link>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span className="pulse-dot"></span>
            <span style={{ color: "#2ee79b", fontWeight: 600 }}>All Systems Operational</span>
          </div>
        </div>

        <div
          style={{
            borderTop: "1px solid rgba(255, 255, 255, 0.04)",
            paddingTop: "20px",
            display: "flex",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "10px",
          }}
        >
          <p>© 2026 SatQuery-X Inc. Geodesic remote sensing intelligence. Compliant with ESA & NASA data policies.</p>
          <p>SIH Problem Statement 26167 • Multimodal Satellite Reasoning</p>
        </div>
      </footer>
    </div>
  );
}
