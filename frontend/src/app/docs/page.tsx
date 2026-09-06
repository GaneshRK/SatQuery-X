"use client";

import { CheckCircle2, ArrowRight } from "lucide-react";
import Link from "next/link";
import PublicNavbar from "../../components/PublicNavbar";

export default function DocumentationPage() {
  const steps = [
    {
      title: "Create an Account",
      desc: "Register your analyst profile with email or authenticate with the default demo account.",
    },
    {
      title: "Explore the Map & Define AOI",
      desc: "Search regions, inspect Sentinel-1 SAR and Sentinel-2 optical layers, and set bounding boxes.",
    },
    {
      title: "Ask Natural Language Queries",
      desc: "Pose open-ended doubts, ask what is changing, or upload single, bi-temporal, or optical+SAR imagery.",
    },
    {
      title: "Autonomous Multi-Agent Execution",
      desc: "Watch the Qwen SLM orchestrator dispatch GeoChat, ChangeFormer, or Grounding DINO with live traces.",
    },
    {
      title: "Verify Metrics & Download Reports",
      desc: "Inspect geodesic surface area calculations, verify biophysical indices, and export executive reports.",
    },
  ];

  return (
    <>
      <PublicNavbar />
      <div className="public-page docs">
        <div>
          <span className="eyebrow">DOCUMENTATION & USER GUIDE</span>
          <h1>How to use SatQuery AI</h1>
          <p>
            A 5-step guided walkthrough to turn multimodal satellite observations into verified,
            geodesic-grounded intelligence.
          </p>
        </div>

        <div className="docs-grid">
          {steps.map((st, i) => (
            <div className="doc-step" key={st.title}>
              <span>{i + 1}</span>
              <CheckCircle2 size={24} />
              <b>{st.title}</b>
              <p>{st.desc}</p>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 40, textAlign: "center" }}>
          <Link href="/assistant" className="btn primary">
            Launch AI Assistant <ArrowRight size={16} />
          </Link>
        </div>
      </div>
    </>
  );
}
