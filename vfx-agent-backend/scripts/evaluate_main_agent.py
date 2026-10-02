#!/usr/bin/env python3
"""Evaluate MainAgent routing and generation briefs with the configured real model."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from agent.llm import get_main_agent_llm
from agent.main_actions import MAIN_AGENT_TOOLS, parse_main_action
from agent.prompts import MAIN_AGENT_SYSTEM


REQUIRED_CATEGORIES = {
    "complete creation",
    "reasonable completion",
    "high ambiguity",
    "creative request",
    "simple edit",
    "parameter update",
    "mixed edit",
    "rename",
    "pinned joint",
    "seconds conversion",
    "unsupported pixels",
    "single reference",
    "multiple references",
    "previous effect",
    "reference creativity",
    "effect explanation",
    "effect comparison",
    "product question",
    "conflicting edit",
    "contradictory request",
    "explicit replacement",
    "clear additive edit",
}


CREATE_CONTEXT = """## Trusted editor context
[Operation: create]
[No active effects]
[No pinned joints]
[No effect mentions]"""

EDIT_CONTEXT = """## Trusted editor context
[Operation: edit]
[Current effect: name=Violet Wrist Glow; status=active]
[Current controls: {"color": {"current": "#AA44FF", "default": "#AA44FF", "description": "Changes the glow color", "label": "Glow color", "type": "color"}, "size": {"current": 20, "default": 20, "description": "Larger values expand the glow", "label": "Glow size", "max": 80, "min": 5, "step": 1, "type": "range"}}]
[No active effects]
[No pinned joints]
[No effect mentions]"""

REFERENCE_CONTEXT = """## Trusted editor context
[Operation: create]
[Active effects: [{"id": "ref-a", "name": "Ribbon Wake", "updated_at": "2026-08-01T10:00:00"}, {"id": "ref-b", "name": "Orbit Halo", "updated_at": "2026-08-02T10:00:00"}]]
[No pinned joints]
[Effect mentions: [{"display_name": "Ribbon Wake", "effect_id": "ref-a"}, {"display_name": "Orbit Halo", "effect_id": "ref-b"}]]"""

PREVIOUS_CONTEXT = """## Trusted editor context
[Operation: create]
[Active effects: [{"id": "ref-a", "name": "Ribbon Wake", "updated_at": "2026-08-01T10:00:00"}, {"id": "ref-b", "name": "Orbit Halo", "updated_at": "2026-08-02T10:00:00"}]]
[No pinned joints]
[Effect mentions: [{"display_name": "Orbit Halo", "effect_id": "ref-b"}]]"""

TIMED_EDIT_CONTEXT = """## Trusted editor context
[Operation: edit]
[Current effect: name=Arm Path Transition; status=active]
[Current controls: {}]
[Editor paths: [{"alias": "path1", "id": "path-a", "point_count": 49}, {"alias": "path2", "id": "path-b", "point_count": 63}]]
[Editor time markers: [{"alias": "t1", "id": "marker-a", "frame": 60}, {"alias": "t3", "id": "marker-c", "frame": 82}, {"alias": "t2", "id": "marker-b", "frame": 153}]]
[No active effects]
[No pinned joints]
[No effect mentions]"""

TIMED_CREATE_CONTEXT = TIMED_EDIT_CONTEXT.replace(
    "[Operation: edit]",
    "[Operation: create]",
).replace(
    "[Current effect: name=Arm Path Transition; status=active]\n[Current controls: {}]\n",
    "",
)

ARM_PATH_HISTORY = (
    (
        "user",
        "At t1, gather bright particles from the right arm into path1, then move them "
        "to the left hand and finally into path2 by t2.",
    ),
    ("assistant", "Arm Path Transition is ready."),
)


@dataclass(frozen=True)
class EvaluationCase:
    """One externally observable MainAgent routing expectation."""

    case_id: str
    category: str
    user_input: str
    expected_action: str
    trusted_context: str = CREATE_CONTEXT
    required_terms: tuple[str, ...] = ()
    required_any: tuple[tuple[str, ...], ...] = ()
    expected_params: dict[str, object] = field(default_factory=dict)
    expected_reference_ids: tuple[str, ...] = ()
    exact_option_count: int | None = None
    critical: bool = False
    history: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class EvaluationResult:
    """One scored model response."""

    case_id: str
    passed: bool
    action: str
    reasons: list[str]
    payload: str = ""


EVALUATION_CASES = (
    EvaluationCase(
        "complete_creation",
        "complete creation",
        "\u5728\u5de6\u53f3\u624b\u8155\u4e4b\u95f4\u505a\u4e00\u6761\u9752\u8272\u80fd\u91cf\u5e26\uff0c\u53cc\u624b\u5206\u5f00\u65f6\u62c9\u957f\u5e76\u9010\u6e10\u6de1\u51fa\u3002",
        "generate",
        required_terms=("left_wrist", "right_wrist", "cyan"),
        required_any=((
            "fade", "dissipat", "vanish", "decay", "disappear",
            "transparent", "opacity",
        ),),
        critical=True,
    ),
    EvaluationCase(
        "reasonable_completion",
        "reasonable completion",
        "\u7ed9\u5de6\u624b\u8155\u52a0\u4e00\u4e2a\u7d2b\u8272\u5149\u6655\u3002",
        "generate",
        required_terms=("left_wrist",),
        required_any=(("violet", "purple"),),
    ),
    EvaluationCase(
        "high_ambiguity",
        "high ambiguity",
        "Make the movement create something dramatic.",
        "clarify",
    ),
    EvaluationCase(
        "creative_request",
        "creative request",
        "\u7ed9\u6211\u60f3\u4e00\u4e2a\u6709\u521b\u610f\u7684\u7279\u6548\u3002",
        "clarify",
        exact_option_count=3,
        critical=True,
    ),
    EvaluationCase(
        "simple_edit",
        "simple edit",
        "\u8ba9\u5f53\u524d\u5149\u6655\u53d8\u6210\u4ece\u624b\u8155\u5411\u5916\u6269\u6563\u7684\u6ce2\u7eb9\u3002",
        "generate",
        trusted_context=EDIT_CONTEXT,
        required_terms=("wrist", "ripple"),
    ),
    EvaluationCase(
        "parameter_update",
        "parameter update",
        "\u628a\u5927\u5c0f\u8c03\u523040\u3002",
        "update_effect",
        trusted_context=EDIT_CONTEXT,
        expected_params={"size": 40},
        critical=True,
    ),
    EvaluationCase(
        "mixed_edit",
        "mixed edit",
        "\u8ba9\u5f53\u524d\u5149\u6655\u53d8\u6210\u87ba\u65cb\uff0c\u540c\u65f6\u628a\u5927\u5c0f\u8c03\u523040\u3002",
        "generate",
        trusted_context=EDIT_CONTEXT,
        required_terms=("spiral",),
        expected_params={"size": 40},
    ),
    EvaluationCase(
        "rename",
        "rename",
        "Rename it Aurora Pulse.",
        "update_effect",
        trusted_context=EDIT_CONTEXT,
        required_terms=("aurora pulse",),
    ),
    EvaluationCase(
        "pinned_joint",
        "pinned joint",
        "\u5728p1\u505a\u4e00\u4e2a\u9752\u8272\u8109\u51b2\u3002",
        "generate",
        trusted_context=CREATE_CONTEXT.replace(
            "[No pinned joints]",
            '[Pinned joints: {"p1": "right_wrist"}]',
        ),
        required_terms=("right_wrist",),
    ),
    EvaluationCase(
        "seconds_conversion",
        "seconds conversion",
        "\u5728\u53f3\u624b\u8155\u505a\u4e00\u4e2a2\u79d2\u5faa\u73af\u7684\u9752\u8272\u8109\u51b2\u3002",
        "generate",
        required_terms=("60 frames", "30 fps"),
        required_any=(("2 seconds", "two seconds", "2-second", "two-second"),),
    ),
    EvaluationCase(
        "unsupported_pixels",
        "unsupported pixels",
        "\u8bfb\u53d6\u8863\u670d\u989c\u8272\uff0c\u7136\u540e\u5728\u8eab\u4f53\u5468\u56f4\u751f\u6210\u540c\u8272\u5149\u6655\u3002",
        "respond",
        required_any=(
            (
                "cannot", "can't", "can\u2019t", "unable", "does not have access",
                "not available", "does not read", "doesn't read", "not video",
                "only",
            ),
            ("shoulder", "hip", "wrist", "ankle", "joint", "pose"),
            ("instead", "alternative", "user-chosen", "choose"),
        ),
        critical=True,
    ),
    EvaluationCase(
        "single_reference",
        "single reference",
        "\u53c2\u8003 @Ribbon Wake \u7684\u62d6\u5c3e\u8282\u594f\uff0c\u5728\u811a\u8e1d\u505a\u91d1\u8272\u8f68\u8ff9\u3002",
        "generate",
        trusted_context=REFERENCE_CONTEXT,
        required_terms=("ankle", "gold"),
        expected_reference_ids=("ref-a",),
    ),
    EvaluationCase(
        "multiple_references",
        "multiple references",
        "\u53c2\u8003 @Ribbon Wake \u7684\u8fd0\u52a8\u548c @Orbit Halo \u7684\u914d\u8272\uff0c\u5728\u53cc\u624b\u505a\u65b0\u7684\u80fd\u91cf\u6548\u679c\u3002",
        "generate",
        trusted_context=REFERENCE_CONTEXT,
        expected_reference_ids=("ref-a", "ref-b"),
    ),
    EvaluationCase(
        "previous_effect",
        "previous effect",
        "\u53c2\u8003\u4e0a\u4e00\u4e2a\u6548\u679c\u7684\u8fd0\u52a8\u65b9\u5f0f\uff0c\u5728\u53cc\u811a\u751f\u6210\u84dd\u8272\u7248\u672c\u3002",
        "generate",
        trusted_context=PREVIOUS_CONTEXT,
        expected_reference_ids=("ref-b",),
    ),
    EvaluationCase(
        "reference_creativity",
        "reference creativity",
        "\u53c2\u8003 @Ribbon Wake \u7ed9\u6211\u4e09\u4e2a\u65b0\u7684\u521b\u610f\u3002",
        "inspect_effects",
        trusted_context=REFERENCE_CONTEXT,
        expected_reference_ids=("ref-a",),
    ),
    EvaluationCase(
        "effect_explanation",
        "effect explanation",
        "\u4e3a\u4ec0\u4e48 @Ribbon Wake \u4f1a\u8fd9\u6837\u52a8\uff1f",
        "inspect_effects",
        trusted_context=REFERENCE_CONTEXT,
        expected_reference_ids=("ref-a",),
    ),
    EvaluationCase(
        "effect_comparison",
        "effect comparison",
        "\u6bd4\u8f83 @Ribbon Wake \u548c @Orbit Halo \u7684\u89c6\u89c9\u8fd0\u52a8\u3002",
        "inspect_effects",
        trusted_context=REFERENCE_CONTEXT,
        expected_reference_ids=("ref-a", "ref-b"),
    ),
    EvaluationCase(
        "product_question",
        "product question",
        "PromptPoseFX \u80fd\u8bfb\u53d6\u89c6\u9891\u80cc\u666f\u4e2d\u7684\u7269\u4f53\u5417\uff1f",
        "respond",
        required_terms=("pose",),
    ),
    EvaluationCase(
        "conflicting_timeline_edit",
        "conflicting edit",
        "The light particles must stay at path1 from t1 to t3.",
        "clarify",
        trusted_context=TIMED_EDIT_CONTEXT,
        exact_option_count=3,
        critical=True,
        history=ARM_PATH_HISTORY,
    ),
    EvaluationCase(
        "contradictory_timeline_request",
        "contradictory request",
        "Start the particles at t2 and end them at the earlier t1, while the animation always plays forward.",
        "clarify",
        trusted_context=TIMED_CREATE_CONTEXT,
    ),
    EvaluationCase(
        "explicit_replacement_edit",
        "explicit replacement",
        "Remove the existing arm-to-path2 motion and replace it entirely with particles held on path1 from t1 to t3.",
        "generate",
        trusted_context=TIMED_EDIT_CONTEXT,
        required_terms=("path1", "t1", "t3"),
        required_any=(("remove", "replace", "instead"),),
        history=ARM_PATH_HISTORY,
    ),
    EvaluationCase(
        "clear_additive_edit",
        "clear additive edit",
        "Keep the current animation unchanged and add a second group of particles that stays on path1 from t1 to t3.",
        "generate",
        trusted_context=TIMED_EDIT_CONTEXT,
        required_terms=("path1", "t1", "t3"),
        required_any=(("keep", "preserve", "unchanged", "existing"),),
        history=ARM_PATH_HISTORY,
    ),
)


def _action_text(action: object) -> str:
    if hasattr(action, "model_dump_json"):
        return action.model_dump_json().casefold()
    return str(action).casefold()


def evaluate_action(case: EvaluationCase, message: AIMessage) -> EvaluationResult:
    """Score one model action against an independent behavior specification."""
    try:
        action = parse_main_action(message)
    except Exception as error:
        return EvaluationResult(case.case_id, False, "invalid", [str(error)], str(message))

    received = action.action
    action_text = _action_text(action)
    reasons = []
    if received != case.expected_action:
        reasons.append(f"expected {case.expected_action}, received {received}")
        return EvaluationResult(case.case_id, False, received, reasons, action_text)

    for term in case.required_terms:
        if term.casefold() not in action_text:
            reasons.append(f"missing required term: {term}")
    for alternatives in case.required_any:
        if not any(term.casefold() in action_text for term in alternatives):
            reasons.append(f"missing one of required terms: {alternatives!r}")

    parameter_updates = getattr(action, "parameter_updates", {}) or {}
    for key, value in case.expected_params.items():
        if parameter_updates.get(key) != value:
            reasons.append(f"expected parameter {key}={value!r}")

    if case.expected_reference_ids:
        if received == "inspect_effects":
            actual_reference_ids = tuple(getattr(action, "effect_ids", ()))
        else:
            actual_reference_ids = tuple(
                reference.effect_id
                for reference in getattr(action, "references", ())
            )
        if actual_reference_ids != case.expected_reference_ids:
            reasons.append(
                "expected references "
                f"{case.expected_reference_ids!r}, received {actual_reference_ids!r}"
            )

    if case.exact_option_count is not None:
        option_count = len(getattr(action, "options", ()))
        if option_count != case.exact_option_count:
            reasons.append(f"expected exactly {case.exact_option_count} options")

    return EvaluationResult(case.case_id, not reasons, received, reasons, action_text)


def invoke_case(case: EvaluationCase) -> AIMessage:
    """Invoke the configured MainAgent model using production prompts and tools."""
    model = get_main_agent_llm().bind_tools(MAIN_AGENT_TOOLS)
    history_messages = [
        HumanMessage(content=content) if role == "user" else AIMessage(content=content)
        for role, content in case.history
    ]
    messages = [
        SystemMessage(content=MAIN_AGENT_SYSTEM),
        SystemMessage(content=case.trusted_context),
        *history_messages,
        HumanMessage(content=case.user_input),
    ]
    response = model.invoke(messages)
    try:
        parse_main_action(response)
        return response
    except Exception as first_error:
        repair = SystemMessage(content=(
            "Your previous MainAgent action was invalid. Return exactly one valid action. "
            f"Validation error: {str(first_error)[:500]}"
        ))
        return model.invoke([*messages, repair])


def main() -> None:
    """Run the fixed evaluation set and fail below the approved accuracy target."""
    parser = argparse.ArgumentParser(description="Evaluate the configured MainAgent model")
    parser.add_argument(
        "--critical-runs",
        type=int,
        default=3,
        help="Number of runs for critical cases; default: 3",
    )
    parser.add_argument(
        "--minimum-accuracy",
        type=float,
        default=0.90,
        help="Required overall pass rate; default: 0.90",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Run only the named case ID; may be repeated",
    )
    args = parser.parse_args()

    results = []
    selected_cases = [
        case for case in EVALUATION_CASES
        if not args.case or case.case_id in args.case
    ]
    if not selected_cases:
        raise SystemExit("No matching evaluation cases")
    for case in selected_cases:
        run_count = max(1, args.critical_runs) if case.critical else 1
        for run_index in range(run_count):
            result = evaluate_action(case, invoke_case(case))
            results.append(result)
            marker = "PASS" if result.passed else "FAIL"
            detail = "; ".join(result.reasons) if result.reasons else result.action
            print(f"[{marker}] {case.case_id} run {run_index + 1}: {detail}")
            if not result.passed:
                print(f"  Action: {result.payload}")

    passed = sum(result.passed for result in results)
    accuracy = passed / len(results)
    print(f"MainAgent evaluation: {passed}/{len(results)} = {accuracy:.1%}")
    if accuracy < args.minimum_accuracy:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
