"""Confidence calibration utilities for SatQuery supervised models.

Calibration is an empirical post-hoc transform learned on held-out validation
predictions. It must never be fitted on the test set.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class CalibrationResult:
    temperature: float
    nll_before: float
    nll_after: float
    ece_before: float
    ece_after: float
    brier_before: float
    brier_after: float


def _sigmoid(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, -80.0, 80.0)
    return 1.0 / (1.0 + np.exp(-x))


def binary_metrics(prob: np.ndarray, target: np.ndarray, bins: int = 15) -> dict[str, float]:
    p = np.asarray(prob, dtype=np.float64).reshape(-1)
    y = np.asarray(target, dtype=np.float64).reshape(-1)
    valid = np.isfinite(p) & np.isfinite(y)
    p, y = np.clip(p[valid], 1e-7, 1 - 1e-7), y[valid]
    if p.size == 0:
        raise ValueError("No finite calibration samples were supplied.")
    nll = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    brier = float(np.mean((p - y) ** 2))
    ece = 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p <= hi if i == bins - 1 else p < hi)
        if not np.any(mask):
            continue
        ece += float(mask.mean()) * abs(float(p[mask].mean()) - float(y[mask].mean()))
    return {"nll": nll, "brier": brier, "ece": float(ece)}


def fit_temperature_binary(logits: np.ndarray, target: np.ndarray) -> CalibrationResult:
    """Fit a single positive temperature by minimizing validation NLL."""
    logits = np.asarray(logits, dtype=np.float64).reshape(-1)
    target = np.asarray(target, dtype=np.float64).reshape(-1)
    valid = np.isfinite(logits) & np.isfinite(target)
    logits, target = logits[valid], target[valid]
    if logits.size == 0:
        raise ValueError("No finite logits were supplied for calibration.")

    before = binary_metrics(_sigmoid(logits), target)
    # Deterministic grid + local refinement avoids adding an optimizer dependency.
    grid = np.exp(np.linspace(math.log(0.05), math.log(20.0), 161))
    losses = []
    for t in grid:
        p = np.clip(_sigmoid(logits / float(t)), 1e-7, 1 - 1e-7)
        losses.append(-np.mean(target * np.log(p) + (1 - target) * np.log(1 - p)))
    best = float(grid[int(np.argmin(losses))])
    for _ in range(3):
        lo, hi = best / 1.12, best * 1.12
        local = np.exp(np.linspace(math.log(lo), math.log(hi), 41))
        vals = []
        for t in local:
            p = np.clip(_sigmoid(logits / float(t)), 1e-7, 1 - 1e-7)
            vals.append(-np.mean(target * np.log(p) + (1 - target) * np.log(1 - p)))
        best = float(local[int(np.argmin(vals))])
    after = binary_metrics(_sigmoid(logits / best), target)
    return CalibrationResult(best, before["nll"], after["nll"], before["ece"], after["ece"], before["brier"], after["brier"])


def apply_binary_temperature(logits: np.ndarray, temperature: float) -> np.ndarray:
    t = float(temperature)
    if not math.isfinite(t) or t <= 0:
        raise ValueError("Calibration temperature must be finite and > 0.")
    return _sigmoid(np.asarray(logits, dtype=np.float64) / t)
