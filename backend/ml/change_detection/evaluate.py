"""Real supervised bi-temporal change-detection evaluation."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from ml.change_detection.dataset import ChangeDetectionManifestDataset
from ml.change_detection.model import SiameseChangeNet


def evaluate(manifest: str, checkpoint: str, output: str, threshold: float = 0.5, size: int = 256, device: str = "auto") -> dict:
    resolved_device = "cuda" if device == "auto" and torch.cuda.is_available() else ("cpu" if device == "auto" else device)
    ckpt = torch.load(checkpoint, map_location=resolved_device)
    model = SiameseChangeNet(in_channels=int(ckpt.get("in_channels", 3))).to(resolved_device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    ds = ChangeDetectionManifestDataset(manifest, size)
    loader = DataLoader(ds, batch_size=1, shuffle=False, num_workers=0)
    tp = fp = fn = tn = 0
    latencies = []
    sample_rows = []
    with torch.inference_mode():
        for batch in loader:
            start = time.perf_counter()
            probabilities = torch.sigmoid(model(batch["t1"].to(resolved_device), batch["t2"].to(resolved_device)))
            latency_ms = (time.perf_counter() - start) * 1000.0
            pred = probabilities.cpu().numpy() >= threshold
            target = batch["mask"].numpy() > 0.5
            tp_i = int(np.logical_and(pred, target).sum()); fp_i = int(np.logical_and(pred, ~target).sum())
            fn_i = int(np.logical_and(~pred, target).sum()); tn_i = int(np.logical_and(~pred, ~target).sum())
            tp += tp_i; fp += fp_i; fn += fn_i; tn += tn_i; latencies.append(latency_ms)
            sample_rows.append({"id": batch["id"][0], "tp": tp_i, "fp": fp_i, "fn": fn_i, "tn": tn_i, "latency_ms": latency_ms})

    precision = tp / max(tp + fp, 1); recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    iou = tp / max(tp + fp + fn, 1)
    accuracy = (tp + tn) / max(tp + tn + fp + fn, 1)
    report = {
        "task": "bi_temporal_change_detection", "model_id": "CHANGE_DETECTION",
        "checkpoint": str(Path(checkpoint).resolve()), "manifest": str(Path(manifest).resolve()),
        "sample_count": len(ds), "threshold": threshold,
        "metrics": {"pixel_accuracy": accuracy, "precision": precision, "recall": recall, "f1": f1, "iou": iou, "mean_latency_ms": sum(latencies)/len(latencies) if latencies else None},
        "confusion_counts": {"tp": tp, "fp": fp, "fn": fn, "tn": tn}, "samples": sample_rows,
    }
    out = Path(output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    p = argparse.ArgumentParser(description="Run real change-detection evaluation")
    p.add_argument("--manifest", required=True); p.add_argument("--checkpoint", required=True); p.add_argument("--output", required=True)
    p.add_argument("--threshold", type=float, default=0.5); p.add_argument("--size", type=int, default=256); p.add_argument("--device", default="auto")
    args = p.parse_args(); report = evaluate(**vars(args)); print(json.dumps(report["metrics"], indent=2))


if __name__ == "__main__": main()
