"""Unified real evaluation entrypoint for trained SatQuery models.

This module never contains benchmark scores. A score exists only after
inference has been executed against a supplied held-out manifest.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def run_benchmark_eval(model_id: str, checkpoint_path: str, dataset_name: str, split: str = "test", manifest: str | None = None, output: str | None = None, **kwargs):
    if not manifest:
        raise ValueError("A real held-out --manifest is required; no score is inferred or hardcoded.")
    if not Path(manifest).exists():
        raise FileNotFoundError(manifest)
    if not Path(checkpoint_path).exists():
        raise FileNotFoundError(checkpoint_path)
    name = dataset_name.lower().replace("_", "-")
    if model_id == "RS_VQA" and name in {"rsvqa", "vrsbench-vqa"}:
        from ml.evaluation.evaluate_rsvqa import evaluate
        return evaluate(checkpoint_path, manifest, output or f"ml/evaluation/results/RS_VQA_{dataset_name}_{split}.json", dataset_name, split, kwargs.get("image_root"))
    if model_id == "CHANGE_DETECTION" and name in {"change-detection", "levir-cd", "dsifn-cd"}:
        from ml.change_detection.evaluate import evaluate
        return evaluate(manifest, checkpoint_path, output or f"ml/evaluation/results/CHANGE_DETECTION_{dataset_name}_{split}.json", **{k: kwargs[k] for k in ("threshold", "size", "device") if k in kwargs})
    if model_id == "CHANGE_VQA" and name in {"change-vqa", "cdvqa", "cdvqa-bitemporal"}:
        from ml.training_change_vqa.evaluate import evaluate
        return evaluate(checkpoint_path, manifest, output or f"ml/evaluation/results/CHANGE_VQA_{dataset_name}_{split}.json")
    raise ValueError(f"No real evaluator is registered for model={model_id!r}, dataset={dataset_name!r}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a real SatQuery benchmark evaluation")
    parser.add_argument("--model", required=True, choices=["RS_VQA", "CHANGE_DETECTION", "CHANGE_VQA"])
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output")
    parser.add_argument("--image-root")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()
    report = run_benchmark_eval(**vars(args))
    print(report["metrics"])
