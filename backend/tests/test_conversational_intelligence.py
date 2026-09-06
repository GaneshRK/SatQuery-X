"""Unit and integration tests for SatQuery AI Conversational Intelligence Pipeline.
Validates deictic pronoun resolution, multi-turn memory, non-hardcoded dynamic metrics,
calibrated confidence, and multi-location comparison per SIH 26167.
"""

import pytest
from apps.agent.context_engine import ContextEngine
from apps.agent.evidence_engine import EvidenceEngine
from apps.agent.intent_ontology import GeoIntent, classify_geo_intent, extract_multiple_locations
from apps.agent.response_engine import ResponseEngine
from apps.agent.understander import understand_query
from apps.system.frontend_contract_views import get_or_create_default_user
from apps.queries.models import Query
from apps.sessions.models import Session
from apps.agent.agent import Agent


def test_deictic_resolution_with_active_aoi():
    """Verifies that 'What is changing here?' resolves against the active AOI rather than failing or asking clarification."""
    session_ctx = {
        "active_aoi": {
            "name": "Coimbatore Industrial Basin",
            "bbox": [76.90, 10.95, 77.05, 11.08],
        },
        "image_count": 0,
        "has_images": False,
    }
    intent = understand_query("What is changing here?", session_ctx)
    assert intent.clarification_required is False
    assert intent.location["name"] == "Coimbatore Industrial Basin"
    assert intent.location["bbox"] == [76.90, 10.95, 77.05, 11.08]
    assert intent.temporal is True
    assert intent.geo_intent == GeoIntent.BI_TEMPORAL_CHANGE


def test_deictic_resolution_with_viewport_bbox():
    """Verifies that 'What is changing here?' resolves against current map viewport."""
    session_ctx = {
        "current_viewport": {
            "bbox": [76.95, 11.00, 77.05, 11.10],
        },
        "image_count": 0,
        "has_images": False,
    }
    intent = understand_query("What is changing here?", session_ctx)
    assert intent.clarification_required is False
    assert intent.location["source"] == "map_viewport"
    assert intent.location["bbox"] == [76.95, 11.00, 77.05, 11.10]


def test_multi_location_comparison_extraction():
    """Verifies that comparing two regions triggers REGION_COMPARISON with structured options."""
    query_text = "Compare Coimbatore and Chennai"
    locations = extract_multiple_locations(query_text)
    assert len(locations) == 2
    names = [loc["name"] for loc in locations]
    assert "Coimbatore Industrial Basin" in names
    assert "Chennai Metropolitan Region" in names

    intent = understand_query(query_text, {})
    assert intent.intent == "REGION_COMPARISON"
    assert intent.geo_intent == GeoIntent.REGION_COMPARISON
    assert intent.clarification_required is False
    assert len(intent.multi_locations) == 2
    loc_names = [l["name"] for l in intent.multi_locations]
    assert "Coimbatore Industrial Basin" in loc_names
    assert "Chennai Metropolitan Region" in loc_names


def test_conversational_follow_up_filter_and_quantify():
    """Verifies that follow-up queries like 'Only show vegetation' and 'How much?' utilize conversational memory."""
    ce = ContextEngine({
        "conversation_history": [
            {
                "query_text": "What is changing in Coimbatore?",
                "intent": "change_vqa",
                "target": "surface_change",
                "location": "Coimbatore Industrial Basin",
                "metrics": {
                    "detected_change_km2": 4.85,
                    "detected_change_ha": 485.0,
                    "model_confidence_pct": 89.5,
                },
            }
        ]
    })

    assert ce.is_follow_up_query("Only show vegetation") is True
    assert ce.is_follow_up_query("How much?") is True

    # Test understanding follow-up
    intent_filter = understand_query("Only show vegetation", ce.raw_context)
    assert intent_filter.intent == "FOLLOW_UP_REFINEMENT"
    assert intent_filter.target == "vegetation"
    assert intent_filter.operation == "filter_target"
    assert intent_filter.is_follow_up is True
    assert intent_filter.location["name"] == "Coimbatore Industrial Basin"

    intent_quant = understand_query("How much?", ce.raw_context)
    assert intent_quant.intent == "FOLLOW_UP_REFINEMENT"
    assert intent_quant.operation == "quantify"
    assert intent_quant.is_follow_up is True


def test_calibrated_confidence_formula():
    """Verifies that confidence is mathematically discounted by cloud cover, coarse resolution, and data quality."""
    # Ideal conditions
    conf_ideal = EvidenceEngine.calculate_calibrated_confidence(
        model_confidence=0.95,
        cloud_cover_pct=0.0,
        usable_data_pct=100.0,
        registration_score=1.0,
        spatial_resolution_m=10.0,
    )
    assert conf_ideal["calibrated_confidence_pct"] >= 90.0

    # Adverse atmospheric conditions (30% cloud cover, 85% usable data)
    conf_adverse = EvidenceEngine.calculate_calibrated_confidence(
        model_confidence=0.95,
        cloud_cover_pct=30.0,
        usable_data_pct=85.0,
        registration_score=0.95,
        spatial_resolution_m=10.0,
    )
    # 0.95 * 0.70 * 0.85 * 0.95 = ~0.537
    assert conf_adverse["calibrated_confidence_pct"] < conf_ideal["calibrated_confidence_pct"]
    assert 50.0 <= conf_adverse["calibrated_confidence_pct"] <= 60.0


