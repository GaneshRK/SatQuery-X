"""Internal Held-Out Evaluation Set mimicking ISRO/SAC Cartosat-2S + RISAT SAR structure."""

from __future__ import annotations

from pathlib import Path
from training.datasets.schema import RemoteSensingSample


class HeldoutISRORehearsalSet:
    """Strictly held-out evaluation set constructed from public sensor pairings.

    Never trained on — used exclusively for validation, generalization testing,
    and end-to-end rehearsal against Cartosat-2S optical + RISAT SAR paired data.
    """

    def __init__(self, root_dir: str | Path = "data/heldout_isro_rehearsal") -> None:
        self.root_dir = Path(root_dir)

    def load_evaluation_cases(self) -> list[RemoteSensingSample]:
        return [
            # Mode 1: High-Resolution Optical VQA (Cartosat-2S style)
            RemoteSensingSample(
                sample_id="isro_rehearsal_m1_cartosat",
                task_type="vqa",
                image_paths=["data/samples/cartosat_ahmedabad.tif"],
                sensor_types=["optical"],
                crs="EPSG:32643",
                query="Identify key infrastructure in the western perimeter.",
                ground_truth_answer="Industrial manufacturing plants and transportation interchange.",
                split="heldout_eval",
            ),
            # Mode 2: Optical + SAR Cross-Modal Fusion (Cartosat + RISAT style)
            RemoteSensingSample(
                sample_id="isro_rehearsal_m2_fusion",
                task_type="fusion",
                image_paths=["data/samples/cartosat_coast.tif", "data/samples/risat_coast.tif"],
                sensor_types=["optical", "sar"],
                crs="EPSG:32643",
                query="Perform joint optical and SAR analysis of the coastline and detect surface water boundaries.",
                ground_truth_answer="Coastal zone with confirmed water body extent and low backscatter tidal mudflats.",
                split="heldout_eval",
            ),
            # Mode 3: Bi-temporal Change Detection (Flood Inundation / Urban Growth)
            RemoteSensingSample(
                sample_id="isro_rehearsal_m3_bitemporal",
                task_type="change_detection",
                image_paths=["data/samples/flood_t1_pre.tif", "data/samples/flood_t2_post.tif"],
                sensor_types=["optical", "optical"],
                crs="EPSG:32643",
                query="Detect spatial change and flood inundation boundary.",
                ground_truth_answer="Detected substantial flood inundation covering agricultural lowlands.",
                split="heldout_eval",
            ),
            # Mode 4: Change-Based VQA
            RemoteSensingSample(
                sample_id="isro_rehearsal_m4_change_vqa",
                task_type="change_vqa",
                image_paths=["data/samples/flood_t1_pre.tif", "data/samples/flood_t2_post.tif"],
                sensor_types=["optical", "optical"],
                crs="EPSG:32643",
                query="Has submerged area increased following the heavy monsoon event?",
                ground_truth_answer="Yes, significant water body expansion and agricultural submergence detected.",
                split="heldout_eval",
            ),
        ]
