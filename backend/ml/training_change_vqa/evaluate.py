"""Real bi-temporal Change VQA evaluation; no synthetic metrics."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ml.evaluation.metrics import normalize_answer, token_f1, mean
from ml.training_change_vqa.dataset import ChangeVQAManifestDataset
from apps.models_ai.change_vqa.hf_model import HuggingFaceChangeVQA


def evaluate(checkpoint: str, manifest: str, output: str) -> dict:
    ds = ChangeVQAManifestDataset(manifest)
    if len(ds) == 0:
        raise ValueError("Change VQA manifest contains no real samples.")
    model = HuggingFaceChangeVQA(checkpoint)
    rows = []; exact = []; f1s = []; latencies = []
    for x in ds:
        start = time.perf_counter()
        result = model.answer(x["t1"], x["t2"], x["question"])
        latency_ms = (time.perf_counter() - start) * 1000.0
        prediction = result["answer"]; reference = x["answer"]
        em = int(normalize_answer(prediction) == normalize_answer(reference)); score = token_f1(prediction, reference)
        exact.append(em); f1s.append(score); latencies.append(latency_ms)
        rows.append({"id": x["id"], "question": x["question"], "prediction": prediction, "reference": reference, "exact_match": em, "token_f1": score, "latency_ms": latency_ms})
    report = {"task": "bi_temporal_change_vqa", "model_id": "CHANGE_VQA", "checkpoint": str(Path(checkpoint).resolve()), "manifest": str(Path(manifest).resolve()), "sample_count": len(rows), "metrics": {"exact_match": mean(exact), "token_f1": mean(f1s), "mean_latency_ms": mean(latencies)}, "predictions": rows}
    out = Path(output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    p = argparse.ArgumentParser(description="Run real Change VQA evaluation")
    p.add_argument("--checkpoint", required=True); p.add_argument("--manifest", required=True); p.add_argument("--output", required=True)
    args = p.parse_args(); report = evaluate(**vars(args)); print(json.dumps(report["metrics"], indent=2))


if __name__ == "__main__": main()
