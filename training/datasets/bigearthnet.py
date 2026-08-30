"""BigEarthNet (S1 SAR + S2 Optical) dataset loader and paired text synthesizer."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from training.datasets.schema import RemoteSensingSample


class BigEarthNetLoader:
    def __init__(self, root_dir: str | Path = "data/BigEarthNet") -> None:
        self.root_dir = Path(root_dir)

    def generate_caption_from_labels(self, labels: list[str]) -> str:
        if not labels:
            return "Satellite scene depicting general mixed terrain."
        labels_str = ", ".join(labels)
        return f"Co-registered optical and SAR satellite observation covering land cover classes: {labels_str}."

    def load_samples(self, split: str = "train", limit: int | None = None) -> list[RemoteSensingSample]:
        samples: list[RemoteSensingSample] = []
        # Representative synthetic/mock catalog when raw dataset directory is not yet downloaded
        sample_defs = [
            {
                "id": "ben_s1_s2_001",
                "labels": ["broad-leaved forest", "water courses"],
                "optical": "data/samples/s2_forest_01.tif",
                "sar": "data/samples/s1_forest_01.tif",
            },
            {
                "id": "ben_s1_s2_002",
                "labels": ["continuous urban fabric", "industrial units"],
                "optical": "data/samples/s2_urban_01.tif",
                "sar": "data/samples/s1_urban_01.tif",
            },
            {
                "id": "ben_s1_s2_003",
                "labels": ["non-irrigated arable land", "pastures"],
                "optical": "data/samples/s2_agri_01.tif",
                "sar": "data/samples/s1_agri_01.tif",
            },
        ]

        for s in sample_defs[:limit] if limit else sample_defs:
            samples.append(
                RemoteSensingSample(
                    sample_id=s["id"],
                    task_type="fusion",
                    image_paths=[s["optical"], s["sar"]],
                    sensor_types=["optical", "sar"],
                    crs="EPSG:32632",
                    query="Describe land cover classes in this optical and SAR footprint.",
                    ground_truth_answer=f"Predominant classes: {', '.join(s['labels'])}",
                    ground_truth_caption=self.generate_caption_from_labels(s["labels"]),
                    land_cover_labels=s["labels"],
                    split=split,
                )
            )

        return samples
