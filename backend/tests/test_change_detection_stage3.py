import json
from pathlib import Path

import numpy as np
from PIL import Image
import torch

from ml.change_detection.model import SiameseChangeNet
from ml.change_detection.dataset import ChangeDetectionManifestDataset


def test_siamese_change_model_shape():
    model = SiameseChangeNet()
    out = model(torch.rand(1, 3, 64, 64), torch.rand(1, 3, 64, 64))
    assert out.shape == (1, 1, 64, 64)


def test_manifest_dataset(tmp_path: Path):
    for name in ("a.png", "b.png", "mask.png"):
        arr = np.zeros((16, 16, 3), dtype=np.uint8) if name != "mask.png" else np.zeros((16, 16), dtype=np.uint8)
        Image.fromarray(arr).save(tmp_path / name)
    manifest = tmp_path / "train.json"
    manifest.write_text(json.dumps([{
        "id": "x",
        "image_t1": "a.png",
        "image_t2": "b.png",
        "mask": "mask.png",
    }]), encoding="utf-8")
    ds = ChangeDetectionManifestDataset(manifest, size=16)
    item = ds[0]
    assert item["t1"].shape == (3, 16, 16)
    assert item["t2"].shape == (3, 16, 16)
    assert item["mask"].shape == (1, 16, 16)
