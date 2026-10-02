"""Contracts for the repeatable real-model MainAgent evaluation suite."""

from langchain_core.messages import AIMessage

from scripts.evaluate_main_agent import (
    EVALUATION_CASES,
    PREVIOUS_CONTEXT,
    REQUIRED_CATEGORIES,
    EvaluationCase,
    evaluate_action,
)


def _tool_action(name: str, args: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[{
        "name": name,
        "args": args,
        "id": "eval-action",
    }])


def test_eval_suite_covers_every_approved_main_agent_category():
    categories = {case.category for case in EVALUATION_CASES}

    assert categories == REQUIRED_CATEGORIES
    assert len(EVALUATION_CASES) >= 22
    assert all(case.user_input for case in EVALUATION_CASES)


def test_eval_suite_covers_conflict_clarification_and_explicit_edit_intent():
    expected = {
        "conflicting_timeline_edit": "clarify",
        "contradictory_timeline_request": "clarify",
        "explicit_replacement_edit": "generate",
        "clear_additive_edit": "generate",
    }

    assert {
        case.case_id: case.expected_action
        for case in EVALUATION_CASES
        if case.case_id in expected
    } == expected
    conflict = next(
        case for case in EVALUATION_CASES
        if case.case_id == "conflicting_timeline_edit"
    )
    assert conflict.history
    assert "path2" in conflict.history[0][1]


def test_eval_suite_marks_correct_action_and_required_brief_terms():
    case = next(case for case in EVALUATION_CASES if case.case_id == "pinned_joint")
    message = _tool_action("generate_effect", {
        "user_description": (
            "Create a cyan pulse at right_wrist with a two-second cycle "
            "(60 frames at 30 FPS)."
        ),
        "requested_name": "Cyan Wrist Pulse",
    })

    result = evaluate_action(case, message)

    assert result.passed is True
    assert result.reasons == []


def test_eval_suite_reports_wrong_route_without_calling_product_tools():
    case = next(case for case in EVALUATION_CASES if case.case_id == "parameter_update")
    message = _tool_action("generate_effect", {
        "user_description": "Set the current Effect size to 40.",
    })

    result = evaluate_action(case, message)

    assert result.passed is False
    assert result.reasons == ["expected update_effect, received generate"]
    assert '"action":"generate"' in result.payload


def test_creative_case_requires_three_complete_options():
    case = next(case for case in EVALUATION_CASES if case.case_id == "creative_request")
    incomplete = _tool_action("ask_clarification", {
        "question": "Which idea should I create?",
        "options": [
            {
                "label": "Glow",
                "description": "A wrist glow.",
                "brief": {"user_description": "Create a wrist glow."},
            },
            {
                "label": "Trail",
                "description": "A wrist trail.",
                "brief": {"user_description": "Create a wrist trail."},
            },
        ],
    })

    result = evaluate_action(case, incomplete)

    assert result.passed is False
    assert "expected exactly 3 options" in result.reasons


def test_eval_suite_accepts_approved_semantic_alternatives():
    case = EvaluationCase(
        case_id="semantic-alternative",
        category="complete creation",
        user_input="Create it.",
        expected_action="respond",
        required_any=(("cannot", "does not have access", "unable"),),
    )

    result = evaluate_action(
        case,
        AIMessage(content="PromptPoseFX does not have access to video pixels."),
    )

    assert result.passed is True


def test_previous_effect_context_matches_backend_resolved_mention():
    assert '"effect_id": "ref-b"' in PREVIOUS_CONTEXT
    assert '"display_name": "Orbit Halo"' in PREVIOUS_CONTEXT


def test_eval_suite_accepts_color_and_duration_synonyms():
    case = EvaluationCase(
        case_id="synonyms",
        category="reasonable completion",
        user_input="Create it.",
        expected_action="generate",
        required_any=(("violet", "purple"), ("2 seconds", "two seconds")),
    )
    message = _tool_action("generate_effect", {
        "user_description": "Create a purple pulse lasting two seconds.",
    })

    assert evaluate_action(case, message).passed is True


def test_pose_only_limit_is_scored_by_capability_and_alternative_semantics():
    case = next(case for case in EVALUATION_CASES if case.case_id == "unsupported_pixels")
    message = AIMessage(content=(
        "PromptPoseFX works from pose coordinates, not video pixels. "
        "Choose a color instead and attach the glow to the shoulders."
    ))

    assert evaluate_action(case, message).passed is True


def test_eval_suite_accepts_transparency_hyphenation_and_direct_limit_wording():
    creation = next(case for case in EVALUATION_CASES if case.case_id == "complete_creation")
    creation_message = _tool_action("generate_effect", {
        "user_description": (
            "Create a cyan band between left_wrist and right_wrist that becomes "
            "progressively more transparent as the hands separate."
        ),
    })
    duration = next(case for case in EVALUATION_CASES if case.case_id == "seconds_conversion")
    duration_message = _tool_action("generate_effect", {
        "user_description": "Create a 2-second pulse (60 frames at 30 FPS).",
    })
    limit = next(case for case in EVALUATION_CASES if case.case_id == "unsupported_pixels")
    limit_message = AIMessage(content=(
        "I can't read clothing colors from the video. Choose a color and I can "
        "anchor the glow to the shoulders and hips."
    ))

    assert evaluate_action(creation, creation_message).passed is True
    assert evaluate_action(duration, duration_message).passed is True
    assert evaluate_action(limit, limit_message).passed is True
