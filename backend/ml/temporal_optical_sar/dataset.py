from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from PIL import Image
import torch
from torch.utils.data import Dataset
from .model import question_ids

class TemporalOpticalSARDataset(Dataset):
    required = {"optical_t1", "sar_t1", "optical_t2", "sar_t2", "question", "answer"}
    def __init__(self, manifest: str, answer_to_id: dict[str, int] | None = None):
        self.path = Path(manifest)
        self.rows = [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]
        for i, row in enumerate(self.rows):
            missing = self.required - set(row)
            if missing:
                raise ValueError(f"{self.path}:{i+1} missing {sorted(missing)}")
        self.answers = sorted({str(r["answer"]).strip() for r in self.rows})
        self.answer_to_id = answer_to_id or {a: i for i, a in enumerate(self.answers)}

    def _load(self, path, channels):
        im = Image.open(path)
        if channels == 1:
            arr = np.asarray(im.convert("L"), dtype=np.float32) / 255.0
            x = torch.from_numpy(arr)[None]
        else:
            arr = np.asarray(im.convert("RGB").resize((256, 256), Image.Resampling.BILINEAR), dtype=np.float32) / 255.0
            x = torch.from_numpy(arr).permute(2, 0, 1)
        if channels == 1 and tuple(x.shape[-2:]) != (256, 256):
            x = torch.nn.functional.interpolate(x[None], size=(256, 256), mode="bilinear", align_corners=False)[0]
        return (x - 0.5) / 0.5

    def __len__(self): return len(self.rows)
    def __getitem__(self, i):
        r = self.rows[i]
        return {
            "optical_t1": self._load(r["optical_t1"], 3), "sar_t1": self._load(r["sar_t1"], 1),
            "optical_t2": self._load(r["optical_t2"], 3), "sar_t2": self._load(r["sar_t2"], 1),
            "question_ids": torch.tensor(question_ids(r["question"]), dtype=torch.long),
            "answer_id": self.answer_to_id[str(r["answer"]).strip()], "answer": str(r["answer"]).strip(),
        }

def collate(batch):
    m = max(x["question_ids"].numel() for x in batch)
    q = torch.zeros(len(batch), m, dtype=torch.long)
    for i, x in enumerate(batch): q[i, :x["question_ids"].numel()] = x["question_ids"]
    return {k: torch.stack([x[k] for x in batch]) for k in ("optical_t1", "sar_t1", "optical_t2", "sar_t2")} | {
        "question_ids": q, "answer_id": torch.tensor([x["answer_id"] for x in batch])
    }
