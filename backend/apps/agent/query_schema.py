"""Query Understanding & Analysis Plan JSON Contracts per SatQuery AI Architecture.
Provides deterministic, structured schema contracts between language understanding
and geospatial execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class ComparisonMode:
    MODE_A_DESCRIPTIVE = "MODE_A_DESCRIPTIVE"  # Single-date regional baseline comparison
    MODE_B_CHANGE_DYNAMICS = "MODE_B_CHANGE_DYNAMICS"  # Bi-temporal change dynamic comparison (growth rate)


@dataclass
class QueryUnderstandingContract:
    raw_query: str
    intent: str
    entities: List[Dict[str, Any]] = field(default_factory=list)
    subject: Dict[str, Any] = field(default_factory=lambda: {"type": "GENERAL"})
    temporal: Dict[str, Any] = field(default_factory=lambda: {"required": False})
    modalities: Dict[str, Any] = field(default_factory=lambda: {"required": "AUTO"})
    spatial: Dict[str, Any] = field(default_factory=lambda: {"relation": "SINGLE_AOI"})
    comparison_mode: Optional[str] = None
    conversation_refs: List[str] = field(default_factory=list)
    confidence: float = 0.90

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "intent": self.intent,
            "entities": self.entities,
            "subject": self.subject,
            "temporal": self.temporal,
            "modalities": self.modalities,
            "spatial": self.spatial,
            "comparison_mode": self.comparison_mode,
            "conversation_refs": self.conversation_refs,
            "confidence": self.confidence,
        }


@dataclass
class PlanStepContract:
    step_number: int
    tool: str
    action: str
    input_params: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    status: str = "PENDING"  # PENDING, RUNNING, DONE, FAILED, NOT_REQUIRED


@dataclass
class AnalysisPlanContract:
    intent: str
    comparison_mode: Optional[str] = None
    steps: List[PlanStepContract] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "comparison_mode": self.comparison_mode,
            "steps": [
                {
                    "step_number": s.step_number,
                    "tool": s.tool,
                    "action": s.action,
                    "input_params": s.input_params,
                    "rationale": s.rationale,
                    "status": s.status,
                }
                for s in self.steps
            ],
        }
