# SatQuery-X — Conversation Engine & Reference Resolution

## 1. Core Functions
The `ConversationEngine` (`backend/apps/agent/conversation_engine.py`) provides:
1. **Anaphoric & Pronoun Reference Resolution**:
   - Resolves words like *"they"*, *"this part"*, *"here"*, *"those buildings"* using the current `conversation_entities` and `active_region`.
2. **Ambiguity Detection & Targeted Clarification**:
   - Intercepts queries like *"Is this place growing?"* or *"What changed?"* when multiple conflicting interpretations exist.
   - Formulates minimal, smart clarification questions with structured option pills.
3. **Context State Accumulation**:
   - Updates `Session.conversation_context` after each query turn with newly extracted entities, physical measurements, and active visual state.

---

## 2. Reference Resolution Rules

| User Query Fragment | Contextual Resolution Rule |
| :--- | :--- |
| *"What is happening here?"* | Grounded to `context.active_aoi` or `context.current_visual_state.center`. |
| *"Focus on the construction."* | Targets `built_up` entities identified in the previous turn. Sets focus entity to `"built_up"`. |
| *"Were they there in 2019?"* | Resolves `"they"` $\to$ `"built_up"`. Sets comparison baseline date to `"2019-01-01"`. |
| *"How much did they expand?"* | Resolves `"they"` $\to$ `"built_up"`. Emits metric quantification request for the change delta. |
| *"Why did it happen?"* | Sets `external_evidence_required = True`. Triggers Web Research Agent for regional planning news. |
| *"Show me exactly where."* | Emits `ZOOM_TO_REGION` and `SHOW_LAYER: change_overlay` UI actions. |

---

## 3. Ambiguity & Clarification Protocol
When a query contains multiple plausible semantic targets:
```json
{
  "type": "CLARIFICATION_REQUIRED",
  "prompt": "Do you mean urban development, vegetation canopy changes, or surface water expansion?",
  "options": [
    { "label": "Urban Development", "value": "Analyze urban and building expansion in this region" },
    { "label": "Vegetation Growth", "value": "Analyze vegetation canopy health and NDVI changes" },
    { "label": "Water Bodies", "value": "Analyze surface water extent and flood changes" }
  ]
}
```
The frontend renders these options as immediate one-click query pills.
