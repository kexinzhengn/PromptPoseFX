"""Contract tests for Effect V2 generation and validation prompts."""

import re
from pathlib import Path

from agent.hard_validate import hard_validate_effect
from agent.prompts import (
    CODE_AGENT_SYSTEM,
    FRAMEWORK_CONSTRAINTS,
    MAIN_AGENT_SYSTEM,
    PRIVATE_CONVENTIONS,
    VALIDATE_SYSTEM,
)


BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_code_agent_prompt_teaches_sequential_frame_contract():
    """CodeAgent learns bounded state, passive redraws, and explicit resets."""
    combined = FRAMEWORK_CONSTRAINTS + PRIVATE_CONVENTIONS

    assert "static CONTRACT_VERSION = 2" in combined
    assert "frameData.isNewFrame" in combined
    assert "frameData.deltaFrames" in combined
    assert "frameData.discontinuity" in combined
    assert "bounded" in combined
    assert "Passive redraw" in combined
    assert "Never save cross-frame state" not in combined
    assert "Do not store a particle array" not in combined
    assert "reconstruct particles" not in combined.lower()
    assert "frameData.currentFrame - this.lastFrame > 1" not in combined
    assert "必须除以 frameDelta" not in combined


def test_code_agent_prompt_treats_constructor_as_optional():
    """The generation contract must match JavaScript's implicit constructor."""
    assert "`constructor()` is optional" in FRAMEWORK_CONSTRAINTS


def test_code_agent_prompt_separates_hard_and_optional_soft_validation():
    """Hard validation is universal; LLM review is reserved for complex work."""
    assert "Every `submit_code` call runs hard validation" in CODE_AGENT_SYSTEM
    assert "real Pose data" in CODE_AGENT_SYSTEM
    assert "passive redraw" in CODE_AGENT_SYSTEM
    assert "Simple creation" in CODE_AGENT_SYSTEM
    assert "Do not call `validate`" in CODE_AGENT_SYSTEM
    assert "Pose history" in CODE_AGENT_SYSTEM
    assert "call `validate` for soft semantic review" in CODE_AGENT_SYSTEM
    assert "Use for every new effect" not in CODE_AGENT_SYSTEM
    assert "Repair definite issues once" in CODE_AGENT_SYSTEM
    assert "soft-review limit was reached" in CODE_AGENT_SYSTEM


def test_validator_prompt_reviews_only_visual_semantics():
    """Soft review judges requested visuals without duplicating hard validation."""
    assert "joint binding" in VALIDATE_SYSTEM
    assert "trigger conditions" in VALIDATE_SYSTEM
    assert "color" in VALIDATE_SYSTEM
    assert "motion" in VALIDATE_SYSTEM
    assert "lifetime" in VALIDATE_SYSTEM
    assert "particle count" in VALIDATE_SYSTEM
    assert "CONFIG controls" in VALIDATE_SYSTEM
    assert "suggestions never affect `passed`" in VALIDATE_SYSTEM

    hard_validation_terms = (
        "static CONTRACT_VERSION = 2",
        "frameData.isNewFrame",
        "frameData.deltaFrames",
        "frameData.discontinuity",
        "Passive redraw",
        "sketch.random()",
        "randomSeed()",
        "noiseSeed()",
        "sketch.clear()",
        "sketch.background()",
        "Complete `sketch.` prefixes",
        "CONFIG structure",
    )
    assert all(term not in VALIDATE_SYSTEM for term in hard_validation_terms)


def test_validator_prompt_defers_random_and_retained_state_to_hard_validation():
    """A legal retained-random particle pattern is outside soft-review scope."""
    assert "Do not report framework-contract, API-safety, or runtime-state findings" in VALIDATE_SYSTEM
    assert "Random sampling and retained-state safety are hard-validation concerns" in VALIDATE_SYSTEM


def test_prompts_allow_saved_randomness_only_during_new_frame_updates():
    """Random particle attributes are sampled once, while shared seeds stay forbidden."""
    combined = FRAMEWORK_CONSTRAINTS + PRIVATE_CONVENTIONS + VALIDATE_SYSTEM

    assert "sketch.random()" in combined
    assert "frameData.isNewFrame" in combined
    assert "save" in combined.lower()
    assert "randomSeed()" in combined
    assert "noiseSeed()" in combined


def test_agent_and_validator_prompt_structure_is_english():
    """Agent instructions and product-facing output use English."""
    assert "## Role" in MAIN_AGENT_SYSTEM
    assert "## Available tools" in MAIN_AGENT_SYSTEM
    assert "Reply to product and Effect questions in concise English" in MAIN_AGENT_SYSTEM

    assert "## Core principles" in CODE_AGENT_SYSTEM
    assert "## Visual concept template" in CODE_AGENT_SYSTEM
    assert "## P5.js Effect framework constraints" in FRAMEWORK_CONSTRAINTS
    assert "## Common pitfalls" in PRIVATE_CONVENTIONS
    assert "## Review checklist" in VALIDATE_SYSTEM

    old_section_titles = (
        "## 角色",
        "## 可用工具",
        "## 核心规则",
        "## 基本原则",
        "## 编写要求",
        "## 检查项",
    )
    combined = "\n".join((
        MAIN_AGENT_SYSTEM,
        CODE_AGENT_SYSTEM,
        FRAMEWORK_CONSTRAINTS,
        PRIVATE_CONVENTIONS,
        VALIDATE_SYSTEM,
    ))
    assert all(title not in combined for title in old_section_titles)


def test_main_agent_prompt_preserves_editor_point_aliases_and_selection():
    assert "[Editor points]" in MAIN_AGENT_SYSTEM
    assert "[Editor selection]" in MAIN_AGENT_SYSTEM
    assert "Preserve a listed Point's alias" in MAIN_AGENT_SYSTEM
    assert '"here"' in MAIN_AGENT_SYSTEM
    assert "does not require every listed Point" in MAIN_AGENT_SYSTEM
    assert "expand to the exact joint" not in MAIN_AGENT_SYSTEM


def test_prompts_require_english_config_ui_copy():
    """Generated CONFIG labels, descriptions, and options must be English."""
    combined = FRAMEWORK_CONSTRAINTS + VALIDATE_SYSTEM

    assert "UI labels, descriptions, and option labels must be English" in combined
    assert "Chinese UI labels" not in combined


def test_code_agent_prompt_matches_the_four_type_config_contract():
    """CodeAgent must receive the same CONFIG rules enforced by static validation."""
    assert "Every parameter requires `default`, `type`, `label`, and `description`" in FRAMEWORK_CONSTRAINTS
    assert "A range parameter also requires finite numeric `min`, `max`, and `step`" in FRAMEWORK_CONSTRAINTS
    assert "A color default must use `#RRGGBB`" in FRAMEWORK_CONSTRAINTS
    assert "A boolean default must be `true` or `false`" in FRAMEWORK_CONSTRAINTS
    assert "A select parameter requires a non-empty" in FRAMEWORK_CONSTRAINTS
    assert "description?" not in FRAMEWORK_CONSTRAINTS


def test_complete_prompt_example_passes_sequential_hard_validation(pose_timeline_path):
    """The complete example taught to CodeAgent must execute under the real contract."""
    javascript_blocks = re.findall(
        r"```javascript\n(.*?)```",
        FRAMEWORK_CONSTRAINTS,
        flags=re.DOTALL,
    )

    result = hard_validate_effect(
        javascript_blocks[-1],
        pose_timeline_path,
        frames=60,
    )

    assert result.passed is True, result.errors
