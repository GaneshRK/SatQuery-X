"""Fit and save held-out temperature scaling for change detection."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
from PIL import Image

from ml.evaluation.calibration import fit_temperature_binary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--logits-npy", required=True, help="Validation logits flattened or image-shaped.")
    p.add_argument("--targets-npy", required=True, help="Validation binary targets matching logits.")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    logits = np.load(args.logits_npy)
    targets = np.load(args.targets_npy)
    result = fit_temperature_binary(logits, targets)
    payload = {"task":"CHANGE_DETECTION", "method":"temperature_scaling", "temperature":result.temperature,
               "validation_metrics":{"before": {"nll":result.nll_before,"ece":result.ece_before,"brier":result.brier_before},
                                     "after": {"nll":result.nll_after,"ece":result.ece_after,"brier":result.brier_after}},
               "calibration_data":"held_out_validation"}
    Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))

if __name__ == "__main__": main()
