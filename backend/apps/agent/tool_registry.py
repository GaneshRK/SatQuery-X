"""
Evidence-grounded tool registry for SatQuery-X.

Design principles
-----------------
1. Tools operate only on real supplied data.
2. Scientific indices are calculated only when the required spectral bands
   are explicitly available and correctly mapped.
3. No synthetic raster fallback is permitted.
4. No fabricated coordinates, CRS, resolution, dates, sensor names, areas,
   confidence scores, or verification scores are introduced here.
5. Geospatial measurements require real georeferencing information.
6. Satellite search requires an explicit temporal interval.
7. Model/tool outputs are preserved as evidence; this registry does not
   invent conclusions on behalf of downstream reasoning components.
8. The registry is deterministic and framework-agnostic so the Django agent
   executor can invoke tools safely.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from apps.agent.web_research import WebResearchAgent
from apps.geospatial.cv_engine import (
    detect_and_count_structures,
    segment_vegetation,
    segment_water,
)
from apps.geospatial.indices import (
    compute_ndbi,
    compute_nbr,
    compute_ndvi,
    compute_ndwi,
)
from apps.geospatial.math import quantify_mask_area
from apps.satellite.providers import get_satellite_provider


# ---------------------------------------------------------------------------
# Registry contracts
# ---------------------------------------------------------------------------


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, str]
    output_schema: dict[str, str]
    handler: Callable[..., dict[str, Any]]

    timeout_seconds: int = 30
    requires_imagery: bool = True
    task: str = "general"
    required_images: int = 1
    required_relationship: str = "SINGLE_IMAGE"
    model: str = "Deterministic/GIS"
    gpu_requirement: str = "CPU_ONLY"

    provenance_metadata: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """
    Central registry for all executable SatQuery-X tools.

    The registry itself does not decide what a scientific result means.
    Planning and evidence/reasoning layers remain responsible for orchestration
    and interpretation.
    """

    _instance: ToolRegistry | None = None

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._register_default_tools()

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, tool: ToolDefinition) -> None:
        if not tool.name or not tool.name.strip():
            raise ValueError("Tool name cannot be empty.")

        self._tools[tool.name.strip()] = tool

    def get_tool(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "task": tool.task,
                "required_images": tool.required_images,
                "required_relationship": tool.required_relationship,
                "model": tool.model,
                "gpu_requirement": tool.gpu_requirement,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
                "timeout_seconds": tool.timeout_seconds,
                "requires_imagery": tool.requires_imagery,
                "provenance_metadata": dict(tool.provenance_metadata),
            }
            for tool in self._tools.values()
        ]

    def get_tool_manifest(self) -> list[dict[str, Any]]:
        return self.list_tools()

    def find_tools_for_task(
        self,
        task: str,
        image_count: int | None = None,
        relationship: str | None = None,
    ) -> list[ToolDefinition]:
        """
        Discover tools compatible with a requested task and input relationship.
        """

        task_clean = str(task or "").strip().lower()

        if not task_clean:
            return []

        candidates: list[ToolDefinition] = []

        for tool in self._tools.values():
            tool_task = tool.task.lower()
            tool_name = tool.name.lower()

            matches_task = (
                tool_task == task_clean
                or tool_name == task_clean
                or task_clean in tool_task
                or tool_task in task_clean
            )

            if not matches_task:
                continue

            if (
                image_count is not None
                and tool.requires_imagery
                and tool.required_images > image_count
            ):
                continue

            if relationship is not None:
                if tool.required_relationship not in ("NONE", relationship):
                    continue

            candidates.append(tool)

        return candidates

    def can_solve(
        self,
        tool_name: str,
        task: str,
        image_count: int,
        relationship: str = "SINGLE_IMAGE",
    ) -> tuple[bool, str]:
        """
        Validate whether a registered tool is compatible with the supplied
        image configuration.

        `task` is retained in the public contract for planner compatibility.
        Task matching is intentionally permissive here because the planner
        normally resolves the exact tool before execution.
        """

        del task

        tool = self.get_tool(tool_name)

        if tool is None:
            return (
                False,
                f"Tool '{tool_name}' is not registered in ToolRegistry.",
            )

        if tool.requires_imagery and tool.required_images > image_count:
            return (
                False,
                (
                    f"Tool '{tool_name}' requires "
                    f"{tool.required_images} image(s), "
                    f"but only {image_count} provided."
                ),
            )

        if (
            relationship != "NONE"
            and tool.required_relationship
            not in ("NONE", "SINGLE_IMAGE", relationship)
        ):
            return (
                False,
                (
                    f"Tool '{tool_name}' requires relationship "
                    f"'{tool.required_relationship}', "
                    f"but inputs have '{relationship}'."
                ),
            )

        return True, "Tool is compatible with task and input constraints."

    def execute(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        """
        Execute one registered tool.

        Exceptions are converted into a structured error response so the
        executor can persist FAILED execution steps without crashing the
        complete agent pipeline.
        """

        tool = self.get_tool(tool_name)

        if tool is None:
            return {
                "status": "error",
                "tool": tool_name,
                "error": f"Tool '{tool_name}' not found in registry.",
            }

        started = time.perf_counter()

        try:
            result = tool.handler(**kwargs)

            if not isinstance(result, dict):
                result = {
                    "status": "error",
                    "error": (
                        f"Tool '{tool_name}' returned "
                        f"{type(result).__name__}; expected dict."
                    ),
                }

            latency_ms = int((time.perf_counter() - started) * 1000)

            result = dict(result)
            result["latency_ms"] = latency_ms
            result["tool"] = tool_name
            result["status"] = result.get("status", "ok")

            return result

        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)

            return {
                "status": "error",
                "tool": tool_name,
                "error": str(exc),
                "latency_ms": latency_ms,
            }

    # -----------------------------------------------------------------------
    # Tool registration
    # -----------------------------------------------------------------------

    def _register_default_tools(self) -> None:
        self.register(
            ToolDefinition(
                name="calculate_ndvi",
                description=(
                    "Calculate NDVI from explicitly mapped red and NIR "
                    "spectral bands."
                ),
                task="NDVI",
                required_images=1,
                required_relationship="SINGLE_IMAGE",
                model="SpectralIndices/Rasterio",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "raster_array": "numpy.ndarray",
                    "red_band_index": "int",
                    "nir_band_index": "int",
                },
                output_schema={
                    "mean_ndvi": "float",
                    "valid_pixel_count": "int",
                    "index": "str",
                },
                handler=_handle_calculate_ndvi,
            )
        )

        self.register(
            ToolDefinition(
                name="calculate_ndwi",
                description=(
                    "Calculate NDWI from explicitly mapped green and NIR "
                    "spectral bands."
                ),
                task="NDWI",
                required_images=1,
                required_relationship="SINGLE_IMAGE",
                model="SpectralIndices/Rasterio",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "raster_array": "numpy.ndarray",
                    "green_band_index": "int",
                    "nir_band_index": "int",
                },
                output_schema={
                    "mean_ndwi": "float",
                    "valid_pixel_count": "int",
                    "index": "str",
                },
                handler=_handle_calculate_ndwi,
            )
        )

        self.register(
            ToolDefinition(
                name="detect_water",
                description=(
                    "Detect water candidates from the supplied raster using "
                    "the geospatial segmentation engine and preserve "
                    "measured/vector evidence."
                ),
                task="WATER_DETECTION",
                required_images=1,
                required_relationship="SINGLE_IMAGE",
                model="Otsu/OpenCV",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "raster_array": "numpy.ndarray",
                    "bounds_wgs84": "dict",
                    "affine_list": "list",
                    "crs": "str",
                },
                output_schema={
                    "water_features_count": "int",
                    "features": "list",
                },
                handler=_handle_detect_water,
            )
        )

        self.register(
            ToolDefinition(
                name="detect_vegetation",
                description=(
                    "Detect vegetation candidates from the supplied raster "
                    "using the geospatial segmentation engine."
                ),
                task="VEGETATION_ANALYSIS",
                required_images=1,
                required_relationship="SINGLE_IMAGE",
                model="Otsu/OpenCV",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "raster_array": "numpy.ndarray",
                    "bounds_wgs84": "dict",
                    "affine_list": "list",
                    "crs": "str",
                },
                output_schema={
                    "vegetation_features_count": "int",
                    "features": "list",
                },
                handler=_handle_detect_vegetation,
            )
        )

        self.register(
            ToolDefinition(
                name="detect_and_count_structures",
                description=(
                    "Detect candidate structures from supplied imagery and "
                    "return only engine-derived counts/geometries."
                ),
                task="BUILDING_ANALYSIS",
                required_images=1,
                required_relationship="SINGLE_IMAGE",
                model="Morphological/Contours",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "raster_array": "numpy.ndarray",
                    "bounds_wgs84": "dict",
                    "affine_list": "list",
                    "crs": "str",
                },
                output_schema={
                    "candidate_count": "int",
                    "features": "list",
                },
                handler=_handle_detect_structures,
            )
        )

        self.register(
            ToolDefinition(
                name="calculate_area",
                description=(
                    "Calculate mask area only when the mask and real "
                    "georeferencing information are supplied."
                ),
                task="AREA_MEASUREMENT",
                required_images=0,
                required_relationship="NONE",
                model="Shapely/PyProj",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "mask": "numpy.ndarray",
                    "affine_list": "list",
                    "crs": "str",
                },
                output_schema={
                    "area_m2": "float",
                    "area_km2": "float",
                    "valid_pixel_count": "int",
                },
                handler=_handle_calculate_area,
                requires_imagery=False,
            )
        )

        self.register(
            ToolDefinition(
                name="search_satellite_imagery",
                description=(
                    "Search the configured satellite catalog for candidate "
                    "scenes within an explicitly supplied AOI and date range."
                ),
                task="SATELLITE_SEARCH",
                required_images=0,
                required_relationship="NONE",
                model="ConfiguredSatelliteProvider",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "aoi_geometry": "dict",
                    "sensor": "str",
                    "date_start": "str",
                    "date_end": "str",
                    "max_cloud_cover": "float|None",
                },
                output_schema={
                    "candidate_count": "int",
                    "candidates": "list",
                    "provider": "str",
                },
                handler=_handle_search_satellite,
                requires_imagery=False,
            )
        )

        self.register(
            ToolDefinition(
                name="acquire_satellite_imagery",
                description=(
                    "Select a real catalogue candidate from the immediately "
                    "preceding satellite search, download a real provider asset, "
                    "validate it, and attach it to the active query."
                ),
                task="SATELLITE_ACQUISITION",
                required_images=0,
                required_relationship="NONE",
                model="Copernicus/STAC+Rasterio",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "step_outputs": "dict",
                    "query_id": "str",
                    "asset_preference": "str|None",
                },
                output_schema={
                    "status": "str",
                    "scene_id": "str",
                    "asset_id": "str",
                    "image_asset_id": "str",
                    "local_path": "str",
                    "acquisition_date": "str|None",
                    "provenance": "dict",
                },
                handler=_handle_acquire_satellite,
                requires_imagery=False,
            )
        )

        self.register(
            ToolDefinition(
                name="calculate_ndbi",
                description=(
                    "Calculate NDBI from explicitly mapped SWIR and NIR "
                    "spectral bands."
                ),
                task="NDBI",
                required_images=1,
                required_relationship="SINGLE_IMAGE",
                model="SpectralIndices/Rasterio",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "raster_array": "numpy.ndarray",
                    "swir_band_index": "int",
                    "nir_band_index": "int",
                },
                output_schema={
                    "mean_ndbi": "float",
                    "valid_pixel_count": "int",
                    "index": "str",
                },
                handler=_handle_calculate_ndbi,
            )
        )

        self.register(
            ToolDefinition(
                name="calculate_nbr",
                description=(
                    "Calculate NBR from explicitly mapped NIR and SWIR2 "
                    "spectral bands."
                ),
                task="NBR",
                required_images=1,
                required_relationship="SINGLE_IMAGE",
                model="SpectralIndices/Rasterio",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "raster_array": "numpy.ndarray",
                    "nir_band_index": "int",
                    "swir2_band_index": "int",
                },
                output_schema={
                    "mean_nbr": "float",
                    "valid_pixel_count": "int",
                    "index": "str",
                },
                handler=_handle_calculate_nbr,
            )
        )

        self.register(
            ToolDefinition(
                name="detect_change",
                description=(
                    "Detect pixel-level change between two supplied "
                    "co-registered observations. Area is returned only when "
                    "real georeferencing information is available."
                ),
                task="CHANGE_DETECTION",
                required_images=2,
                required_relationship="BI_TEMPORAL",
                model="RasterDifference/Otsu",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "before_array": "numpy.ndarray",
                    "after_array": "numpy.ndarray",
                    "before_affine_list": "list",
                    "after_affine_list": "list",
                    "before_crs": "str",
                    "after_crs": "str",
                },
                output_schema={
                    "change_percentage": "float",
                    "changed_pixel_count": "int",
                    "changed_area_m2": "float|None",
                    "changed_area_hectares": "float|None",
                    "change_mask": "numpy.ndarray",
                },
                handler=_handle_detect_change,
            )
        )

        self.register(
            ToolDefinition(
                name="search_web",
                description=(
                    "Retrieve external corroborating evidence through the "
                    "configured web research agent."
                ),
                task="WEB_RESEARCH",
                required_images=0,
                required_relationship="NONE",
                model="WebResearchAgent",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "query": "str",
                    "aoi_name": "str|None",
                },
                output_schema={
                    "evidence_count": "int",
                    "citations": "list",
                },
                handler=_handle_search_web,
                requires_imagery=False,
            )
        )

        self.register(
            ToolDefinition(
                name="verify_evidence",
                description=(
                    "Compare supplied satellite evidence and external "
                    "evidence without manufacturing a confidence score."
                ),
                task="VERIFY_EVIDENCE",
                required_images=0,
                required_relationship="NONE",
                model="EvidenceEngine",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "satellite_scenes": "list",
                    "external_evidence": "list",
                },
                output_schema={
                    "verification_status": "str",
                    "supporting_evidence_count": "int",
                    "contradicting_evidence_count": "int",
                    "limitations": "list",
                },
                handler=_handle_verify_evidence,
                requires_imagery=False,
            )
        )

        self.register(
            ToolDefinition(
                name="vqa",
                description=(
                    "Remote-sensing visual question answering using the "
                    "configured specialist model adapter."
                ),
                task="VQA",
                required_images=1,
                required_relationship="SINGLE_IMAGE",
                model="GeoChat",
                gpu_requirement="OPTIONAL",
                input_schema={
                    "question": "str",
                    "image_bytes": "list[bytes]|None",
                    "image_paths": "list[str]|None",
                },
                output_schema={
                    "answer": "str",
                    "confidence": "float|None",
                },
                handler=_handle_vqa,
            )
        )

        self.register(
            ToolDefinition(
                name="caption",
                description=(
                    "Remote-sensing scene captioning using the configured "
                    "specialist model adapter."
                ),
                task="CAPTION",
                required_images=1,
                required_relationship="SINGLE_IMAGE",
                model="GeoChat",
                gpu_requirement="OPTIONAL",
                input_schema={
                    "image_bytes": "list[bytes]|None",
                    "image_paths": "list[str]|None",
                },
                output_schema={
                    "caption": "str",
                    "confidence": "float|None",
                },
                handler=_handle_caption,
            )
        )

        self.register(
            ToolDefinition(
                name="grounding",
                description=(
                    "Text-guided visual grounding using the configured "
                    "grounding model."
                ),
                task="GROUNDING",
                required_images=1,
                required_relationship="SINGLE_IMAGE",
                model="GroundingDINO/SAM",
                gpu_requirement="OPTIONAL",
                input_schema={
                    "text_prompt": "str",
                    "image_bytes": "list[bytes]|None",
                    "image_paths": "list[str]|None",
                },
                output_schema={
                    "boxes": "list",
                    "confidence": "float|None",
                },
                handler=_handle_grounding,
            )
        )

        self.register(
            ToolDefinition(
                name="change_detection",
                description=(
                    "Deep-learning bi-temporal change detection using the "
                    "configured ChangeFormer adapter."
                ),
                task="CHANGE_DETECTION",
                required_images=2,
                required_relationship="BI_TEMPORAL",
                model="ChangeFormer",
                gpu_requirement="OPTIONAL",
                input_schema={
                    "image_bytes": "list[bytes]|None",
                    "image_paths": "list[str]|None",
                },
                output_schema={
                    "answer": "str|None",
                    "boxes": "list",
                    "change_mask": "bytes|numpy.ndarray|None",
                    "confidence": "float|None",
                },
                handler=_handle_change_detection,
            )
        )

        self.register(
            ToolDefinition(
                name="change_vqa",
                description=(
                    "Answer a change-related question using two supplied "
                    "observations and an actual change mask when available."
                ),
                task="CHANGE_VQA",
                required_images=2,
                required_relationship="BI_TEMPORAL",
                model="SupervisedChangeVQA",
                gpu_requirement="OPTIONAL",
                input_schema={
                    "question": "str",
                    "change_mask": "bytes|numpy.ndarray|None",
                    "image_bytes": "list[bytes]|None",
                    "image_paths": "list[str]|None",
                },
                output_schema={
                    "answer": "str",
                    "confidence": "float|None",
                },
                handler=_handle_change_vqa,
            )
        )

        self.register(
            ToolDefinition(
                name="optical_sar_fusion",
                description=(
                    "Cross-modal optical/SAR analysis using two explicitly "
                    "identified modality inputs."
                ),
                task="OPTICAL_SAR_ANALYSIS",
                required_images=2,
                required_relationship="OPTICAL_SAR_PAIR",
                model="OpticalSARFusion",
                gpu_requirement="OPTIONAL",
                input_schema={
                    "image_bytes": "list[bytes]|None",
                    "image_paths": "list[str]|None",
                    "optical_index": "int",
                    "sar_index": "int",
                },
                output_schema={
                    "answer": "str|None",
                    "confidence": "float|None",
                    "boxes": "list",
                },
                handler=_handle_optical_sar,
            )
        )

        self.register(
            ToolDefinition(
                name="coregister_temporal_optical_sar",
                description=(
                    "Pair real Optical/SAR observations by acquisition time and "
                    "reproject each SAR observation onto its paired optical grid."
                ),
                task="TEMPORAL_COREGISTRATION",
                required_images=4,
                required_relationship="TEMPORAL_CROSS_MODAL",
                model="Rasterio/CRS-aware temporal pairing",
                gpu_requirement="CPU_ONLY",
                input_schema={"image_paths": "list[str]", "image_metadata": "list[dict]", "max_pair_delta_hours": "float"},
                output_schema={"status": "str", "ordered_paths": "list[str]", "pairs": "list", "stream_order": "list[str]"},
                handler=_handle_coregister_temporal_optical_sar,
                requires_imagery=True,
            )
        )

        self.register(
            ToolDefinition(
                name="temporal_optical_sar",
                description=(
                    "Native four-stream temporal Optical/SAR reasoning using two "
                    "explicitly identified optical and two SAR observations."
                ),
                task="TEMPORAL_OPTICAL_SAR",
                required_images=4,
                required_relationship="TEMPORAL_CROSS_MODAL",
                model="TemporalOpticalSAR",
                gpu_requirement="OPTIONAL",
                input_schema={"image_bytes": "list[bytes]|None", "image_paths": "list[str]|None", "question": "str"},
                output_schema={"answer": "str", "confidence": "float|None"},
                handler=_handle_temporal_optical_sar,
            )
        )

        self.register(
            ToolDefinition(
                name="geo_metadata",
                description=(
                    "Extract actual raster dimensions, band metadata, CRS, "
                    "bounds, modality and georeferencing state."
                ),
                task="GEO_METADATA",
                required_images=1,
                required_relationship="SINGLE_IMAGE",
                model="GDAL/Rasterio",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "image_bytes": "bytes",
                    "filename": "str",
                },
                output_schema={
                    "width": "int",
                    "height": "int",
                    "band_count": "int",
                    "crs": "str|None",
                    "resolution_m": "float|None",
                    "bounds_wgs84": "dict|None",
                    "is_georeferenced": "bool",
                },
                handler=_handle_geo_metadata,
            )
        )

        self.register(
            ToolDefinition(
                name="histogram_analysis",
                description=(
                    "Compute descriptive statistics from the supplied raster "
                    "bands without interpreting them as a specific sensor."
                ),
                task="HISTOGRAM_ANALYSIS",
                required_images=1,
                required_relationship="SINGLE_IMAGE",
                model="NumPy/Rasterio",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "raster_array": "numpy.ndarray",
                },
                output_schema={
                    "bands_analyzed": "int",
                    "statistics": "list",
                },
                handler=_handle_histogram_analysis,
            )
        )

        self.register(
            ToolDefinition(
                name="coregistration",
                description=(
                    "Check spatial overlap between two observations using "
                    "their actual bounds and, when available, CRS metadata."
                ),
                task="COREGISTRATION",
                required_images=2,
                required_relationship="BI_TEMPORAL",
                model="Rasterio/Affine",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "bounds_a": "dict",
                    "bounds_b": "dict",
                    "crs_a": "str|None",
                    "crs_b": "str|None",
                },
                output_schema={
                    "coregistration_valid": "bool",
                    "overlap": "dict|None",
                    "reason": "str",
                },
                handler=_handle_coregistration,
                requires_imagery=False,
            )
        )

        self.register(
            ToolDefinition(
                name="spatial_relation",
                description=(
                    "Determine the geometric relationship between two supplied "
                    "AOIs using actual geometry."
                ),
                task="SPATIAL_RELATION",
                required_images=0,
                required_relationship="NONE",
                model="Shapely",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "aoi_a": "dict",
                    "aoi_b": "dict",
                },
                output_schema={
                    "relation": "str",
                    "spatial_match": "bool",
                },
                handler=_handle_spatial_relation,
                requires_imagery=False,
            )
        )

        self.register(
            ToolDefinition(
                name="temporal_comparison",
                description=(
                    "Compare supplied temporal statistics without inventing "
                    "thresholds or consistency scores."
                ),
                task="TEMPORAL_COMPARISON",
                required_images=0,
                required_relationship="NONE",
                model="TemporalConsistency",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "t1_stats": "dict",
                    "t2_stats": "dict",
                },
                output_schema={
                    "comparison_available": "bool",
                    "deltas": "dict",
                    "limitations": "list",
                },
                handler=_handle_temporal_comparison,
                requires_imagery=False,
            )
        )

        self.register(
            ToolDefinition(
                name="report_generation",
                description=(
                    "Delegate report generation to the configured report "
                    "service when one is available."
                ),
                task="REPORT_GENERATION",
                required_images=0,
                required_relationship="NONE",
                model="ConfiguredReportService",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "session_id": "str",
                    "query_id": "str",
                },
                output_schema={
                    "status": "str",
                    "report_type": "str|None",
                    "artifact": "dict|None",
                },
                handler=_handle_report_generation,
                requires_imagery=False,
            )
        )

        self.register(
            ToolDefinition(
                name="evidence_export",
                description=(
                    "Export already-derived GeoJSON features without "
                    "inventing geometries."
                ),
                task="EVIDENCE_EXPORT",
                required_images=0,
                required_relationship="NONE",
                model="GeoJSONEngine",
                gpu_requirement="CPU_ONLY",
                input_schema={
                    "features": "list",
                },
                output_schema={
                    "feature_count": "int",
                    "geojson": "dict",
                },
                handler=_handle_evidence_export,
                requires_imagery=False,
            )
        )

        self.register(
            ToolDefinition(
                name="remoteclip_semantic_retrieval",
                description=(
                    "Score explicitly supplied text queries against an image "
                    "using RemoteCLIP. No default semantic classes are added."
                ),
                task="SEMANTIC_RETRIEVAL",
                required_images=1,
                required_relationship="SINGLE_IMAGE",
                model="RemoteCLIP",
                gpu_requirement="OPTIONAL",
                input_schema={
                    "text_queries": "list[str]",
                    "image_bytes": "list[bytes]|None",
                    "image_paths": "list[str]|None",
                },
                output_schema={
                    "similarity_scores": "dict",
                    "ranked_classes": "list",
                },
                handler=_handle_remoteclip_retrieval,
            )
        )


# ===========================================================================
# Generic validation helpers
# ===========================================================================


def _require_array(
    value: Any,
    name: str,
    *,
    ndim: int | None = None,
) -> np.ndarray:
    if value is None:
        raise ValueError(f"'{name}' is required.")

    array = np.asarray(value)

    if array.size == 0:
        raise ValueError(f"'{name}' is empty.")

    if ndim is not None and array.ndim != ndim:
        raise ValueError(
            f"'{name}' must have {ndim} dimensions; "
            f"received {array.ndim}."
        )

    if not np.issubdtype(array.dtype, np.number):
        raise ValueError(
            f"'{name}' must contain numeric raster values."
        )

    return array


def _require_band_index(
    raster_array: np.ndarray,
    band_index: int,
    name: str,
) -> int:
    array = np.asarray(raster_array)

    if array.ndim != 3:
        raise ValueError(
            "Spectral index tools require a 3-D HxWxBands raster array."
        )

    try:
        index = int(band_index)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"'{name}' must be an integer band index."
        ) from exc

    if index < 0 or index >= array.shape[2]:
        raise ValueError(
            f"'{name}'={index} is outside the available "
            f"band range 0..{array.shape[2] - 1}."
        )

    return index


def _extract_band(
    raster_array: np.ndarray,
    band_index: int,
    name: str,
) -> np.ndarray:
    index = _require_band_index(raster_array, band_index, name)
    return np.asarray(raster_array[:, :, index], dtype=np.float64)


def _finite_mask(*arrays: np.ndarray) -> np.ndarray:
    mask: np.ndarray | None = None

    for array in arrays:
        current = np.isfinite(array)

        if mask is None:
            mask = current
        else:
            mask &= current

    if mask is None:
        raise ValueError("No arrays were supplied.")

    return mask


def _clean_index_result(
    values: np.ndarray,
    *,
    index_name: str,
    valid_mask: np.ndarray,
) -> dict[str, Any]:
    valid_values = values[valid_mask]

    if valid_values.size == 0:
        raise ValueError(
            f"No finite pixels were available for {index_name}."
        )

    return {
        f"mean_{index_name.lower()}": float(np.mean(valid_values)),
        "valid_pixel_count": int(valid_values.size),
        "index": index_name,
        "status": "ok",
    }


def _image_inputs(
    image_bytes: Sequence[bytes] | None,
    image_paths: Sequence[str] | None,
    minimum: int,
) -> tuple[list[bytes], list[str]]:
    bytes_list = list(image_bytes or [])
    paths_list = list(image_paths or [])

    total = max(len(bytes_list), len(paths_list))

    if total < minimum:
        raise ValueError(
            f"At least {minimum} image input(s) are required."
        )

    return bytes_list, paths_list


def _select_image_input(
    image_bytes: Sequence[bytes] | None,
    image_paths: Sequence[str] | None,
    index: int,
) -> bytes | str:
    bytes_list = list(image_bytes or [])
    paths_list = list(image_paths or [])

    if index < len(bytes_list) and bytes_list[index]:
        return bytes_list[index]

    if index < len(paths_list) and paths_list[index]:
        return paths_list[index]

    raise ValueError(
        f"No usable image input exists at index {index}."
    )


def _normalize_bounds(
    bounds: Mapping[str, Any] | None,
) -> dict[str, float] | None:
    if not bounds:
        return None

    aliases = {
        "west": ("west", "minx", "xmin", "left"),
        "east": ("east", "maxx", "xmax", "right"),
        "south": ("south", "miny", "ymin", "bottom"),
        "north": ("north", "maxy", "ymax", "top"),
    }

    normalized: dict[str, float] = {}

    for canonical, keys in aliases.items():
        value = None

        for key in keys:
            if key in bounds and bounds[key] is not None:
                value = bounds[key]
                break

        if value is None:
            return None

        try:
            normalized[canonical] = float(value)
        except (TypeError, ValueError):
            return None

    if normalized["east"] <= normalized["west"]:
        return None

    if normalized["north"] <= normalized["south"]:
        return None

    return normalized


def _intersection(
    bounds_a: Mapping[str, Any] | None,
    bounds_b: Mapping[str, Any] | None,
) -> dict[str, float] | None:
    a = _normalize_bounds(bounds_a)
    b = _normalize_bounds(bounds_b)

    if a is None or b is None:
        return None

    west = max(a["west"], b["west"])
    east = min(a["east"], b["east"])
    south = max(a["south"], b["south"])
    north = min(a["north"], b["north"])

    if east <= west or north <= south:
        return None

    return {
        "west": west,
        "east": east,
        "south": south,
        "north": north,
    }


def _json_safe(value: Any) -> Any:
    """
    Convert common NumPy values to JSON-compatible values.

    Arrays are intentionally not converted wholesale because masks and large
    raster outputs should remain binary/numeric artifacts handled by the
    executor rather than being embedded in database JSON.
    """

    if isinstance(value, np.generic):
        return value.item()

    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]

    if isinstance(value, np.ndarray):
        return {
            "type": "numpy.ndarray",
            "shape": list(value.shape),
            "dtype": str(value.dtype),
        }

    return value


# ===========================================================================
# Spectral index handlers
# ===========================================================================


def _handle_calculate_ndvi(
    raster_array: np.ndarray,
    red_band_index: int,
    nir_band_index: int,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    array = _require_array(
        raster_array,
        "raster_array",
        ndim=3,
    )

    red = _extract_band(
        array,
        red_band_index,
        "red_band_index",
    )

    nir = _extract_band(
        array,
        nir_band_index,
        "nir_band_index",
    )

    valid = _finite_mask(red, nir)

    if not np.any(valid):
        raise ValueError(
            "No finite red/NIR pixel pairs are available for NDVI."
        )

    ndvi = np.full(red.shape, np.nan, dtype=np.float64)

    with np.errstate(divide="ignore", invalid="ignore"):
        denominator = nir + red
        valid_denominator = valid & (denominator != 0)

        ndvi[valid_denominator] = (
            compute_ndvi(
                red[valid_denominator],
                nir[valid_denominator],
            )
        )

    final_valid = np.isfinite(ndvi)

    result = _clean_index_result(
        ndvi,
        index_name="NDVI",
        valid_mask=final_valid,
    )

    result["red_band_index"] = int(red_band_index)
    result["nir_band_index"] = int(nir_band_index)

    return result


def _handle_calculate_ndwi(
    raster_array: np.ndarray,
    green_band_index: int,
    nir_band_index: int,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    array = _require_array(
        raster_array,
        "raster_array",
        ndim=3,
    )

    green = _extract_band(
        array,
        green_band_index,
        "green_band_index",
    )

    nir = _extract_band(
        array,
        nir_band_index,
        "nir_band_index",
    )

    valid = _finite_mask(green, nir)

    if not np.any(valid):
        raise ValueError(
            "No finite green/NIR pixel pairs are available for NDWI."
        )

    ndwi = np.full(green.shape, np.nan, dtype=np.float64)

    with np.errstate(divide="ignore", invalid="ignore"):
        denominator = green + nir
        valid_denominator = valid & (denominator != 0)

        ndwi[valid_denominator] = compute_ndwi(
            green[valid_denominator],
            nir[valid_denominator],
        )

    final_valid = np.isfinite(ndwi)

    result = _clean_index_result(
        ndwi,
        index_name="NDWI",
        valid_mask=final_valid,
    )

    result["green_band_index"] = int(green_band_index)
    result["nir_band_index"] = int(nir_band_index)

    return result


def _handle_calculate_ndbi(
    raster_array: np.ndarray,
    swir_band_index: int,
    nir_band_index: int,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    array = _require_array(
        raster_array,
        "raster_array",
        ndim=3,
    )

    swir = _extract_band(
        array,
        swir_band_index,
        "swir_band_index",
    )

    nir = _extract_band(
        array,
        nir_band_index,
        "nir_band_index",
    )

    valid = _finite_mask(swir, nir)

    if not np.any(valid):
        raise ValueError(
            "No finite SWIR/NIR pixel pairs are available for NDBI."
        )

    ndbi = np.full(swir.shape, np.nan, dtype=np.float64)

    with np.errstate(divide="ignore", invalid="ignore"):
        denominator = swir + nir
        valid_denominator = valid & (denominator != 0)

        ndbi[valid_denominator] = compute_ndbi(
            swir[valid_denominator],
            nir[valid_denominator],
        )

    final_valid = np.isfinite(ndbi)

    result = _clean_index_result(
        ndbi,
        index_name="NDBI",
        valid_mask=final_valid,
    )

    result["swir_band_index"] = int(swir_band_index)
    result["nir_band_index"] = int(nir_band_index)

    return result


def _handle_calculate_nbr(
    raster_array: np.ndarray,
    nir_band_index: int,
    swir2_band_index: int,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    array = _require_array(
        raster_array,
        "raster_array",
        ndim=3,
    )

    nir = _extract_band(
        array,
        nir_band_index,
        "nir_band_index",
    )

    swir2 = _extract_band(
        array,
        swir2_band_index,
        "swir2_band_index",
    )

    valid = _finite_mask(nir, swir2)

    if not np.any(valid):
        raise ValueError(
            "No finite NIR/SWIR2 pixel pairs are available for NBR."
        )

    nbr = np.full(nir.shape, np.nan, dtype=np.float64)

    with np.errstate(divide="ignore", invalid="ignore"):
        denominator = nir + swir2
        valid_denominator = valid & (denominator != 0)

        nbr[valid_denominator] = compute_nbr(
            nir[valid_denominator],
            swir2[valid_denominator],
        )

    final_valid = np.isfinite(nbr)

    result = _clean_index_result(
        nbr,
        index_name="NBR",
        valid_mask=final_valid,
    )

    result["nir_band_index"] = int(nir_band_index)
    result["swir2_band_index"] = int(swir2_band_index)

    return result


# ===========================================================================
# Segmentation handlers
# ===========================================================================


def _handle_detect_water(
    raster_array: np.ndarray,
    bounds_wgs84: dict[str, float] | None = None,
    affine_list: list[float] | None = None,
    crs: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    array = _require_array(
        raster_array,
        "raster_array",
    )

    features = segment_water(
        array,
        bounds_wgs84,
        affine_list,
        crs,
    )

    serialized_features = [
        {
            "label": getattr(feature, "label", None),
            "area_km2": _optional_float(
                getattr(feature, "area_km2", None)
            ),
            "confidence": _optional_float(
                getattr(feature, "confidence", None)
            ),
            "geometry": getattr(
                feature,
                "geojson_geometry",
                None,
            ),
        }
        for feature in features
    ]

    result: dict[str, Any] = {
        "water_features_count": len(features),
        "features": serialized_features,
        "status": "ok",
    }

    total_area = _sum_actual_numeric_field(
        serialized_features,
        "area_km2",
    )

    if total_area is not None:
        result["total_water_km2"] = total_area

    return result


def _handle_detect_vegetation(
    raster_array: np.ndarray,
    bounds_wgs84: dict[str, float] | None = None,
    affine_list: list[float] | None = None,
    crs: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    array = _require_array(
        raster_array,
        "raster_array",
    )

    features = segment_vegetation(
        array,
        bounds_wgs84,
        affine_list,
        crs,
    )

    serialized_features = [
        {
            "label": getattr(feature, "label", None),
            "area_km2": _optional_float(
                getattr(feature, "area_km2", None)
            ),
            "confidence": _optional_float(
                getattr(feature, "confidence", None)
            ),
            "geometry": getattr(
                feature,
                "geojson_geometry",
                None,
            ),
        }
        for feature in features
    ]

    result: dict[str, Any] = {
        "vegetation_features_count": len(features),
        "features": serialized_features,
        "status": "ok",
    }

    total_area = _sum_actual_numeric_field(
        serialized_features,
        "area_km2",
    )

    if total_area is not None:
        result["total_veg_km2"] = total_area

    return result


def _handle_detect_structures(
    raster_array: np.ndarray,
    bounds_wgs84: dict[str, float] | None = None,
    affine_list: list[float] | None = None,
    crs: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    array = _require_array(
        raster_array,
        "raster_array",
    )

    count, features = detect_and_count_structures(
        array,
        bounds_wgs84,
        affine_list,
        crs,
    )

    serialized_features = [
        {
            "label": getattr(feature, "label", None),
            "area_km2": _optional_float(
                getattr(feature, "area_km2", None)
            ),
            "confidence": _optional_float(
                getattr(feature, "confidence", None)
            ),
            "geometry": getattr(
                feature,
                "geojson_geometry",
                None,
            ),
        }
        for feature in features
    ]

    result: dict[str, Any] = {
        "candidate_count": int(count),
        "features": serialized_features,
        "status": "ok",
    }

    total_area = _sum_actual_numeric_field(
        serialized_features,
        "area_km2",
    )

    if total_area is not None:
        result["total_structure_km2"] = total_area

    return result


# ===========================================================================
# Geospatial measurement
# ===========================================================================


def _handle_calculate_area(
    mask: np.ndarray,
    affine_list: list[float] | None = None,
    crs: str | None = None,
    bounds_wgs84: dict[str, float] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    if affine_list is None:
        raise ValueError(
            "Cannot calculate geographic area without a real affine transform."
        )

    if not crs:
        raise ValueError(
            "Cannot calculate geographic area without a real CRS."
        )

    mask_array = np.asarray(mask)

    if mask_array.size == 0:
        raise ValueError("Area mask is empty.")

    if mask_array.ndim != 2:
        raise ValueError(
            "Area calculation requires a 2-D binary/boolean mask."
        )

    result = quantify_mask_area(
        mask_array,
        affine_list,
        crs,
        bounds_wgs84,
    )

    if not isinstance(result, dict):
        raise ValueError(
            "Area calculation engine returned an invalid result."
        )

    return _sanitize_numeric_mapping(result)


# ===========================================================================
# Satellite catalog search
# ===========================================================================


def _handle_search_satellite(
    aoi_geometry: dict[str, Any],
    sensor: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    max_cloud_cover: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    if not aoi_geometry:
        raise ValueError(
            "Satellite search requires an explicit AOI geometry."
        )

    if not sensor or not str(sensor).strip():
        raise ValueError(
            "Satellite search requires an explicit sensor/collection."
        )

    if not date_start or not date_end:
        raise ValueError(
            "Satellite search requires explicit date_start and date_end. "
            "The tool will not invent a temporal search window."
        )

    if str(date_start) > str(date_end):
        raise ValueError(
            "date_start cannot be later than date_end."
        )

    provider = get_satellite_provider()

    search_kwargs: dict[str, Any] = {}

    if max_cloud_cover is not None:
        search_kwargs["max_cloud_cover"] = float(max_cloud_cover)

    candidates = provider.search_scenes(
        aoi_geometry,
        date_start,
        date_end,
        sensor,
        **search_kwargs,
    )

    serialized_candidates: list[dict[str, Any]] = []

    for candidate in candidates:
        serialized_candidates.append(
            {
                "stac_item_id": getattr(
                    candidate,
                    "stac_item_id",
                    None,
                ),
                "acquisition_date": getattr(
                    candidate,
                    "acquisition_date",
                    None,
                ),
                "cloud_cover_pct": _optional_float(
                    getattr(
                        candidate,
                        "cloud_cover_pct",
                        None,
                    )
                ),
                "collection": getattr(
                    candidate,
                    "collection",
                    None,
                ),
                "sensor": getattr(candidate, "sensor", None),
                "platform": getattr(candidate, "platform", None),
                "mission": getattr(candidate, "mission", None),
                "instrument": getattr(candidate, "instrument", None),
                "footprint_geom": getattr(candidate, "footprint_geom", None),
                "bbox": getattr(candidate, "bbox", None),
                "stac_item_url": getattr(candidate, "stac_item_url", None),
                "thumbnail_url": getattr(candidate, "thumbnail_url", None),
                "assets_summary": getattr(candidate, "assets_summary", {}) or {},
                "metadata": getattr(candidate, "metadata", {}) or {},
            }
        )

    return {
        "candidate_count": len(serialized_candidates),
        "provider": getattr(provider, "name", None),
        "sensor_requested": sensor,
        "date_start": date_start,
        "date_end": date_end,
        "max_cloud_cover": (
            float(max_cloud_cover)
            if max_cloud_cover is not None
            else None
        ),
        "candidates": serialized_candidates,
        "status": "ok",
    }


# ===========================================================================
# Agentic satellite acquisition
# ===========================================================================


def _handle_acquire_satellite(
    step_outputs: dict[str, Any] | None = None,
    query_id: str | None = None,
    asset_preference: str | None = None,
    required_images: int = 1,
    **kwargs: Any,
) -> dict[str, Any]:
    """Acquire one real asset selected from a prior real catalogue search."""
    del kwargs
    if not query_id:
        raise ValueError("query_id is required for satellite acquisition.")
    outputs = step_outputs if isinstance(step_outputs, dict) else {}
    search = None
    for value in outputs.values():
        if isinstance(value, dict) and value.get("candidates"):
            search = value
    if not search:
        raise ValueError("Satellite acquisition requires a preceding successful catalogue search.")
    candidates = search.get("candidates") or []
    if not candidates:
        return {"status": "insufficient_evidence", "reason": "The real catalogue returned no candidate scenes."}
    preferred = str(asset_preference or "").strip().lower()
    requested_count = max(1, int(required_images or 1))
    usable = [item for item in candidates if isinstance(item, dict) and item.get("stac_item_id")]
    usable.sort(key=lambda x: str(x.get("acquisition_date") or ""))
    def _candidate_modality(item):
        text = f"{item.get('sensor','')} {item.get('platform','')} {item.get('mission','')}".lower()
        return "sar" if any(k in text for k in ("sar", "sentinel-1", "radar")) else ("optical" if any(k in text for k in ("optical", "multispectral", "sentinel-2", "landsat")) else "unknown")
    if requested_count >= 4:
        # For native temporal Optical/SAR, require an explicit optical+SAR pair
        # at each of two distinct acquisition dates. Never fabricate a pairing.
        by_date = {}
        for item in usable:
            date_key = str(item.get("acquisition_date") or "").split("T")[0]
            by_date.setdefault(date_key, {}).setdefault(_candidate_modality(item), []).append(item)
        complete_dates = [(d, grp) for d, grp in sorted(by_date.items()) if grp.get("optical") and grp.get("sar")]
        if len(complete_dates) < 2:
            return {"status": "insufficient_evidence", "reason": "Four-stream temporal Optical/SAR analysis requires two distinct dates, each with an explicit optical and SAR observation.", "complete_date_count": len(complete_dates)}
        first_date, first_grp = complete_dates[0]; last_date, last_grp = complete_dates[-1]
        selected_candidates = [first_grp["optical"][-1], first_grp["sar"][-1], last_grp["optical"][-1], last_grp["sar"][-1]]
    elif requested_count >= 2:
        if len(usable) < 2:
            return {"status": "insufficient_evidence", "reason": "At least two distinct catalogue observations are required for bi-temporal analysis.", "candidate_count": len(usable)}
        selected_candidates = [usable[0], usable[-1]]
    else:
        selected_candidates = [usable[-1]]
    if preferred:
        for idx, item in enumerate(selected_candidates):
            assets = item.get("assets_summary") or {}
            match = next((k for k in assets if preferred in str(k).lower()), None)
            if match:
                selected_candidates[idx] = item

    from apps.satellite.models import SatelliteScene, SatelliteAsset
    from apps.satellite.services.asset_ingestion import download_scene_asset
    from django.utils.dateparse import parse_datetime
    from datetime import datetime, timezone as dt_timezone
    from apps.queries.models import Query
    from apps.imagery.models import ImageAsset
    from django.core.files import File
    from pathlib import Path

    provider_name = "copernicus"
    query = Query.objects.get(id=query_id)
    acquired = []
    for candidate in selected_candidates:
        collection = str(candidate.get("collection") or "").strip()
        sensor_raw = str(candidate.get("sensor") or search.get("sensor_requested") or "").upper()
        sensor = "SAR" if "1" in sensor_raw or "SAR" in sensor_raw else "OPTICAL"
        acquisition = candidate.get("acquisition_date")
        if not acquisition:
            raise ValueError("Selected catalogue candidate has no acquisition date.")
        dt = parse_datetime(str(acquisition))
        if dt is None:
            try:
                dt = datetime.fromisoformat(str(acquisition).replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Selected catalogue candidate has an invalid acquisition timestamp.") from exc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_timezone.utc)
        scene, _ = SatelliteScene.objects.update_or_create(
            provider=provider_name, collection=collection, external_id=str(candidate["stac_item_id"]),
            defaults={"acquisition_datetime": dt, "cloud_cover": candidate.get("cloud_cover_pct"), "geometry": candidate.get("footprint_geom"), "bbox": candidate.get("bbox"), "platform": str(candidate.get("platform") or ""), "mission": str(candidate.get("mission") or ""), "instrument": str(candidate.get("instrument") or ""), "sensor": sensor, "modality": "SAR" if sensor == "SAR" else "MULTISPECTRAL", "stac_item_url": str(candidate.get("stac_item_url") or ""), "thumbnail_url": str(candidate.get("thumbnail_url") or ""), "metadata": candidate.get("metadata") or {}, "availability_status": "CATALOGUED"})
        assets = candidate.get("assets_summary") or {}
        if not isinstance(assets, dict) or not assets:
            raise ValueError("Selected catalogue candidate has no downloadable asset references.")
        keys = list(assets)
        priority = ["visual", "B04", "B02", "VV", "VH", "data"]
        selected_key = next((k for k in priority if k in assets), keys[0])
        if preferred:
            selected_key = next((k for k in keys if preferred in str(k).lower()), selected_key)
        raw = assets[selected_key]
        href = raw.get("href") if isinstance(raw, dict) else None
        if not href:
            raise ValueError(f"Catalogue asset '{selected_key}' has no downloadable href.")
        sat_asset, _ = SatelliteAsset.objects.update_or_create(scene=scene, asset_key=str(selected_key), defaults={"href": str(href), "asset_type": str((raw or {}).get("type", "")) if isinstance(raw, dict) else "", "metadata": raw if isinstance(raw, dict) else {}})
        download = download_scene_asset(scene, sat_asset)
        path = Path(str(download["local_path"]))
        if not path.is_file():
            raise RuntimeError("Downloaded satellite asset is not a local file.")
        with path.open("rb") as fh:
            image_asset = ImageAsset(session=query.session, original_filename=path.name, content_type="application/octet-stream", file_format="GEOTIFF" if path.suffix.lower() in {".tif", ".tiff"} else "TIFF", sensor="SENTINEL-1" if sensor == "SAR" else "SENTINEL-2", modality="SAR" if sensor == "SAR" else "MULTISPECTRAL", acquisition_date=dt.date(), processing_status="VALIDATED")
            image_asset.file.save(path.name, File(fh), save=True)
        query.input_assets.add(image_asset)
        acquired.append({"scene_id": str(scene.id), "asset_id": str(sat_asset.id), "image_asset_id": str(image_asset.id), "local_path": str(image_asset.file.path) if hasattr(image_asset.file, "path") else str(path), "acquisition_date": dt.isoformat(), "selected_asset_key": str(selected_key), "provenance": {"provider": provider_name, "stac_item_id": str(candidate["stac_item_id"]), "collection": collection, "sha256": download.get("sha256")}})
    if acquired:
        query.image = ImageAsset.objects.get(id=acquired[-1]["image_asset_id"])
        query.save(update_fields=["image"])
    return {"status": "completed", "count": len(acquired), "images": acquired, "image_paths": [x["local_path"] for x in acquired], "image_asset_ids": [x["image_asset_id"] for x in acquired]}

# ===========================================================================
# Change detection
# ===========================================================================


def _handle_detect_change(
    before_array: np.ndarray,
    after_array: np.ndarray,
    before_affine_list: list[float] | None = None,
    after_affine_list: list[float] | None = None,
    before_crs: str | None = None,
    after_crs: str | None = None,
    change_threshold: float | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    before = _require_array(
        before_array,
        "before_array",
    )

    after = _require_array(
        after_array,
        "after_array",
    )

    if before.shape != after.shape:
        raise ValueError(
            "Before and after rasters must have identical dimensions "
            "for deterministic pixel-wise differencing. "
            "Use coregistration/resampling before this tool."
        )

    if (
        before.ndim != 2
        and before.ndim != 3
    ):
        raise ValueError(
            "Change detection expects 2-D or 3-D raster arrays."
        )

    if (
        before_affine_list is not None
        and after_affine_list is not None
        and list(before_affine_list) != list(after_affine_list)
    ):
        raise ValueError(
            "Before and after affine transforms differ. "
            "Coregister the observations before pixel-wise change detection."
        )

    if (
        before_crs
        and after_crs
        and str(before_crs) != str(after_crs)
    ):
        raise ValueError(
            "Before and after CRS differ. "
            "Reproject/coregister the observations before pixel-wise "
            "change detection."
        )

    before_float = before.astype(np.float64)
    after_float = after.astype(np.float64)

    valid = _finite_mask(
        before_float,
        after_float,
    )

    if not np.any(valid):
        raise ValueError(
            "No valid overlapping pixels are available for change detection."
        )

    delta = np.abs(after_float - before_float)

    if delta.ndim == 3:
        delta_scalar = np.nanmean(delta, axis=2)
        valid_scalar = np.all(valid, axis=2)
    else:
        delta_scalar = delta
        valid_scalar = valid

    valid_values = delta_scalar[valid_scalar]

    if valid_values.size == 0:
        raise ValueError(
            "No valid scalar change values are available."
        )

    if change_threshold is None:
        raise ValueError(
            "A change threshold must be explicitly supplied. "
            "This tool does not invent a scientific threshold."
        )

    threshold = float(change_threshold)

    if not np.isfinite(threshold) or threshold < 0:
        raise ValueError(
            "change_threshold must be a finite non-negative value."
        )

    change_mask = np.zeros(
        delta_scalar.shape,
        dtype=np.uint8,
    )

    change_mask[
        valid_scalar & (delta_scalar > threshold)
    ] = 1

    valid_pixel_count = int(np.count_nonzero(valid_scalar))
    changed_pixel_count = int(np.count_nonzero(change_mask))

    if valid_pixel_count == 0:
        raise ValueError(
            "No valid pixels remain after change-mask construction."
        )

    change_percentage = (
        changed_pixel_count / valid_pixel_count
    ) * 100.0

    result: dict[str, Any] = {
        "changed_pixel_count": changed_pixel_count,
        "valid_pixel_count": valid_pixel_count,
        "change_percentage": float(change_percentage),
        "change_threshold": threshold,
        "spectral_delta_mean": float(np.mean(valid_values)),
        "spectral_delta_std": float(np.std(valid_values)),
        "change_mask": change_mask,
        "status": "ok",
    }

    if (
        before_affine_list is not None
        and before_crs
    ):
        area_result = _handle_calculate_area(
            mask=change_mask.astype(bool),
            affine_list=before_affine_list,
            crs=before_crs,
        )

        if "area_m2" in area_result:
            result["changed_area_m2"] = area_result["area_m2"]

        if "area_km2" in area_result:
            result["changed_area_km2"] = area_result["area_km2"]

        if "area_hectares" in area_result:
            result["changed_area_hectares"] = area_result[
                "area_hectares"
            ]

    else:
        result["changed_area_m2"] = None
        result["changed_area_km2"] = None
        result["changed_area_hectares"] = None
        result.setdefault("limitations", []).append(
            "Geographic change area was not calculated because "
            "real affine/CRS metadata was not supplied."
        )

    return result


# ===========================================================================
# Web research / evidence verification
# ===========================================================================


def _handle_search_web(
    query: str,
    aoi_name: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    if not query or not str(query).strip():
        raise ValueError(
            "Web research requires a non-empty query."
        )

    agent = WebResearchAgent()

    dtos = agent.research(
        query,
        aoi_name or "",
    )

    citations = []

    for dto in dtos:
        citations.append(
            {
                "publisher": getattr(
                    dto,
                    "publisher",
                    None,
                ),
                "title": getattr(
                    dto,
                    "title",
                    None,
                ),
                "source_url": getattr(
                    dto,
                    "source_url",
                    None,
                ),
                "trust_tier": getattr(
                    dto,
                    "trust_tier",
                    None,
                ),
                "trust_score": _optional_float(
                    getattr(
                        dto,
                        "trust_score",
                        None,
                    )
                ),
                "summary_facts": getattr(
                    dto,
                    "summary_facts",
                    None,
                ),
                "content_hash": getattr(
                    dto,
                    "content_hash",
                    None,
                ),
                "ttl_expires_at": getattr(
                    dto,
                    "ttl_expires_at",
                    None,
                ),
            }
        )

    return {
        "evidence_count": len(citations),
        "citations": citations,
        "status": "ok",
    }


def _handle_verify_evidence(
    satellite_scenes: list[dict[str, Any]],
    external_evidence: list[dict[str, Any]],
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    satellite = list(satellite_scenes or [])
    external = list(external_evidence or [])

    if not satellite and not external:
        return {
            "verification_status": "NO_EVIDENCE",
            "supporting_evidence_count": 0,
            "contradicting_evidence_count": 0,
            "limitations": [
                "No satellite or external evidence was supplied."
            ],
            "status": "ok",
        }

    supporting: list[dict[str, Any]] = []
    contradicting: list[dict[str, Any]] = []
    unclassified: list[dict[str, Any]] = []

    for item in external:
        classification = str(
            item.get(
                "classification",
                item.get(
                    "relation",
                    "",
                ),
            )
        ).strip().lower()

        if classification in {
            "support",
            "supports",
            "supporting",
            "corroborates",
            "corroborated",
        }:
            supporting.append(item)

        elif classification in {
            "contradict",
            "contradicts",
            "contradicting",
            "conflicts",
            "conflicting",
        }:
            contradicting.append(item)

        else:
            unclassified.append(item)

    if contradicting:
        verification_status = "CONFLICTING_EVIDENCE"
    elif supporting:
        verification_status = "SUPPORTED_BY_EXTERNAL_EVIDENCE"
    elif satellite:
        verification_status = "SATELLITE_EVIDENCE_ONLY"
    else:
        verification_status = "UNCLASSIFIED_EXTERNAL_EVIDENCE"

    limitations: list[str] = []

    if unclassified:
        limitations.append(
            "Some external evidence items did not contain an explicit "
            "support/contradiction classification."
        )

    if satellite and not external:
        limitations.append(
            "No external corroborating source was supplied."
        )

    if external and not satellite:
        limitations.append(
            "No satellite observation was supplied for physical "
            "cross-checking."
        )

    return {
        "verification_status": verification_status,
        "supporting_evidence_count": len(supporting),
        "contradicting_evidence_count": len(contradicting),
        "satellite_evidence_count": len(satellite),
        "external_evidence_count": len(external),
        "limitations": limitations,
        "status": "ok",
    }


# ===========================================================================
# Specialist model handlers
# ===========================================================================


def _handle_vqa(
    image_bytes: list[bytes] | None = None,
    image_paths: list[str] | None = None,
    question: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    if not question or not str(question).strip():
        raise ValueError(
            "VQA requires a non-empty question."
        )

    _image_inputs(
        image_bytes,
        image_paths,
        minimum=1,
    )

    from ai.adapters.geochat_adapter import GeoChatVQAAdapter

    adapter = GeoChatVQAAdapter()

    image_input = _select_image_input(
        image_bytes,
        image_paths,
        0,
    )

    out = adapter.answer(
        image_input,
        question=question,
        **kwargs,
    )

    return {
        "answer": getattr(out, "answer", None),
        "confidence": _optional_float(
            getattr(out, "confidence", None)
        ),
        "status": getattr(out, "status", "ok"),
        "raw": getattr(out, "raw", None),
    }


def _handle_caption(
    image_bytes: list[bytes] | None = None,
    image_paths: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    _image_inputs(
        image_bytes,
        image_paths,
        minimum=1,
    )

    from ai.adapters.geochat_adapter import GeoChatVQAAdapter

    adapter = GeoChatVQAAdapter()

    image_input = _select_image_input(
        image_bytes,
        image_paths,
        0,
    )

    out = adapter.caption(
        image_input,
        **kwargs,
    )

    return {
        "caption": getattr(out, "caption", None),
        "confidence": _optional_float(
            getattr(out, "confidence", None)
        ),
        "status": getattr(out, "status", "ok"),
        "raw": getattr(out, "raw", None),
    }


def _handle_grounding(
    image_bytes: list[bytes] | None = None,
    image_paths: list[str] | None = None,
    text_prompt: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    if not text_prompt or not str(text_prompt).strip():
        raise ValueError(
            "Grounding requires a non-empty text prompt."
        )

    _image_inputs(
        image_bytes,
        image_paths,
        minimum=1,
    )

    from ai.adapters.grounding_adapter import GroundingDINOAdapter

    adapter = GroundingDINOAdapter()

    image_input = _select_image_input(
        image_bytes,
        image_paths,
        0,
    )

    out = adapter.ground(
        image_input,
        text_prompt=text_prompt,
        **kwargs,
    )

    return {
        "boxes": getattr(out, "boxes", None) or [],
        "confidence": _optional_float(
            getattr(out, "confidence", None)
        ),
        "status": getattr(out, "status", "ok"),
        "raw": getattr(out, "raw", None),
    }


def _handle_change_detection(
    image_bytes: list[bytes] | None = None,
    image_paths: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    _image_inputs(
        image_bytes,
        image_paths,
        minimum=2,
    )

    from ai.adapters.changeformer_adapter import ChangeFormerAdapter

    adapter = ChangeFormerAdapter()

    before = _select_image_input(
        image_bytes,
        image_paths,
        0,
    )

    after = _select_image_input(
        image_bytes,
        image_paths,
        1,
    )

    out = adapter.detect_change(
        before,
        after,
        params=kwargs,
    )

    return {
        "answer": getattr(out, "answer", None),
        "confidence": _optional_float(
            getattr(out, "confidence", None)
        ),
        "boxes": getattr(out, "boxes", None) or [],
        "change_mask": getattr(out, "change_mask", None),
        "raw": getattr(out, "raw", None),
        "status": getattr(out, "status", "ok"),
    }


def _handle_change_vqa(
    image_bytes: list[bytes] | None = None,
    image_paths: list[str] | None = None,
    question: str = "",
    change_mask: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    if not question or not str(question).strip():
        raise ValueError("Change VQA requires a non-empty question.")
    _image_inputs(image_bytes, image_paths, minimum=2)
    from apps.agent.contracts import ModelInput
    from apps.models_ai.change_vqa.wrapper import ChangeVQAModel
    result = ChangeVQAModel().predict(ModelInput(
        model_id="CHANGE_VQA", image_paths=image_paths or [], image_bytes=image_bytes or [],
        question=str(question), change_mask=change_mask, params=kwargs,
    ))
    return {
        "answer": getattr(result, "answer", None),
        "confidence": _optional_float(getattr(result, "confidence", None)),
        "raw": getattr(result, "raw", None),
        "status": getattr(result, "status", "ok"),
    }


def _handle_coregister_temporal_optical_sar(
    image_paths: list[str] | None = None,
    image_metadata: list[dict[str, Any]] | None = None,
    max_pair_delta_hours: float = 72.0,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs
    if not image_paths or not image_metadata:
        raise ValueError("Temporal coregistration requires image paths and metadata.")
    from django.conf import settings
    from apps.geospatial.temporal_coregistration import prepare_temporal_optical_sar
    result = prepare_temporal_optical_sar(
        image_metadata, image_paths,
        max_pair_delta_hours=float(max_pair_delta_hours),
        output_root=str(Path(settings.MEDIA_ROOT) / "derived"),
    )
    return result


def _handle_temporal_optical_sar(
    image_bytes: list[bytes] | None = None,
    image_paths: list[str] | None = None,
    question: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    _image_inputs(image_bytes, image_paths, minimum=4)
    from apps.agent.contracts import ModelInput
    from apps.models_ai.temporal_optical_sar_wrapper import TemporalOpticalSARModel
    result = TemporalOpticalSARModel().predict(ModelInput(
        model_id="TEMPORAL_OPTICAL_SAR", image_paths=image_paths or [], image_bytes=image_bytes or [],
        question=str(question), params=kwargs, context={"analysis_route": kwargs.get("analysis_route", {})},
    ))
    return {"answer": getattr(result,"answer",None), "confidence": _optional_float(getattr(result,"confidence",None)), "raw": getattr(result,"raw",None), "status": getattr(result,"status","ok"), "error": getattr(result,"error",None)}


def _handle_optical_sar(
    image_bytes: list[bytes] | None = None,
    image_paths: list[str] | None = None,
    optical_index: int = 0,
    sar_index: int = 1,
    **kwargs: Any,
) -> dict[str, Any]:
    _image_inputs(
        image_bytes,
        image_paths,
        minimum=2,
    )

    if optical_index == sar_index:
        raise ValueError(
            "Optical and SAR inputs must reference different images."
        )

    from ai.adapters.optical_sar_adapter import OpticalSARAdapter

    adapter = OpticalSARAdapter()

    optical_input = _select_image_input(
        image_bytes,
        image_paths,
        optical_index,
    )

    sar_input = _select_image_input(
        image_bytes,
        image_paths,
        sar_index,
    )

    out = adapter.fuse(
        optical_input,
        sar_input,
        params=kwargs,
    )

    return {
        "answer": getattr(out, "answer", None),
        "confidence": _optional_float(
            getattr(out, "confidence", None)
        ),
        "boxes": getattr(out, "boxes", None) or [],
        "status": getattr(out, "status", "ok"),
        "raw": getattr(out, "raw", None),
    }


# ===========================================================================
# Metadata / statistics
# ===========================================================================


def _handle_geo_metadata(
    image_bytes: bytes | None = None,
    filename: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    if not image_bytes:
        raise ValueError(
            "No raster bytes provided for metadata extraction."
        )

    if not filename or not str(filename).strip():
        raise ValueError(
            "A real source filename is required for metadata extraction."
        )

    from apps.geospatial.ingestion import extract_metadata_from_bytes

    meta = extract_metadata_from_bytes(
        image_bytes,
        filename,
    )

    return {
        "width": getattr(meta, "width", None),
        "height": getattr(meta, "height", None),
        "band_count": getattr(meta, "band_count", None),
        "crs": getattr(meta, "crs", None),
        "sensor": getattr(meta, "sensor", None),
        "modality": getattr(meta, "modality", None),
        "resolution_m": _optional_float(
            getattr(meta, "resolution_m", None)
        ),
        "bounds_wgs84": getattr(
            meta,
            "bounds_wgs84",
            None,
        ),
        "is_georeferenced": getattr(
            meta,
            "is_georeferenced",
            None,
        ),
        "status": "ok",
    }


def _handle_histogram_analysis(
    raster_array: np.ndarray,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    array = _require_array(
        raster_array,
        "raster_array",
    )

    if array.ndim == 2:
        bands = [array]
    elif array.ndim == 3:
        bands = [
            array[:, :, index]
            for index in range(array.shape[2])
        ]
    else:
        raise ValueError(
            "Histogram analysis expects a 2-D or 3-D raster."
        )

    statistics: list[dict[str, Any]] = []

    for index, band in enumerate(bands):
        finite = np.asarray(band)[np.isfinite(band)]

        if finite.size == 0:
            statistics.append(
                {
                    "band_index": index,
                    "valid_pixel_count": 0,
                }
            )
            continue

        statistics.append(
            {
                "band_index": index,
                "valid_pixel_count": int(finite.size),
                "min": float(np.min(finite)),
                "max": float(np.max(finite)),
                "mean": float(np.mean(finite)),
                "std": float(np.std(finite)),
            }
        )

    return {
        "bands_analyzed": len(statistics),
        "statistics": statistics,
        "status": "ok",
    }


# ===========================================================================
# Spatial / temporal comparison
# ===========================================================================


def _handle_coregistration(
    bounds_a: dict[str, float],
    bounds_b: dict[str, float],
    crs_a: str | None = None,
    crs_b: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    if not bounds_a or not bounds_b:
        raise ValueError(
            "Both observations require real spatial bounds."
        )

    if crs_a and crs_b and str(crs_a) != str(crs_b):
        return {
            "coregistration_valid": False,
            "overlap": None,
            "reason": (
                "The observations use different CRS values. "
                "Reprojection/coregistration is required before "
                "pixel-wise comparison."
            ),
            "crs_a": str(crs_a),
            "crs_b": str(crs_b),
            "status": "CRS_MISMATCH",
        }

    overlap = _intersection(
        bounds_a,
        bounds_b,
    )

    if overlap is None:
        return {
            "coregistration_valid": False,
            "overlap": None,
            "reason": "The supplied spatial bounds do not overlap.",
            "status": "NO_SPATIAL_OVERLAP",
        }

    return {
        "coregistration_valid": True,
        "overlap": overlap,
        "reason": "The supplied spatial bounds overlap.",
        "status": "SPATIAL_OVERLAP",
    }


def _handle_spatial_relation(
    aoi_a: dict[str, Any],
    aoi_b: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    if not aoi_a or not aoi_b:
        raise ValueError(
            "Both AOI geometries are required."
        )

    try:
        from shapely.geometry import shape

        geometry_a = shape(aoi_a)
        geometry_b = shape(aoi_b)

    except Exception as exc:
        raise ValueError(
            "AOI geometries must be valid GeoJSON geometries."
        ) from exc

    if geometry_a.is_empty or geometry_b.is_empty:
        raise ValueError(
            "AOI geometries cannot be empty."
        )

    if geometry_a.equals(geometry_b):
        relation = "EQUAL"

    elif geometry_a.contains(geometry_b):
        relation = "CONTAINS"

    elif geometry_b.contains(geometry_a):
        relation = "WITHIN"

    elif geometry_a.intersects(geometry_b):
        relation = "INTERSECTS"

    elif geometry_a.touches(geometry_b):
        relation = "TOUCHES"

    else:
        relation = "DISJOINT"

    return {
        "relation": relation,
        "spatial_match": relation != "DISJOINT",
        "status": "ok",
    }


def _handle_temporal_comparison(
    t1_stats: dict[str, Any],
    t2_stats: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    if not t1_stats or not t2_stats:
        raise ValueError(
            "Both temporal statistic sets are required."
        )

    deltas: dict[str, float] = {}

    shared_keys = set(t1_stats.keys()) & set(t2_stats.keys())

    for key in sorted(shared_keys):
        value_a = t1_stats.get(key)
        value_b = t2_stats.get(key)

        if not _is_number(value_a) or not _is_number(value_b):
            continue

        deltas[key] = float(value_b) - float(value_a)

    if not deltas:
        return {
            "comparison_available": False,
            "deltas": {},
            "limitations": [
                "No shared numeric statistics were supplied."
            ],
            "status": "ok",
        }

    return {
        "comparison_available": True,
        "deltas": deltas,
        "limitations": [
            (
                "No significance threshold or physical interpretation "
                "was inferred by this tool."
            )
        ],
        "status": "ok",
    }


# ===========================================================================
# Report/export handlers
# ===========================================================================


def _handle_report_generation(
    session_id: str,
    query_id: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Do not claim that a report has been generated unless a real report
    service is connected.

    The handler provides a structured delegation contract that another
    service can replace later.
    """

    del kwargs

    if not session_id or not query_id:
        raise ValueError(
            "session_id and query_id are required for report generation."
        )

    return {
        "status": "NOT_GENERATED",
        "report_type": None,
        "artifact": None,
        "session_id": str(session_id),
        "query_id": str(query_id),
        "message": (
            "No report-generation service is connected to this tool."
        ),
    }


