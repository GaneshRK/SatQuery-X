import pytest
from apps.agent.conversation_engine import ConversationEngine


def test_default_context_generation():
    engine = ConversationEngine()
    ctx = engine.get_default_context("Chennai Region")
    assert ctx["active_aoi"]["name"] == "Chennai Region"
    assert ctx["active_focus"] == "landscape"
    assert len(ctx["selected_dates"]) == 2
    assert "center" in ctx["current_visual_state"]
    assert ctx["current_visual_state"]["zoom"] == 11


def test_detect_ambiguity_triggers():
    engine = ConversationEngine()
    ctx = engine.get_default_context()

    # Vague query 1: "is this place growing?"
    res1 = engine.detect_ambiguity("is this place growing?", ctx)
    assert res1 is not None
    assert res1["is_ambiguous"] is True
    assert "urban" in res1["clarification_prompt"].lower()
    assert len(res1["options"]) >= 3

    # Vague query 2: "what changed?"
    res2 = engine.detect_ambiguity("what changed?", ctx)
    assert res2 is not None
    assert res2["is_ambiguous"] is True
    assert len(res2["options"]) >= 3

    # Specific query: should NOT trigger ambiguity
    res3 = engine.detect_ambiguity("Assess flood extent and standing water in Kaziranga", ctx)
    assert res3 is None


def test_detect_ambiguity_bypassed_in_active_focus():
    engine = ConversationEngine()
    ctx = engine.get_default_context()
    ctx["active_focus"] = "built_up"  # ongoing focused dialogue

    # Even if short, user is already deep in dialogue about built_up
    res = engine.detect_ambiguity("is this place growing?", ctx)
    assert res is None


def test_reference_resolution_focus_and_pronouns():
    engine = ConversationEngine()
    ctx = engine.get_default_context("Pollachi Agricultural Basin")

    # Turn 1: User redirects focus to construction
    q1 = "Focus on the construction and new buildings"
    resolved_q1, ctx1 = engine.resolve_references(q1, ctx)
    assert ctx1["active_focus"] == "built_up"
    assert "built-up infrastructure" in ctx1["conversation_entities"]

    # Turn 2: User uses anaphoric pronoun "they"
    q2 = "Were they there in 2019?"
    resolved_q2, ctx2 = engine.resolve_references(q2, ctx1)
    assert "2019" in resolved_q2
    assert "built_up" in resolved_q2.lower() or "built-up" in resolved_q2.lower()
    assert "baseline" in resolved_q2.lower()

    # Turn 3: User asks "how much did they expand?"
    q3 = "How much did they expand?"
    resolved_q3, ctx3 = engine.resolve_references(q3, ctx2)
    assert "hectares" in resolved_q3.lower() or "area" in resolved_q3.lower()
    assert "built_up" in resolved_q3.lower() or "built-up" in resolved_q3.lower()


def test_reference_resolution_spatial_phrases():
    engine = ConversationEngine()
    ctx = engine.get_default_context("Brahmaputra Flood Plain")

    # Spatial query: "What is happening here?"
    q = "What is happening here?"
    resolved_q, _ = engine.resolve_references(q, ctx)
    assert "Brahmaputra Flood Plain" in resolved_q
    assert "landcover" in resolved_q.lower() or "surface" in resolved_q.lower()

    # Report query: "Give me a report"
    q_rep = "Give me a report"
    resolved_rep, _ = engine.resolve_references(q_rep, ctx)
    assert "Brahmaputra Flood Plain" in resolved_rep
    assert "report" in resolved_rep.lower()


def test_context_update_after_query():
    engine = ConversationEngine()
    ctx = engine.get_default_context()

    plan = {
        "target": "water",
        "aoi": {"name": "Barpeta District", "bbox": [90.5, 26.1, 91.2, 26.6]},
        "time_range": {"start": "2020-07-01", "end": "2020-07-15"},
    }
    measurements = [{"metric": "Inundated Area", "value": 45.2, "unit": "km2"}]

    updated_ctx = engine.update_context_after_query(
        context=ctx,
        query_text="Quantify flood surface area",
        answer="Inundated surface water reached 45.2 km2 across Barpeta.",
        plan=plan,
        measurements=measurements,
    )

    assert "Quantify flood surface area" in updated_ctx["previous_questions"]
    assert len(updated_ctx["previous_results"]) == 1
    assert updated_ctx["previous_results"][0]["measurements"][0]["value"] == 45.2
    assert updated_ctx["active_aoi"]["name"] == "Barpeta District"
    assert updated_ctx["selected_dates"] == ["2020-07-01", "2020-07-15"]
    assert "water" in updated_ctx["conversation_entities"]
