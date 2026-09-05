"""RS-VQA PyTorch Dataset implementation per §16 & §54."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

try:
    from torch.utils.data import Dataset
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    class Dataset:
        pass


class RSVQADataset(Dataset):
    """
    Remote Sensing Visual Question Answering dataset loader.
    Supports in-memory samples or on-disk GeoTIFF / PNG datasets with optional data augmentation.
    """
    def __init__(
        self,
        samples: list[dict[str, Any]] | None = None,
        image_dir: str | Path | None = None,
        transform: Any = None,
        split: str = "train",
    ) -> None:
        self.samples = samples or []
        self.image_dir = Path(image_dir) if image_dir else None
        self.transform = transform
        self.split = split

        if not self.samples:
            # Generate representative default remote-sensing VQA sample curriculum
            self.samples = [
                {
                    "image_id": "sample_urban_01",
                    "question": "Is there built-up infrastructure in this scene?",
                    "answer": "Yes, dense residential and commercial buildings are present.",
                    "land_cover": "urban",
                },
                {
                    "image_id": "sample_water_02",
                    "question": "Are there open water bodies visible?",
                    "answer": "Yes, a prominent river corridor traverses the scene.",
                    "land_cover": "water",
                },
                {
                    "image_id": "sample_forest_03",
                    "question": "What is the dominant vegetation type?",
                    "answer": "Dense canopy forest covers the elevated terrain.",
                    "land_cover": "vegetation",
                },
                {
                    "image_id": "sample_agri_04",
                    "question": "What agricultural activity is observed?",
                    "answer": "Active crop fields and cultivated parcels are visible.",
                    "land_cover": "agriculture",
                },
            ]

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        item = self.samples[idx]
        image = None

        if self.image_dir and "image_file" in item:
            path = self.image_dir / item["image_file"]
            if path.exists():
                image = Image.open(path).convert("RGB")

        if image is None:
            # Synthetic fallback image for unit testing / rehearsal [384, 384, 3]
            np.random.seed(idx)
            raw = np.random.randint(40, 200, (384, 384, 3), dtype=np.uint8)
            image = Image.fromarray(raw, mode="RGB")

        if self.transform:
            image = self.transform(image)

        return {
            "image": image,
            "question": item["question"],
            "answer": item["answer"],
            "image_id": item.get("image_id", str(idx)),
        }
