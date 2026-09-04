from __future__ import annotations
from typing import Any, Dict, List


class FollowUpGenerator:
    """
    Generates contextually aware, intelligence-grounded follow-up question suggestions
    based on the executed query intent, active Area of Interest, and detected ground changes.
    """

    def generate(
        self, intent: str, aoi_name: str, has_changes: bool = False, has_external: bool = False
    ) -> List[str]:
        suggestions: List[str] = []

        if "urban" in intent or "building" in intent or has_changes:
            suggestions.extend([
                f"How much vegetation was converted to built-up area in {aoi_name}?",
                "Highlight the largest newly developed construction zone.",
                "Compare current built-up density with the 2016 earliest satellite baseline.",
                f"Generate a certified intelligence report for {aoi_name}.",
            ])
        elif "flood" in intent or "water" in intent:
            suggestions.extend([
                "Quantify total flood inundation area in hectares using Sentinel-1 SAR.",
                "Identify which infrastructure corridors intersect the flooded zone.",
                "Compare peak monsoon water extent against dry-season baselines.",
                "Export inundation boundary polygons as GeoJSON.",
            ])
        elif "vegetation" in intent or "agriculture" in intent:
            suggestions.extend([
                f"Show the NDVI time-lapse progression across {aoi_name} from 2018 to 2026.",
                "Did precipitation deficits cause this canopy reduction?",
                "Detect agricultural plot boundaries using multi-spectral NIR bands.",
                "What is the average NDVI health score for this crop sector?",
            ])
        else:
            suggestions.extend([
                f"What changed in {aoi_name} over the last 5 years?",
                "Run bi-temporal change detection on the latest cloud-free overpass.",
                "Show all available Sentinel-2 observations on the timeline.",
                "Generate an executive intelligence summary report.",
            ])

        return suggestions[:4]
