# Stage 11 — Confidence calibration and fallback policy

SatQuery now distinguishes **model confidence** from raw model scores.

## What changed

- Added held-out validation temperature scaling utilities in `ml/evaluation/calibration.py`.
- Added calibration artifact builders for change detection and optical-SAR fusion.
- Runtime wrappers consume calibration only when an explicit JSON artifact is configured.
- Uncalibrated supervised inference does not claim calibrated confidence.
- Existing heuristic/evidence fallbacks remain explicitly identified and are never presented as calibrated neural confidence.
- Calibration reports include NLL, ECE and Brier score before/after calibration.

## Fit the artifacts

Change detection:

```bash
python -m ml.evaluation.calibrate_change_detection \
  --logits-npy validation_logits.npy \
  --targets-npy validation_targets.npy \
  --output ml/checkpoints/change_detection_calibration.json
```

Optical-SAR:

```bash
python -m ml.evaluation.calibrate_optical_sar \
  --logits-npy validation_logits.npy \
  --labels-npy validation_labels.npy \
  --output ml/checkpoints/optical_sar_calibration.json
```

The arrays must come from a **held-out validation split** produced by the real
trained model. Do not fit temperature on the benchmark test set.

## Interpretation

- **NLL**: probabilistic log loss; lower is better.
- **Brier**: squared probabilistic error; lower is better.
- **ECE**: expected calibration error; lower generally means predicted
  probabilities better track empirical correctness.

A calibration artifact does not improve segmentation accuracy by itself. It
makes probability/confidence reporting more statistically meaningful.

## Important limitation

RS-VQA and Change-VQA generation confidence remains `None` unless a separate
validated confidence estimator is implemented. Generated token text is not
silently converted into a probability score.
