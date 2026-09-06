"""
Serializers for the SatQuery-X conversational query API.

Important:
- Serializers expose only evidence that actually exists.
- No scientific method, provider, measurement, CRS, or confidence value
  is invented here.
- The answer contract is generated from the query's execution/evidence data.
- The frontend can use the contract to render maps, measurements, sources,
  evidence and trace information safely.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from rest_framework import serializers

from apps.imagery.models import ImageAsset, ImagePair

from .models import ExecutionStep, Query


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _first_present(data: dict, *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value
    return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalise_confidence(value: Any) -> float | None:
    """
    Normalize a confidence value only when the upstream evidence actually
    provides one.
    """
    number = _safe_float(value)

    if number is None:
        return None

    if 0.0 <= number <= 1.0:
        return number

    return None


def _append_unique(items: list, value: Any) -> None:
    if value is None:
        return

    if isinstance(value, str) and not value.strip():
        return

    if value not in items:
        items.append(value)


# ---------------------------------------------------------------------------
# Execution step
# ---------------------------------------------------------------------------

class ExecutionStepSerializer(serializers.ModelSerializer):
    """
    Public representation of one orchestration step.

    This intentionally exposes a concise execution record rather than
    internal reasoning.
    """

    class Meta:
        model = ExecutionStep
        fields = [
            "id",
            "step_number",
            "tool_name",
            "agent_type",
            "model_version",
            "parameters",
            "input_refs",
            "output_ref",
            "evidence_refs",
            "status",
            "latency_ms",
            "retry_count",
            "started_at",
            "completed_at",
            "error",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Evidence serializers
# ---------------------------------------------------------------------------

class EvidenceRegionSerializer(serializers.Serializer):
    """
    Flexible evidence-region representation.

    Different specialist agents can produce different region structures,
    therefore the serializer intentionally accepts the common fields without
    imposing fabricated scientific assumptions.
    """

    id = serializers.CharField(required=False, allow_blank=True)

    label = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    geometry = serializers.JSONField(
        required=False,
        allow_null=True,
    )

    bbox = serializers.JSONField(
        required=False,
        allow_null=True,
    )

    coordinate_space = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    area = serializers.FloatField(
        required=False,
        allow_null=True,
    )

    area_unit = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    confidence = serializers.FloatField(
        required=False,
        allow_null=True,
    )

    source = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    evidence_ref = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    def validate_confidence(self, value):
        if value is None:
            return value

        if not 0.0 <= value <= 1.0:
            raise serializers.ValidationError(
                "Confidence must be between 0 and 1."
            )

        return value


class ExternalEvidenceSerializer(serializers.Serializer):
    """
    Evidence originating outside the local specialist-agent execution.
    """

    id = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    source = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    provider = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    title = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    url = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    retrieved_at = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    content = serializers.JSONField(
        required=False,
        allow_null=True,
    )

    evidence_type = serializers.CharField(
        required=False,
        allow_blank=True,
    )


# ---------------------------------------------------------------------------
# Answer contract helpers
# ---------------------------------------------------------------------------

def _extract_measurements(evidence: dict) -> list[dict]:
    """
    Extract measurements explicitly present in evidence.

    No measurement is calculated here.
    """

    measurements: list[dict] = []

    measurement_containers = [
        evidence.get("measurements"),
        evidence.get("metrics"),
        evidence.get("statistics"),
    ]

    for container in measurement_containers:
        if not isinstance(container, dict):
            continue

        for name, value in container.items():
            if isinstance(value, dict):
                number = _first_present(
                    value,
                    "value",
                    "measurement",
                    "amount",
                )

                unit = _first_present(
                    value,
                    "unit",
                    "units",
                )
            else:
                number = value
                unit = None

            if number is None:
                continue

            measurements.append(
                {
                    "name": str(name),
                    "value": number,
                    "unit": unit,
                    "source": "evidence",
                }
            )

    root_measurement_keys = [
        "area_km2",
        "area_ha",
        "area_m2",
        "changed_area_km2",
        "changed_area_ha",
        "changed_area_m2",
        "pixel_area_m2",
        "resolution_m",
        "ground_sample_distance_m",
        "change_pixels",
        "changed_pixels",
        "change_percent",
        "change_percentage",
        "water_area_km2",
        "vegetation_area_km2",
        "structure_area_km2",
    ]

    unit_map = {
        "area_km2": "km²",
        "area_ha": "ha",
        "area_m2": "m²",
        "changed_area_km2": "km²",
        "changed_area_ha": "ha",
        "changed_area_m2": "m²",
        "pixel_area_m2": "m²/pixel",
        "resolution_m": "m",
        "ground_sample_distance_m": "m",
        "change_pixels": "pixels",
        "changed_pixels": "pixels",
        "change_percent": "%",
        "change_percentage": "%",
        "water_area_km2": "km²",
        "vegetation_area_km2": "km²",
        "structure_area_km2": "km²",
    }

    existing_names = {
        item["name"]
        for item in measurements
        if isinstance(item, dict)
    }

    for key in root_measurement_keys:
        if key not in evidence:
            continue

        value = evidence.get(key)

        if value is None:
            continue

        if key in existing_names:
            continue

        measurements.append(
            {
                "name": key,
                "value": value,
                "unit": unit_map.get(key),
                "source": "evidence",
            }
        )

    return measurements


def _extract_sources(
    query: Query,
    evidence: dict,
    external_evidence: list,
) -> list[dict]:
    """
    Build a source list only from actual metadata/evidence.
    """

    sources: list[dict] = []

    def add_source(
        *,
        source_type: str,
        name: Any = None,
        identifier: Any = None,
        metadata: dict | None = None,
    ) -> None:
        if not name and not identifier:
            return

        sources.append(
            {
                "type": source_type,
                "name": name,
                "identifier": identifier,
                "metadata": metadata or {},
            }
        )

    context = _as_dict(
        query.context_snapshot
    )

    imagery_context = _as_dict(
        context.get("imagery")
    )

    if imagery_context:
        add_source(
            source_type="imagery_context",
            name=_first_present(
                imagery_context,
                "filename",
                "name",
                "title",
            ),
            identifier=_first_present(
                imagery_context,
                "id",
                "asset_id",
            ),
            metadata=imagery_context,
        )

    source_metadata = _as_dict(
        evidence.get("source_metadata")
    )

    if source_metadata:
        add_source(
            source_type="source_metadata",
            name=_first_present(
                source_metadata,
                "provider",
                "source",
                "name",
                "platform",
            ),
            identifier=_first_present(
                source_metadata,
                "id",
                "stac_item_id",
                "product_id",
            ),
            metadata=source_metadata,
        )

    provenance = evidence.get("provenance")

    if isinstance(provenance, list):
        for item in provenance:
            if not isinstance(item, dict):
                continue

            add_source(
                source_type="provenance",
                name=_first_present(
                    item,
                    "source",
                    "provider",
                    "name",
                ),
                identifier=_first_present(
                    item,
                    "id",
                    "asset_id",
                    "artifact_id",
                ),
                metadata=item,
            )

    elif isinstance(provenance, dict):
        add_source(
            source_type="provenance",
            name=_first_present(
                provenance,
                "source",
                "provider",
                "name",
            ),
            identifier=_first_present(
                provenance,
                "id",
                "asset_id",
                "artifact_id",
            ),
            metadata=provenance,
        )

    for item in external_evidence:
        if not isinstance(item, dict):
            continue

        add_source(
            source_type="external",
            name=_first_present(
                item,
                "source",
                "provider",
                "title",
            ),
            identifier=_first_present(
                item,
                "id",
                "url",
            ),
            metadata=item,
        )

    return sources


def _extract_methods(query: Query) -> list[dict]:
    """
    Extract actual executed methods/models from ExecutionStep records.
    """

    methods: list[dict] = []

    steps = query.execution_steps.all()

    for step in steps:
        if step.status != "DONE":
            continue

        method_name = (
            step.tool_name
            or step.agent_type
        )

        if not method_name:
            continue

        methods.append(
            {
                "name": method_name,
                "agent_type": step.agent_type or None,
                "model_version": (
                    step.model_version
                    if step.model_version
                    and step.model_version != "unknown"
                    else None
                ),
                "step_number": step.step_number,
            }
        )

    return methods


def _extract_limitations(
    query: Query,
    evidence: dict,
) -> list[str]:
    """
    Return limitations explicitly disclosed by execution/evidence.
    """

    limitations: list[str] = []

    candidates = [
        evidence.get("limitations"),
        evidence.get("limitations_disclosed"),
        evidence.get("warnings"),
        evidence.get("caveats"),
    ]

    for candidate in candidates:
        if isinstance(candidate, str):
            _append_unique(
                limitations,
                candidate,
            )

        elif isinstance(candidate, list):
            for item in candidate:
                if isinstance(item, str):
                    _append_unique(
                        limitations,
                        item,
                    )

                elif isinstance(item, dict):
                    text = _first_present(
                        item,
                        "message",
                        "text",
                        "description",
                    )

                    if text:
                        _append_unique(
                            limitations,
                            str(text),
                        )

        elif isinstance(candidate, dict):
            for value in candidate.values():
                if isinstance(value, str):
                    _append_unique(
                        limitations,
                        value,
                    )

    if evidence.get(
        "insufficient_evidence"
    ) is True:
        _append_unique(
            limitations,
            "Available evidence is insufficient for a reliable conclusion.",
        )

    if evidence.get(
        "georeference_available"
    ) is False:
        _append_unique(
            limitations,
            "The imagery does not contain a usable geospatial reference.",
        )

    return limitations


def _extract_regions(
    evidence: dict,
) -> list[dict]:
    """
    Collect regions produced by specialist analysis.
    """

    region_candidates = [
        evidence.get("regions"),
        evidence.get("change_regions"),
        evidence.get("detections"),
        evidence.get("objects"),
    ]

    regions: list[dict] = []

    for candidate in region_candidates:
        if not isinstance(candidate, list):
            continue

        for item in candidate:
            if not isinstance(item, dict):
                continue

            regions.append(item)

    return regions


def _extract_map_actions(
    evidence: dict,
) -> list[dict]:
    """
    Extract explicit map/UI actions from evidence.
    """

    actions: list[dict] = []

    map_data = _as_dict(
        evidence.get("map")
    )

    if map_data:
        geometry = map_data.get(
            "geometry"
        )

        artifact_url = _first_present(
            map_data,
            "overlay_url",
            "geojson_url",
            "artifact_url",
        )

        if geometry is not None:
            actions.append(
                {
                    "type": "SHOW_GEOMETRY",
                    "geometry": geometry,
                }
            )

        if artifact_url:
            actions.append(
                {
                    "type": "SHOW_ARTIFACT",
                    "url": artifact_url,
                }
            )

    artifact_data = evidence.get(
        "artifacts"
    )

    if isinstance(artifact_data, list):
        for artifact in artifact_data:
            if not isinstance(artifact, dict):
                continue

            url = _first_present(
                artifact,
                "url",
                "artifact_url",
                "download_url",
            )

            if url:
                actions.append(
                    {
                        "type": "SHOW_ARTIFACT",
                        "url": url,
                        "artifact_type": artifact.get(
                            "artifact_type"
                        ),
                    }
                )

    return actions


# ---------------------------------------------------------------------------
# Query detail serializer
# ---------------------------------------------------------------------------

class QueryDetailSerializer(
    serializers.ModelSerializer
):
    """
    Full query representation for the frontend.
    """

    execution_steps = ExecutionStepSerializer(
        many=True,
        read_only=True,
    )

    evidence_regions = serializers.SerializerMethodField()

    external_evidence = serializers.SerializerMethodField()

    answer_contract = serializers.SerializerMethodField()

    ui_actions = serializers.SerializerMethodField()

    clarification = serializers.SerializerMethodField()

    input_asset_ids = serializers.SerializerMethodField()

    class Meta:
        model = Query

        fields = [
            "id",
            "session",
            "user",
            "text",
            "image",
            "image_pair",
            "input_asset_ids",
            "detected_mode",
            "detected_task",
            "status",
            "plan",
            "structured_plan",
            "context_snapshot",
            "follow_up_questions",
            "evidence_graph",
            "evidence_bundle",
            "answer",
            "confidence",
            "clarification_required",
            "clarification",
            "answer_trace",
            "error",
            "created_at",
            "completed_at",
            "execution_steps",
            "evidence_regions",
            "external_evidence",
            "answer_contract",
            "ui_actions",
        ]

        read_only_fields = fields

    def get_input_asset_ids(
        self,
        obj: Query,
    ) -> list[str]:

        try:
            ids = list(
                obj.input_assets.values_list(
                    "id",
                    flat=True,
                )
            )
        except Exception:
            ids = []

        if obj.image_id and obj.image_id not in ids:
            ids.insert(
                0,
                obj.image_id,
            )

        return [
            str(value)
            for value in ids
        ]

    def _combined_evidence(
        self,
        obj: Query,
    ) -> dict:
        """
        Combine validated evidence bundle with evidence graph.
        """

        graph = _as_dict(
            obj.evidence_graph
        )

        bundle = _as_dict(
            obj.evidence_bundle
        )

        if not graph and not bundle:
            return {}

        combined = dict(graph)

        for key, value in bundle.items():
            combined[key] = value

        return combined

    def get_evidence_regions(
        self,
        obj: Query,
    ) -> list[dict]:

        evidence = self._combined_evidence(
            obj
        )

        regions = _extract_regions(
            evidence
        )

        output = []

        for region in regions:
            serializer = EvidenceRegionSerializer(
                data=region
            )

            if serializer.is_valid():
                output.append(
                    serializer.validated_data
                )

        return output

    def get_external_evidence(
        self,
        obj: Query,
    ) -> list[dict]:

        evidence = self._combined_evidence(
            obj
        )

        candidates = evidence.get(
            "external_evidence",
            evidence.get(
                "external_sources",
                [],
            ),
        )

        if not isinstance(
            candidates,
            list,
        ):
            return []

        output = []

        for item in candidates:
            if not isinstance(
                item,
                dict,
            ):
                continue

            serializer = ExternalEvidenceSerializer(
                data=item
            )

            if serializer.is_valid():
                output.append(
                    serializer.validated_data
                )

        return output

    def get_clarification(
        self,
        obj: Query,
    ) -> dict:

        clarification = _as_dict(
            obj.clarification
        )

        if clarification:
            return clarification

        evidence = self._combined_evidence(
            obj
        )

        fallback = evidence.get(
            "clarification"
        )

        if isinstance(
            fallback,
            dict,
        ):
            return fallback

        return {}

    def get_ui_actions(
        self,
        obj: Query,
    ) -> list[dict]:

        evidence = self._combined_evidence(
            obj
        )

        actions = _extract_map_actions(
            evidence
        )

        artifacts = evidence.get(
            "artifacts"
        )

        if isinstance(
            artifacts,
            list,
        ):
            for artifact in artifacts:
                if not isinstance(
                    artifact,
                    dict,
                ):
                    continue

                url = _first_present(
                    artifact,
                    "url",
                    "artifact_url",
                    "download_url",
                )

                if not url:
                    continue

                artifact_type = artifact.get(
                    "artifact_type"
                )

                if artifact_type in {
                    "CHANGE_MASK",
                    "CHANGE_GEOJSON",
                    "CHANGE_OVERLAY",
                }:
                    actions.append(
                        {
                            "type": "SHOW_CHANGE_ARTIFACT",
                            "url": url,
                            "artifact_type": artifact_type,
                        }
                    )

        return actions

    def get_answer_contract(
        self,
        obj: Query,
    ) -> dict:

        evidence = self._combined_evidence(
            obj
        )

        external_evidence = (
            self.get_external_evidence(obj)
        )

        measurements = _extract_measurements(
            evidence
        )

        sources = _extract_sources(
            obj,
            evidence,
            external_evidence,
        )

        methods = _extract_methods(
            obj
        )

        limitations = _extract_limitations(
            obj,
            evidence,
        )

        regions = self.get_evidence_regions(
            obj
        )

        evidence_confidence = (
            _normalise_confidence(
                _first_present(
                    evidence,
                    "confidence",
                    "evidence_confidence",
                    "validated_confidence",
                )
            )
        )

        query_confidence = (
            _normalise_confidence(
                obj.confidence
            )
        )

        confidence = (
            evidence_confidence
            if evidence_confidence is not None
            else query_confidence
        )

        geospatial = _as_dict(
            evidence.get("geospatial")
        )

        geometry = _first_present(
            geospatial,
            "geometry",
            "geojson",
        )

        bbox = _first_present(
            geospatial,
            "bbox",
            "bounds",
            "extent",
        )

        crs = _first_present(
            geospatial,
            "crs",
            "coordinate_reference_system",
        )

        georeferenced = _first_present(
            geospatial,
            "georeferenced",
            "has_georeference",
        )

        artifacts = []

        raw_artifacts = evidence.get(
            "artifacts",
            [],
        )

        if isinstance(
            raw_artifacts,
            list,
        ):
            for artifact in raw_artifacts:
                if isinstance(
                    artifact,
                    dict,
                ):
                    artifacts.append(
                        artifact
                    )

        processing = _as_dict(
            evidence.get(
                "processing"
            )
        )

        return {
            "version": "1.0",

            "answer_available": (
                obj.has_answer
            ),

            "clarification_required": (
                obj.clarification_required
            ),

            "task": obj.detected_task,

            "mode": obj.detected_mode,

            "confidence": confidence,

            "measurements": measurements,

            "regions": regions,

            "methods": methods,

            "sources": sources,

            "limitations": limitations,

            "geospatial": {
                "available": bool(
                    geometry is not None
                    or bbox is not None
                    or crs is not None
                    or georeferenced is True
                ),
                "geometry": geometry,
                "bbox": bbox,
                "crs": crs,
                "georeferenced": georeferenced,
            },

            "processing": processing,

            "artifacts": artifacts,

            "evidence_status": _first_present(
                evidence,
                "evidence_status",
                "validation_status",
                "status",
            ),

            "evidence_refs": _as_list(
                evidence.get(
                    "evidence_refs"
                )
            ),

            "trace_available": bool(
                obj.answer_trace
                or obj.execution_steps.exists()
            ),
        }


# ---------------------------------------------------------------------------
# Query creation/update serializer
# ---------------------------------------------------------------------------

class QueryCreateSerializer(
    serializers.ModelSerializer
):
    """
    Internal/API serializer for creating a query.

    The actual execution is performed by the orchestrator task.
    """

    image_id = serializers.PrimaryKeyRelatedField(
        source="image",
        queryset=ImageAsset.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
    )

    image_pair_id = serializers.PrimaryKeyRelatedField(
        source="image_pair",
        queryset=ImagePair.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
    )

    input_asset_ids = serializers.PrimaryKeyRelatedField(
        source="input_assets",
        queryset=ImageAsset.objects.all(),
        many=True,
        required=False,
        write_only=True,
    )

    visual_context = serializers.JSONField(
        required=False,
        write_only=True,
    )

    aoi_geometry = serializers.JSONField(
        required=False,
        write_only=True,
    )

    class Meta:
        model = Query

        fields = [
            "id",
            "session",
            "user",
            "text",
            "image_id",
            "image_pair_id",
            "input_asset_ids",
            "detected_mode",
            "detected_task",
            "visual_context",
            "aoi_geometry",
            "context_snapshot",
        ]

        read_only_fields = [
            "id",
            "user",
            "detected_mode",
            "detected_task",
        ]

    def validate(
        self,
        attrs,
    ):
        request = self.context.get(
            "request"
        )

        session = attrs.get(
            "session"
        )

        if request is not None:
            user = request.user

            if not user.is_authenticated:
                raise serializers.ValidationError(
                    "Authentication is required."
                )

            if session is not None:
                if getattr(
                    session,
                    "user_id",
                    None,
                ) != user.id:
                    raise serializers.ValidationError(
                        "Session does not belong to the authenticated user."
                    )

        image = attrs.get(
            "image"
        )

        image_pair = attrs.get(
            "image_pair"
        )

        input_assets = attrs.get(
            "input_assets"
        ) or []

        if session is not None:

            if (
                image is not None
                and image.session_id != session.id
            ):
                raise serializers.ValidationError(
                    {
                        "image_id": (
                            "Image must belong to the selected session."
                        )
                    }
                )

            if (
                image_pair is not None
                and image_pair.session_id != session.id
            ):
                raise serializers.ValidationError(
                    {
                        "image_pair_id": (
                            "Image pair must belong to the selected session."
                        )
                    }
                )

            invalid_assets = [
                str(asset.id)
                for asset in input_assets
                if asset.session_id != session.id
            ]

            if invalid_assets:
                raise serializers.ValidationError(
                    {
                        "input_asset_ids": (
                            "All input assets must belong to the "
                            "selected session."
                        )
                    }
                )

        text = attrs.get(
            "text",
            "",
        )

        if not isinstance(
            text,
            str,
        ) or not text.strip():
            raise serializers.ValidationError(
                {
                    "text": "Query text is required."
                }
            )

        if (
            image_pair is not None
            and image is not None
        ):
            pair_asset_ids = {
                image_pair.image_before_id,
                image_pair.image_after_id,
            }

            if image.id not in pair_asset_ids:
                raise serializers.ValidationError(
                    {
                        "image_id": (
                            "The selected image is not part of "
                            "the selected image pair."
                        )
                    }
                )

        return attrs

    @transaction.atomic
    def create(
        self,
        validated_data,
    ):
        visual_context = validated_data.pop(
            "visual_context",
            None,
        )

        aoi_geometry = validated_data.pop(
            "aoi_geometry",
            None,
        )

        input_assets = validated_data.pop(
            "input_assets",
            [],
        )

        request = self.context.get(
            "request"
        )

        if request is not None:
            validated_data["user"] = (
                request.user
            )

        context_snapshot = _as_dict(
            validated_data.get(
                "context_snapshot"
            )
        )

        if visual_context is not None:
            context_snapshot[
                "visual_context"
            ] = visual_context

        if aoi_geometry is not None:
            context_snapshot[
                "aoi_geometry"
            ] = aoi_geometry

        validated_data[
            "context_snapshot"
        ] = context_snapshot

        query = Query.objects.create(
            **validated_data
        )

        if input_assets:
            query.input_assets.set(
                input_assets
            )

        return query