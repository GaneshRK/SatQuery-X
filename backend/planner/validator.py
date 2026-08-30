"""Plan validation against input mode and registry constraints."""

from __future__ import annotations

from backend.planner.schemas import PlanStep
from backend.registry.loader import ModelRegistry


MAX_PLAN_STEPS = 5


class PlanValidationError(Exception):
    pass


def validate_plan(
    plan: list[PlanStep],
    detected_mode: str,
    image_count: int,
    registry: ModelRegistry,
) -> None:
    if not plan:
        raise PlanValidationError("Plan must contain at least one step.")
    if len(plan) > MAX_PLAN_STEPS:
        raise PlanValidationError(f"Plan exceeds maximum of {MAX_PLAN_STEPS} steps.")

    for step in plan:
        entry = registry.get(step.tool)
        if detected_mode not in entry.input_modes and detected_mode != "change_vqa":
            if not (detected_mode == "bi_temporal" and "bi_temporal" in entry.input_modes):
                if not (detected_mode == "cross_modal_pair" and "cross_modal_pair" in entry.input_modes):
                    if detected_mode == "single_image" and "single_image" not in entry.input_modes:
                        raise PlanValidationError(
                            f"Tool {step.tool} incompatible with mode {detected_mode}."
                        )

        if step.tool == "CHANGE_DETECTION" and image_count < 2:
            raise PlanValidationError("CHANGE_DETECTION requires two images.")
        if step.tool == "OPTICAL_SAR_FUSION" and image_count < 2:
            raise PlanValidationError("OPTICAL_SAR_FUSION requires two images.")

    # Dependency check
    executed: set[str] = set()
    for step in plan:
        entry = registry.get(step.tool)
        for dep in entry.depends_on:
            if dep not in executed:
                raise PlanValidationError(f"{step.tool} depends on {dep} which has not run yet.")
        executed.add(step.tool)
