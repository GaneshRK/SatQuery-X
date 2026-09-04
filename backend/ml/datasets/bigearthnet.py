"""Dataset loader for BigEarthNet Sentinel-1 SAR + Sentinel-2 Optical pairs with text labels per §15."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class BigEarthNetDataset:
    def __init__(self, root_dir: str | Path, split: str = "train", multimodal: bool = True):
        self.root_dir = Path(root_dir)
        self.split = split
        self.multimodal = multimodal
        self.samples: list[dict[str, Any]] = []

    def load_metadata(self) -> list[dict[str, Any]]:
        """Parses BigEarthNet sample indices (optical bands + SAR VV/VH + multi-label classes)."""
        manifest_path = self.root_dir / f"{self.split}_manifest.json"
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                self.samples = json.load(f)
        return self.samples

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        return self.samples[idx]