@pytest.mark.django_db
def test_end_to_end_follow_up_execution_without_hardcoded_metrics():
    """Verifies that follow-up queries executed through Agent.run produce accurate dynamic metrics without static 18.7 km²."""
    user = get_or_create_default_user()
    session = Session.objects.create(
        user=user,
        name="Conversational Test Session",
        conversation_context={
            "conversation_history": [
                {
                    "query_text": "What changed in Coimbatore?",
                    "intent": "change_vqa",
                    "target": "surface_change",
                    "location": "Coimbatore Industrial Basin",
                    "metrics": {
                        "detected_change_km2": 7.32,
                        "detected_change_ha": 732.0,
                        "model_confidence_pct": 92.4,
                    },
                }
            ]
        },
    )

    q_quant = Query.objects.create(session=session, user=user, text="How much changed?")
    result = Agent.run(q_quant, session_context=session.conversation_context)

    assert result["status"] == "COMPLETED"
    assert "7.320 km²" in q_quant.answer
    assert "732.0 hectares" in q_quant.answer
    assert "18.7" not in q_quant.answer
    assert result["metrics"]["detected_change_km2"] == 7.32


def test_lowercase_location_resolution_and_contamination_prevention():
    """Verifies 'what so change in thoothukudi' does not contaminate with previous Coimbatore active_aoi."""
    session_ctx = {
        "active_aoi": {
            "name": "Coimbatore Industrial Basin",
            "bbox": [76.90, 10.95, 77.05, 11.08],
        },
        "conversation_history": [
            {
                "query_text": "what changed in coimbatore?",
                "location": "Coimbatore Industrial Basin",
            }
        ]
    }
    intent = understand_query("what so change in thoothukudi", session_ctx)
    assert intent.location["name"] == "Thoothukudi Port & Maritime Industrial Hub"
    assert "Coimbatore" not in intent.location["name"]
    assert intent.temporal is True


def test_case_insensitive_region_comparison():
    """Verifies 'compare thoothukudi to coimbatore' correctly identifies both locations and triggers REGION_COMPARISON."""
    intent = understand_query("compare thoothukudi to coimbatore", {})
    assert intent.intent == "REGION_COMPARISON"
    assert len(intent.multi_locations) == 2
    names = [l["name"] for l in intent.multi_locations]
    assert "Thoothukudi Port & Maritime Industrial Hub" in names
    assert "Coimbatore Industrial Basin" in names


@pytest.mark.django_db
def test_clean_domain_specific_reasoning_without_log_boilerplate():
    """Verifies responses do not dump internal step counts and contain factual domain context."""
    user = get_or_create_default_user()
    session = Session.objects.create(user=user, name="Domain Reasoning Test Session")
    q = Query.objects.create(session=session, user=user, text="what so change in thoothukudi")

    res = Agent.run(q, session.conversation_context)
    assert res["status"] == "COMPLETED"
    assert "Completed 3 analysis step(s)" not in q.answer
    assert "AI Cloud Masking" not in q.answer
    assert "Thoothukudi" in q.answer
    assert any(w in q.answer.lower() for w in ("port", "coastal", "salt", "maritime"))


def test_entity_switch_what_about_thothukudi():
    """Verifies that 'what about thothukudi?' preserves the change analysis intent and resolves to Thoothukudi."""
    session_ctx = {
        "conversation_history": [
            {
                "turn_index": 1,
                "query_text": "what is changing in coimbatore?",
                "intent": "BI_TEMPORAL_CHANGE",
                "task": "CHANGE_DETECTION",
                "target": "surface_change",
                "location": {"name": "Coimbatore Industrial Basin"},
            }
        ]
    }
    intent = understand_query("what about thothukudi?", session_ctx)
    assert intent.location["name"] == "Thoothukudi Port & Maritime Industrial Hub"
    assert "Coimbatore" not in intent.location["name"]
    assert intent.temporal is True
    assert intent.intent == "CHANGE_DETECTION"
    assert intent.is_follow_up is True


def test_location_resolver_typo_tolerance():
    """Verifies that LocationResolver repairs common phonetic typos."""
    from apps.agent.location_resolver import LocationResolver

    loc1 = LocationResolver.resolve("thothukudi")
    assert loc1 is not None
    assert loc1.canonical_name == "Thoothukudi Port & Maritime Industrial Hub"
    assert loc1.bbox == [78.08, 8.70, 78.22, 8.85]

    loc2 = LocationResolver.resolve("coimbature")
    assert loc2 is not None
    assert loc2.canonical_name == "Coimbatore Industrial Basin"
    assert loc2.bbox == [76.85, 10.90, 77.10, 11.15]


@pytest.mark.django_db
def test_fail_closed_comparison_on_unresolvable_region():
    """Verifies that comparative analysis fails closed with 0.0 confidence when a region cannot be verified."""
    user = get_or_create_default_user()
    session = Session.objects.create(user=user, name="Fail-Closed Comparison Session")
    q = Query.objects.create(session=session, user=user, text="compare thoothukudi to unresolvablecity999")

    res = Agent.run(q, session.conversation_context)
    assert res["status"] == "COMPLETED"
    assert q.confidence == 0.0
    assert "Comparative Analysis Blocked" in q.answer
    assert "Fail-Closed" in q.answer
    assert "Thoothukudi Port & Maritime Industrial Hub" in q.answer


