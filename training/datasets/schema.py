"""Standardized RemoteSensingSample data contract for all remote sensing datasets (§8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RemoteSensingSample:
    sample_id: str
    task_type: str  # "vqa", "caption", "grounding", "change_detection", "change_vqa", "fusion"
    image_paths: list[str] = field(default_factory=list)
    sensor_types: list[str] = field(default_factory=list)  # "optical", "sar", "multispectral"
    capture_dates: list[datetime | None] = field(default_factory=list)
    crs: str | None = None
    bounds_wgs84: dict[str, float] | None = None
    query: str | None = None
    ground_truth_answer: str | None = None
    ground_truth_caption: str | None = None
    ground_truth_boxes: list[dict[str, Any]] = field(default_factory=list)
    ground_truth_change_mask: str | None = None
    land_cover_labels: list[str] = field(default_factory=list)
    split: str = "train"  # "train", "val", "test", "heldout_eval"
    metadata: dict[str, Any] = field(default_factory=dict)