def _handle_evidence_export(
    features: list[dict[str, Any]],
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    if features is None:
        raise ValueError(
            "features is required."
        )

    if not isinstance(features, list):
        raise ValueError(
            "features must be a list of existing evidence features."
        )

    sanitized_features: list[dict[str, Any]] = []

    for feature in features:
        if not isinstance(feature, dict):
            raise ValueError(
                "Every evidence feature must be a dictionary."
            )

        if "geometry" not in feature:
            raise ValueError(
                "Evidence feature is missing its actual geometry."
            )

        sanitized_features.append(
            _json_safe(feature)
        )

    return {
        "feature_count": len(sanitized_features),
        "geojson": {
            "type": "FeatureCollection",
            "features": sanitized_features,
        },
        "status": "EXPORTED",
    }


# ===========================================================================
# RemoteCLIP
# ===========================================================================


def _handle_remoteclip_retrieval(
    image_bytes: list[bytes] | None = None,
    image_paths: list[str] | None = None,
    text_queries: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs

    if not text_queries:
        raise ValueError(
            "RemoteCLIP retrieval requires explicit text_queries."
        )

    queries = [
        str(query).strip()
        for query in text_queries
        if str(query).strip()
    ]

    if not queries:
        raise ValueError(
            "RemoteCLIP text_queries cannot be empty."
        )

    _image_inputs(
        image_bytes,
        image_paths,
        minimum=1,
    )

    from ai.adapters.remoteclip_adapter import RemoteCLIPAdapter

    adapter = RemoteCLIPAdapter()

    image_input = _select_image_input(
        image_bytes,
        image_paths,
        0,
    )

    scores = adapter.score_similarity(
        image_input,
        queries,
    )

    ranked = adapter.classify_region(
        image_input,
        queries,
    )

    return {
        "similarity_scores": scores,
        "ranked_classes": ranked,
        "status": "ok",
    }


# ===========================================================================
# Small utility helpers
# ===========================================================================


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not np.isfinite(number):
        return None

    return number


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False

    try:
        number = float(value)
    except (TypeError, ValueError):
        return False

    return bool(np.isfinite(number))


def _sum_actual_numeric_field(
    items: Sequence[Mapping[str, Any]],
    field_name: str,
) -> float | None:
    values: list[float] = []

    for item in items:
        value = item.get(field_name)

        if _is_number(value):
            values.append(float(value))

    if not values:
        return None

    return float(sum(values))


def _sanitize_numeric_mapping(
    mapping: Mapping[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for key, value in mapping.items():
        if isinstance(value, np.generic):
            result[str(key)] = value.item()

        elif isinstance(value, dict):
            result[str(key)] = _sanitize_numeric_mapping(
                value
            )

        elif isinstance(value, list):
            result[str(key)] = [
                item.item()
                if isinstance(item, np.generic)
                else item
                for item in value
            ]

        else:
            result[str(key)] = value

    return result