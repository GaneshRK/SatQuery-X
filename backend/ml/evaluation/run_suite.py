"""Run any configured subset of the real SatQuery evaluation suite.

Example:
  python -m ml.evaluation.run_suite --config evaluation.yaml

The config lists real checkpoints and held-out manifests. Missing inputs cause
an error rather than producing placeholder numbers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml.evaluation.evaluate_benchmarks import run_benchmark_eval


def main() -> None:
    p = argparse.ArgumentParser(description="Run the real SatQuery evaluation suite")
    p.add_argument("--config", required=True, help="JSON evaluation-suite configuration")
    args = p.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    jobs = cfg.get("evaluations", [])
    if not jobs:
        raise ValueError("Evaluation suite config contains no evaluations.")
    reports = []
    for job in jobs:
        reports.append(run_benchmark_eval(**job))
    print(json.dumps([{"model_id": r["model_id"], "dataset": r.get("dataset"), "split": r.get("split"), "sample_count": r["sample_count"], "metrics": r["metrics"]} for r in reports], indent=2))


if __name__ == "__main__":
    main()
