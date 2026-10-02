"""MainAgent requirement-compiler prompt contract tests."""

from agent.prompts import MAIN_AGENT_SYSTEM


def test_prompt_exposes_only_v3_actions_and_one_side_effect_rule():
    assert "`ask_clarification`" in MAIN_AGENT_SYSTEM
    assert "`generate_effect`" in MAIN_AGENT_SYSTEM
    assert "`update_effect`" in MAIN_AGENT_SYSTEM
    assert "`inspect_effects`" in MAIN_AGENT_SYSTEM
    assert "at most one side-effecting action" in MAIN_AGENT_SYSTEM
    assert "`invoke_code_agent`" not in MAIN_AGENT_SYSTEM
    assert "`get_effect_detail`" not in MAIN_AGENT_SYSTEM


def test_prompt_compiles_chinese_requests_into_english_briefs():
    assert "The user may write in Chinese" in MAIN_AGENT_SYSTEM
    assert "user_description` and `requested_name` in English" in MAIN_AGENT_SYSTEM
    assert "left hand" in MAIN_AGENT_SYSTEM
    assert "left_wrist" in MAIN_AGENT_SYSTEM
    assert "p1" in MAIN_AGENT_SYSTEM


def test_prompt_asks_only_for_high_impact_ambiguity_and_offers_three_ideas():
    assert "high-impact ambiguity" in MAIN_AGENT_SYSTEM
    assert "Do not clarify color, exact count, opacity" in MAIN_AGENT_SYSTEM
    assert "exactly three complete, meaningfully different concepts" in MAIN_AGENT_SYSTEM
    assert "Add an effect" in MAIN_AGENT_SYSTEM


def test_prompt_requires_clarification_for_conflicting_or_destructive_edits():
    assert "Treat an edit request as a change to the current Effect, not a complete replacement" in MAIN_AGENT_SYSTEM
    assert "overlaps or conflicts with existing timing or behavior" in MAIN_AGENT_SYSTEM
    assert "add, modify, or replace" in MAIN_AGENT_SYSTEM
    assert "remove an existing anchor, stage, Path, trigger, or visual element" in MAIN_AGENT_SYSTEM
    assert "internally contradictory" in MAIN_AGENT_SYSTEM
    assert "Do not invent destructive intent" in MAIN_AGENT_SYSTEM
    assert '"only," "without," "instead," "remove," or "replace"' in MAIN_AGENT_SYSTEM


def test_prompt_routes_parameter_structural_and_mixed_edits():
    assert "existing control" in MAIN_AGENT_SYSTEM
    assert "use `update_effect`" in MAIN_AGENT_SYSTEM
    assert "has no matching current control" in MAIN_AGENT_SYSTEM
    assert "use `generate_effect`" in MAIN_AGENT_SYSTEM
    assert "include the explicit values in `parameter_updates`" in MAIN_AGENT_SYSTEM


def test_prompt_preserves_relative_semantics_and_converts_time():
    assert "preserve that semantic relationship" in MAIN_AGENT_SYSTEM
    assert "Do not invent a pixel offset" in MAIN_AGENT_SYSTEM
    assert "2 seconds (60 frames at 30 FPS)" in MAIN_AGENT_SYSTEM


def test_prompt_preserves_trusted_time_control_aliases():
    assert "[Editor time markers]" in MAIN_AGENT_SYSTEM
    assert "Preserve listed aliases such as `t1` and `t2`" in MAIN_AGENT_SYSTEM
    assert "do not replace them with their current frame numbers" in MAIN_AGENT_SYSTEM
    assert "do not treat the current Playhead frame as a persistent Time Marker" in MAIN_AGENT_SYSTEM
    assert "from t1 to t2" in MAIN_AGENT_SYSTEM
    assert "two Time Markers define the interval directly" in MAIN_AGENT_SYSTEM


def test_prompt_preserves_paths_as_drawn_content_and_spatial_references():
    assert "[Editor paths]" in MAIN_AGENT_SYSTEM
    assert "Preserve a listed Path alias such as `path1`" in MAIN_AGENT_SYSTEM
    assert "drawn visual content" in MAIN_AGENT_SYSTEM
    assert "spatial reference" in MAIN_AGENT_SYSTEM
    assert "selected Path" in MAIN_AGENT_SYSTEM


def test_prompt_handles_pose_only_limits_without_inventing_visual_access():
    assert "pixel sampling" in MAIN_AGENT_SYSTEM
    assert "clothing color" in MAIN_AGENT_SYSTEM
    assert "occlusion judgment" in MAIN_AGENT_SYSTEM
    assert "Pose-only alternative" in MAIN_AGENT_SYSTEM


def test_prompt_requires_track_selection_and_treats_history_as_reference_only():
    assert "select that Effect's track first" in MAIN_AGENT_SYSTEM
    assert "Copying an Effect is unsupported" in MAIN_AGENT_SYSTEM
    assert "Historical Effects may be used only as references" in MAIN_AGENT_SYSTEM


def test_prompt_routes_reference_questions_through_safe_inspection():
    assert "Why does this Effect move this way?" in MAIN_AGENT_SYSTEM
    assert "compare their safe summaries" in MAIN_AGENT_SYSTEM
    assert "three related complete concepts" in MAIN_AGENT_SYSTEM
    assert "must explicitly reference it again" in MAIN_AGENT_SYSTEM
