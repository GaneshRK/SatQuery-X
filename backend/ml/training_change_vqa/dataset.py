"""Manifest-backed bi-temporal Change VQA dataset."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from PIL import Image
from torch.utils.data import Dataset

def load_records(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if path.suffix.lower() == ".jsonl":
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict): data = data.get("records", data.get("items", []))
    if not isinstance(data, list): raise ValueError("Change VQA manifest must contain a list or {records:[...]}")
    return data

class ChangeVQAManifestDataset(Dataset):
    """Each record must contain image_t1, image_t2, question and answer."""
    def __init__(self, manifest: str | Path):
        self.manifest = Path(manifest)
        self.root = self.manifest.parent
        self.items = load_records(self.manifest)
        for i, item in enumerate(self.items):
            for key in ("image_t1", "image_t2", "question", "answer"):
                if key not in item or item[key] in (None, ""):
                    raise ValueError(f"Record {i} is missing required field: {key}")

    def __len__(self): return len(self.items)

    def _path(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else self.root / p

    def _image(self, value: str) -> Image.Image:
        with Image.open(self._path(value)) as im:
            return im.convert("RGB").copy()

    def __getitem__(self, index: int):
        item = self.items[index]
        return {"t1": self._image(item["image_t1"]), "t2": self._image(item["image_t2"]),
                "question": str(item["question"]), "answer": str(item["answer"]),
                "id": str(item.get("id", index))}
