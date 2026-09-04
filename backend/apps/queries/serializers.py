from rest_framework import serializers
from apps.evidence.models import EvidenceRegion, ExternalEvidence
from apps.queries.models import ExecutionStep, Query


class ExecutionStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExecutionStep
        fields = "__all__"


class EvidenceRegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvidenceRegion
        fields = "__all__"


class ExternalEvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalEvidence
        fields = "__all__"


class QueryDetailSerializer(serializers.ModelSerializer):
    execution_steps = ExecutionStepSerializer(many=True, read_only=True)
    evidence_regions = EvidenceRegionSerializer(many=True, read_only=True)
    external_evidence = ExternalEvidenceSerializer(many=True, read_only=True)
    answer_contract = serializers.SerializerMethodField()

    class Meta:
        model = Query
        fields = (
            "id",
            "session",
            "text",
            "image",
            "image_pair",
            "detected_mode",
            "detected_task",
            "status",
            "plan",
            "structured_plan",
            "follow_up_questions",
            "evidence_graph",
            "answer",
            "confidence",
            "answer_contract",
            "error",
            "created_at",
            "completed_at",
            "execution_steps",
            "evidence_regions",
            "external_evidence",
        )

    def get_answer_contract(self, obj: Query) -> dict:
        """
        Produces the canonical 10-key Answer Contract:
        {
          answer: str,
          confidence: float,
          findings: list,
          measurements: list,
          regions: list,
          evidence: list,
          sources: list,
          models: list,
          methods: list,
          limitations: list
        }
        """
        findings = []
        measurements = []
        models_used = []
        methods_used = []
        evidence_list = []

        # Collect from execution steps
        for step in obj.execution_steps.all():
            models_used.append(step.tool_name)
            output = step.output_ref or {}
            if isinstance(output, dict):
                for k, v in output.items():
                    if k in ("area_km2", "total_water_km2", "total_veg_km2", "total_structure_km2", "area_ha"):
                        measurements.append({"metric": k, "value": v, "unit": "km2" if "km2" in k else "ha"})
                    elif k in ("candidate_count", "water_features_count", "valid_pixels"):
                        measurements.append({"metric": k, "value": v, "unit": "count"})
                    elif k in ("mean_ndvi", "mean", "min", "max", "std"):
                        measurements.append({"metric": k, "value": v, "unit": "index_value"})

        # Collect findings from answer and evidence
        if obj.answer:
            findings.append(obj.answer)

        # Collect regions
        regions = []
        for reg in obj.evidence_regions.all()[:50]:
            feat = {
                "id": str(reg.id),
                "type": "Feature",
                "geometry": reg.geojson_geometry,
                "properties": {
                    "class_name": reg.class_name,
                    "confidence": reg.confidence,
                    "area_km2": reg.area_km2,
                    "area_ha": reg.area_ha,
                }
            }
            regions.append(feat)
            evidence_list.append({
                "type": "polygon",
                "label": reg.class_name,
                "confidence": reg.confidence,
                "area_km2": reg.area_km2,
            })

        # Sources
        sources = []
        if obj.image:
            prov = obj.image.provenance or {}
            sources.append({
                "sensor": obj.image.sensor,
                "filename": obj.image.original_filename,
                "crs": obj.image.crs,
                "provider": prov.get("source", "Copernicus Data Space Ecosystem"),
                "stac_item_id": prov.get("stac_item_id"),
            })
        if obj.image_pair:
            sources.append({
                "pair_type": obj.image_pair.pair_type,
                "image_a": obj.image_pair.image_a.original_filename if obj.image_pair.image_a else None,
                "image_b": obj.image_pair.image_b.original_filename if obj.image_pair.image_b else None,
            })

        for ext in obj.external_evidence.all():
            sources.append({
                "source_type": "EXTERNAL_WEB_EVIDENCE",
                "publisher": ext.publisher,
                "title": ext.title,
                "domain": ext.source_domain,
                "trust_tier": ext.source_type,
                "trust_score": ext.trust_score,
                "url": ext.source_url,
            })
            evidence_list.append({
                "type": "external_citation",
                "publisher": ext.publisher,
                "trust_tier": ext.source_type,
                "facts": ext.summary_facts,
            })

        # Methods based on task
        if obj.detected_task == "CHANGE_DETECTION":
            methods_used.extend([
                "Bi-temporal Differencing",
                "Morphological Opening and Closing",
                "Connected Component Polygonization",
                "Local Equal-Area Geodesic Metric Integration",
            ])
        elif obj.detected_task == "VQA":
            methods_used.extend([
                "Deterministic Spatial Computer Vision",
                "Spectral Normalized Difference Index Math",
                "Contour Feature Extraction",
            ])
        else:
            methods_used.extend([
                "Multimodal Remote Sensing Analysis",
                "GeoTIFF Rasterio Chunk Window Processing",
            ])

        # Scientific limitations per requirement
        limitations = [
            "Spatial resolution constrained by satellite sensor Ground Sample Distance (GSD).",
            "Spectral response subject to atmospheric transmission and uncalibrated aerosol effects.",
            "Area metrics derived via local Cylindrical Equal Area (CEA) approximation.",
        ]

        return {
            "answer": obj.answer or "",
            "confidence": obj.confidence or 0.0,
            "findings": findings,
            "measurements": measurements,
            "regions": regions,
            "evidence": evidence_list,
            "sources": sources,
            "models": list(set(models_used)),
            "methods": list(set(methods_used)),
            "limitations": limitations,
        }
