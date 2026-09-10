"""Manifest-backed datasets for real remote-sensing VQA training.

The loader intentionally does not invent questions/answers.  Training data must
provide the image path plus the question and answer.  For BigEarthNet domain
adaptation, a text/caption field can be used with a fixed *user prompt* so the
adaptation stage learns the remote-sensing image/text domain without claiming
that BigEarthNet itself is an RSVQA benchmark.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image
from torch.utils.data import Dataset


def _read_records(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("samples", data.get("data", []))
    if not isinstance(data, list):
        raise ValueError(f"Manifest must be a list or contain samples/data: {path}")
    return data


def _resolve(root: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else root / p


class RSVQAManifestDataset(Dataset):
    """Dataset with records: {image, question, answer}."""

    def __init__(self, manifest: str | Path, image_root: str | Path | None = None):
        self.manifest = Path(manifest)
        self.root = Path(image_root) if image_root else self.manifest.parent
        self.records = _read_records(self.manifest)
        if not self.records:
            raise ValueError(f"No samples found in {self.manifest}")
        for i, row in enumerate(self.records):
            for key in ("image", "question", "answer"):
                if not row.get(key):
                    raise ValueError(f"Sample {i} is missing required field '{key}'")

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        row = self.records[idx]
        image_path = _resolve(self.root, str(row["image"]))
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found for sample {idx}: {image_path}")
        with Image.open(image_path) as img:
            image = img.convert("RGB").copy()
        return {"image": image, "question": str(row["question"]), "answer": str(row["answer"]), "id": row.get("id", idx)}


class BigEarthNetTextDataset(Dataset):
    """Image/text domain-adaptation dataset.

    Records must contain {image, text} (or caption). No synthetic answer is
    inferred from land-cover labels. The training script uses a fixed prompt
    such as "Describe this remote-sensing image." and the supplied text as the
    target sequence.
    """

    def __init__(self, manifest: str | Path, image_root: str | Path | None = None):
        self.manifest = Path(manifest)
        self.root = Path(image_root) if image_root else self.manifest.parent
        self.records = _read_records(self.manifest)
        if not self.records:
            raise ValueError(f"No samples found in {self.manifest}")
        for i, row in enumerate(self.records):
            if not row.get("image"):
                raise ValueError(f"Sample {i} is missing 'image'")
            if not (row.get("text") or row.get("caption")):
                raise ValueError(f"Sample {i} is missing 'text'/'caption'")

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        row = self.records[idx]
        image_path = _resolve(self.root, str(row["image"]))
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found for sample {idx}: {image_path}")
        with Image.open(image_path) as img:
            image = img.convert("RGB").copy()
        return {
            "image": image,
            "text": str(row.get("text") or row.get("caption")),
            "id": row.get("id", idx),
        }
