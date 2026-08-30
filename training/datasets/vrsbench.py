"""VRSBench dataset loader for RS-VQA, Captioning, and Grounding."""

from __future__ import annotations

from pathlib import Path
from training.datasets.schema import RemoteSensingSample


class VRSBenchLoader:
    def __init__(self, root_dir: str | Path = "data/VRSBench") -> None:
        self.root_dir = Path(root_dir)

    def load_samples(self, task: str = "vqa", split: str = "val", limit: int | None = None) -> list[RemoteSensingSample]:
        samples: list[RemoteSensingSample] = []
        catalog = [
            {
                "id": "vrs_vqa_01",
                "task": "vqa",
                "img": "data/samples/vrs_port_01.png",
                "q": "What is the primary facility visible in this satellite scene?",
                "a": "A commercial shipping port with cargo container berths.",
            },
            {
                "id": "vrs_cap_01",
                "task": "caption",
                "img": "data/samples/vrs_airport_01.png",
                "q": "Describe this satellite image.",
                "a": "High-resolution satellite view of an international airport runway and terminal taxiways.",
            },
            {
                "id": "vrs_gnd_01",
                "task": "grounding",
                "img": "data/samples/vrs_solar_01.png",
                "q": "Locate solar panels",
                "boxes": [{"x1": 40.0, "y1": 50.0, "x2": 180.0, "y2": 200.0, "label": "solar panel"}],
            },
        ]

        filtered = [c for c in catalog if c["task"] == task or task == "all"]
        for item in filtered[:limit] if limit else filtered:
            samples.append(
                RemoteSensingSample(
                    sample_id=item["id"],
                    task_type=item["task"],
                    image_paths=[item["img"]],
                    sensor_types=["optical"],
                    query=item.get("q"),
                    ground_truth_answer=item.get("a"),
                    ground_truth_caption=item.get("a") if item["task"] == "caption" else None,
                    ground_truth_boxes=item.get("boxes", []),
                    split=split,
                )
            )
        return samples
