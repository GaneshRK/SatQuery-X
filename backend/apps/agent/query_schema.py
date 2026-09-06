"""
SatQuery-X Query Schema Contracts
=================================

Stable JSON-safe contracts shared by:

    Query Understanding
            ↓
    Query Optimizer
            ↓
    Planner
            ↓
    Executor
            ↓
    Evidence / Response layers

Design goals
------------
- Deterministic and JSON serializable.
- No fabricated coordinates, dates, sensors, measurements, or confidence.
- Explicit distinction between:
    * user request
    * resolved context
    * execution requirements
    * execution plan
- Backward-compatible field names where practical.
- Safe for Django JSONField persistence.
- Does not contain scientific evidence itself.
- Does not expose chain-of-thought.

Important
---------
`confidence` in QueryUnderstandingContract is intentionally optional.
A query understanding component must not manufacture a confidence score.
If a caller has an independently calibrated score, it may be supplied;
otherwise it remains None.

The schema is deliberately permissive because different specialist agents
may add domain-specific metadata. Validation is conservative rather than
destructive.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# ============================================================================
# Constants
# ============================================================================


class ComparisonMode:
    """
    Supported comparison semantics.

    These are semantic modes, not execution results.
    """

    MODE_A_DESCRIPTIVE = "MODE_A_DESCRIPTIVE"
    MODE_B_CHANGE_DYNAMICS = "MODE_B_CHANGE_DYNAMICS"

    # Additional explicit modes used by the newer pipeline.
    SINGLE_OBSERVATION = "SINGLE_OBSERVATION"
    BI_TEMPORAL = "BI_TEMPORAL"
    CROSS_MODAL = "CROSS_MODAL"


class PlanStepStatus:
    """Execution lifecycle states for plan steps."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    NOT_REQUIRED = "NOT_REQUIRED"


class QueryStatus:
    """High-level query lifecycle states."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"


# ============================================================================
# JSON safety helpers
# ============================================================================


def _json_safe(value: Any) -> Any:
    """
    Convert common Python values into JSON-safe structures.

    This helper intentionally avoids importing Django or NumPy at module
    import time. Optional support is detected dynamically.
    """

    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    # datetime/date
    try:
        from datetime import date, datetime

        if isinstance(value, (datetime, date)):
            return value.isoformat()
    except Exception:
        pass

    # UUID
    try:
        from uuid import UUID

        if isinstance(value, UUID):
            return str(value)
    except Exception:
        pass

    # NumPy
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return value.tolist()

        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass

    # Django model-like objects.
    object_id = getattr(value, "id", None)

    if object_id is not None:
        try:
            return str(object_id)
        except Exception:
            pass

    # Last-resort string representation.
    return str(value)


# ============================================================================
# Query understanding contract
# ============================================================================


@dataclass
class QueryUnderstandingContract:
    """
    Structured representation of what the user is asking.

    This contract describes the request and available context.

    It does NOT represent:
    - satellite observations
    - scientific measurements
    - model predictions
    - generated confidence
    - final answers
    """

    raw_query: str

    intent: str

    entities: List[Dict[str, Any]] = field(
        default_factory=list
    )

    subject: Dict[str, Any] = field(
        default_factory=lambda: {
            "type": "GENERAL"
        }
    )

    temporal: Dict[str, Any] = field(
        default_factory=lambda: {
            "required": False
        }
    )

    modalities: Dict[str, Any] = field(
        default_factory=lambda: {
            "required": "AUTO",
            "requested": [],
            "available": [],
        }
    )

    spatial: Dict[str, Any] = field(
        default_factory=lambda: {
            "relation": "SINGLE_AOI"
        }
    )

    comparison_mode: Optional[str] = None

    conversation_refs: List[str] = field(
        default_factory=list
    )

    # This is optional by design.
    #
    # None means:
    # "No calibrated understanding-confidence value was supplied."
    confidence: Optional[float] = None

    # Additional fields required by the current SatQuery-X architecture.
    operation: Optional[str] = None

    requested_outputs: List[str] = field(
        default_factory=list
    )

    requested_measurements: List[str] = field(
        default_factory=list
    )

    location: Dict[str, Any] = field(
        default_factory=dict
    )

    time_range: Dict[str, Any] = field(
        default_factory=dict
    )

    is_follow_up: bool = False

    clarification_required: bool = False

    clarification_prompt: Optional[str] = None

    clarification_options: List[str] = field(
        default_factory=list
    )

    missing_data: List[str] = field(
        default_factory=list
    )

    auto_search_required: bool = False

    external_evidence_required: bool = False

    external_query: str = ""

    context_source: List[str] = field(
        default_factory=list
    )

    source: str = "query_understanding"

    schema_version: str = "2.0"

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe dictionary."""

        return _json_safe(asdict(self))


# ============================================================================
# Plan step contract
# ============================================================================


