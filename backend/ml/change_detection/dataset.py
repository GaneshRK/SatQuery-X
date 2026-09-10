"""Manifest-backed bi-temporal change-detection dataset."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
import torch
from torch.utils.data import Dataset


def _records(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("records", data.get("items", []))
    if not isinstance(data, list):
        raise ValueError("Change-detection manifest must contain a list or {records:[...]}")
    return data


class ChangeDetectionManifestDataset(Dataset):
    """Manifest records require image_t1, image_t2 and binary mask paths."""

    def __init__(self, manifest: str | Path, size: int = 256) -> None:
        self.manifest = Path(manifest)
        self.root = self.manifest.parent
        self.items = _records(self.manifest)
        self.size = int(size)
        for i, item in enumerate(self.items):
            for key in ("image_t1", "image_t2", "mask"):
                if key not in item:
                    raise ValueError(f"Record {i} is missing required field: {key}")

    def __len__(self) -> int:
        return len(self.items)

    def _path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else self.root / path

    def _image(self, path: Path) -> torch.Tensor:
        with Image.open(path) as image:
            image = image.convert("RGB").resize((self.size, self.size), Image.Resampling.BILINEAR)
            arr = np.asarray(image, dtype=np.float32) / 255.0
        return torch.from_numpy(arr).permute(2, 0, 1)

    def _mask(self, path: Path) -> torch.Tensor:
        with Image.open(path) as image:
            image = image.convert("L").resize((self.size, self.size), Image.Resampling.NEAREST)
            arr = (np.asarray(image, dtype=np.uint8) > 0).astype(np.float32)
        return torch.from_numpy(arr)[None, ...]

    def __getitem__(self, index: int):
        item = self.items[index]
        return {
            "t1": self._image(self._path(item["image_t1"])),
            "t2": self._image(self._path(item["image_t2"])),
            "mask": self._mask(self._path(item["mask"])),
            "id": item.get("id", str(index)),
        }
