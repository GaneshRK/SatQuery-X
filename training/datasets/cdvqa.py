"""CDVQA (Change Detection Visual Question Answering) dataset loader."""

from __future__ import annotations

from pathlib import Path
from training.datasets.schema import RemoteSensingSample


class CDVQALoader:
    def __init__(self, root_dir: str | Path = "data/CDVQA") -> None:
        self.root_dir = Path(root_dir)

    def load_samples(self, split: str = "val", limit: int | None = None) -> list[RemoteSensingSample]:
        samples: list[RemoteSensingSample] = []
        catalog = [
            {
                "id": "cdvqa_sample_01",
                "t1": "data/samples/cd_t1_urban.png",
                "t2": "data/samples/cd_t2_urban.png",
                "q": "Has built-up area increased between these two images?",
                "a": "Yes, significant residential and commercial expansion is observed in the eastern section.",
                "boxes": [{"x1": 80.0, "y1": 60.0, "x2": 220.0, "y2": 240.0, "label": "new_built_up"}],
            },
            {
                "id": "cdvqa_sample_02",
                "t1": "data/samples/cd_t1_forest.png",
                "t2": "data/samples/cd_t2_forest.png",
                "q": "What is the primary change in vegetation cover?",
                "a": "Deforestation and clear-cutting along the river boundary.",
                "boxes": [{"x1": 110.0, "y1": 90.0, "x2": 300.0, "y2": 280.0, "label": "vegetation_loss"}],
            },
        ]

        for item in catalog[:limit] if limit else catalog:
            samples.append(
                RemoteSensingSample(
                    sample_id=item["id"],
                    task_type="change_vqa",
                    image_paths=[item["t1"], item["t2"]],
                    sensor_types=["optical", "optical"],
                    query=item["q"],
                    ground_truth_answer=item["a"],
                    ground_truth_boxes=item.get("boxes", []),
                    split=split,
                )
            )
        return samples
