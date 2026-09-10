"use client";

import React from "react";
import { CheckCircle2, CircleHelp, ShieldCheck, Target, Gauge } from "lucide-react";
import { AnalysisResponseData } from "./assistant/ScientificAnswerCard";

interface OutcomeQualityPanelProps {
  data: AnalysisResponseData;
}

function clamp(value: number) {
  return Math.max(0, Math.min(100, value));
}

function scoreFromData(data: AnalysisResponseData) {
  const breakdown = data.confidence_breakdown;
  if (!breakdown) {
    const confidence = typeof data.confidence === "number" ? data.confidence * 100 : null;
    return confidence === null ? null : Math.round(confidence * 10) / 10;
  }

  const values = [
    breakdown.data_quality_pct,
    breakdown.model_confidence_pct,
    breakdown.geometry_quality_pct,
    breakdown.evidence_coverage_pct,
    breakdown.result_confidence_pct,
  ].filter((v): v is number => typeof v === "number" && Number.isFinite(v));

  if (!values.length) return null;
  return Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 10) / 10;
}

const metricLabels: Array<{ key: keyof NonNullable<AnalysisResponseData["confidence_breakdown"]>; label: string }> = [
  { key: "data_quality_pct", label: "Input quality" },
  { key: "model_confidence_pct", label: "Model confidence" },
  { key: "geometry_quality_pct", label: "Geometry quality" },
  { key: "evidence_coverage_pct", label: "Evidence coverage" },
  { key: "result_confidence_pct", label: "Result confidence" },
];

export default function OutcomeQualityPanel({ data }: OutcomeQualityPanelProps) {
  const breakdown = data.confidence_breakdown;
  const score = scoreFromData(data);
  const hasGroundTruth = Boolean(
    data.metrics?.ground_truth_accuracy ?? data.metrics?.accuracy ?? data.metrics?.benchmark_accuracy
  );

  return (
    <section className="outcome-panel" aria-label="Outcome quality and correctness evidence">
      <div className="outcome-header">
        <div className="outcome-title-wrap">
          <div className="outcome-icon"><Gauge size={18} /></div>
          <div>
            <div className="eyebrow">Presentation-ready validation</div>
            <h3>Outcome Quality & Correctness Evidence</h3>
            <p>Confidence is separated from measured accuracy so the result is not overstated.</p>
          </div>
        </div>
        <div className="outcome-groundtruth">
          <Target size={14} />
          {hasGroundTruth ? "Ground-truth benchmark available" : "Ground-truth accuracy: not supplied"}
        </div>
      </div>

      <div className="outcome-grid">
        <div className="outcome-score-card">
          <div className="score-ring" style={{ "--score": `${score ?? 0}%` } as React.CSSProperties}>
            <div className="score-ring-inner">
              <span>{score === null ? "—" : score.toFixed(1)}</span>
              <small>/ 100</small>
            </div>
          </div>
          <div>
            <div className="score-label">Outcome quality score</div>
            <div className="score-status">
              {score === null ? "Awaiting validated evidence" : score >= 85 ? "Strong evidence alignment" : score >= 70 ? "Review before claiming high precision" : "Low evidence alignment"}
            </div>
            <div className="score-note">
              Composite evidence signal, not a substitute for a labeled test-set accuracy metric.
            </div>
          </div>
        </div>

        <div className="outcome-metrics">
          {metricLabels.map(({ key, label }) => {
            const value = breakdown?.[key];
            if (typeof value !== "number") return null;
            const safe = clamp(value);
            return (
              <div className="quality-metric" key={key}>
                <div className="quality-metric-head">
                  <span>{label}</span>
                  <strong>{safe.toFixed(1)}%</strong>
                </div>
                <div className="quality-track"><span style={{ width: `${safe}%` }} /></div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="outcome-footer">
        <div><ShieldCheck size={14} /> Evidence-backed result</div>
        <div><CheckCircle2 size={14} /> Traceable processing stages</div>
        <div><CircleHelp size={14} /> Accuracy requires ground truth</div>
      </div>
    </section>
  );
}