@dataclass
class PlanStepContract:
    """
    One auditable execution step.

    `rationale` is a short operational explanation only.
    It must never contain hidden chain-of-thought.
    """

    step_number: int

    tool: str

    action: str

    input_params: Dict[str, Any] = field(
        default_factory=dict
    )

    rationale: str = ""

    status: str = PlanStepStatus.PENDING

    # Optional dependency information.
    depends_on: List[int] = field(
        default_factory=list
    )

    # Number of real image observations required.
    required_images: int = 0

    # Relationship between inputs.
    relationship: Optional[str] = None

    # Whether failure should stop the whole pipeline.
    optional: bool = False

    # Logical capability represented by this step.
    capability: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe step dictionary."""

        return _json_safe(
            {
                "step_number": self.step_number,
                "tool": self.tool,
                "action": self.action,
                "input_params": self.input_params,
                "rationale": self.rationale,
                "status": self.status,
                "depends_on": self.depends_on,
                "required_images": self.required_images,
                "relationship": self.relationship,
                "optional": self.optional,
                "capability": self.capability,
            }
        )


# ============================================================================
# Analysis plan contract
# ============================================================================


@dataclass
class AnalysisPlanContract:
    """
    Complete machine-readable analysis plan.

    The plan says what should happen. It does not contain the scientific
    result of those operations.
    """

    intent: str

    comparison_mode: Optional[str] = None

    steps: List[PlanStepContract] = field(
        default_factory=list
    )

    target: Optional[str] = None

    operation: Optional[str] = None

    aoi: Dict[str, Any] = field(
        default_factory=dict
    )

    time_range: Dict[str, Any] = field(
        default_factory=dict
    )

    modalities: List[str] = field(
        default_factory=list
    )

    requested_outputs: List[str] = field(
        default_factory=list
    )

    requested_measurements: List[str] = field(
        default_factory=list
    )

    input_requirements: Dict[str, Any] = field(
        default_factory=dict
    )

    uncertainty_notes: List[str] = field(
        default_factory=list
    )

    clarification_required: bool = False

    clarification_prompt: Optional[str] = None

    clarification_options: List[str] = field(
        default_factory=list
    )

    external_evidence_required: bool = False

    external_query: str = ""

    is_follow_up: bool = False

    context: Dict[str, Any] = field(
        default_factory=dict
    )

    source: str = "query_optimizer"

    optimizer_version: str = "6.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert the complete plan to a JSON-safe dictionary."""

        return _json_safe(
            {
                "intent": self.intent,
                "comparison_mode": self.comparison_mode,
                "steps": [
                    step.to_dict()
                    if isinstance(step, PlanStepContract)
                    else step
                    for step in self.steps
                ],
                "target": self.target,
                "operation": self.operation,
                "aoi": self.aoi,
                "time_range": self.time_range,
                "modalities": self.modalities,
                "requested_outputs": self.requested_outputs,
                "requested_measurements": self.requested_measurements,
                "input_requirements": self.input_requirements,
                "uncertainty_notes": self.uncertainty_notes,
                "clarification_required": self.clarification_required,
                "clarification_prompt": self.clarification_prompt,
                "clarification_options": self.clarification_options,
                "external_evidence_required": self.external_evidence_required,
                "external_query": self.external_query,
                "is_follow_up": self.is_follow_up,
                "context": self.context,
                "source": self.source,
                "optimizer_version": self.optimizer_version,
            }
        )


# ============================================================================
# Compatibility helpers
# ============================================================================


def understanding_to_plan_contract(
    understanding: QueryUnderstandingContract,
) -> AnalysisPlanContract:
    """
    Convert a query-understanding contract into an empty analysis plan.

    Actual execution steps are intentionally NOT invented here.
    """

    return AnalysisPlanContract(
        intent=understanding.intent,
        comparison_mode=understanding.comparison_mode,
        target=(
            understanding.subject.get("name")
            or understanding.subject.get("type")
        ),
        operation=understanding.operation,
        aoi=dict(understanding.location or {}),
        time_range=dict(understanding.time_range or {}),
        modalities=list(
            understanding.modalities.get(
                "requested",
                []
            )
            or []
        ),
        requested_outputs=list(
            understanding.requested_outputs
        ),
        requested_measurements=list(
            understanding.requested_measurements
        ),
        input_requirements={
            "missing_data": list(
                understanding.missing_data
            ),
            "auto_search_required": (
                understanding.auto_search_required
            ),
        },
        clarification_required=(
            understanding.clarification_required
        ),
        clarification_prompt=(
            understanding.clarification_prompt
        ),
        clarification_options=list(
            understanding.clarification_options
        ),
        external_evidence_required=(
            understanding.external_evidence_required
        ),
        external_query=(
            understanding.external_query
        ),
        is_follow_up=(
            understanding.is_follow_up
        ),
        context={
            "conversation_refs": list(
                understanding.conversation_refs
            ),
            "context_source": list(
                understanding.context_source
            ),
        },
    )


# ============================================================================
# Public exports
# ============================================================================


__all__ = [
    "ComparisonMode",
    "PlanStepStatus",
    "QueryStatus",
    "QueryUnderstandingContract",
    "PlanStepContract",
    "AnalysisPlanContract",
    "understanding_to_plan_contract",
]