from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator
from langchain_core.tools import tool
from .hard_validate import hard_validate_effect
from .llm import call_llm_structured
from .prompts import VALIDATE_SYSTEM
from config import CODE_AGENT_MODEL, POSE_DATA_DIR
from .pose_data import PoseDataReader



class ValidateOutput(BaseModel):
    """Structured output returned by the validation tool."""
    passed: bool
    issues: list[str] = []
    suggestions: list[str] = []


class TodoItem(BaseModel):
    """One model-visible execution-plan item."""

    content: str
    status: Literal["pending", "in_progress", "completed"] = "pending"

    @field_validator("status", mode="before")
    @classmethod
    def normalize_unknown_status(cls, value: object) -> object:
        if value not in {"pending", "in_progress", "completed"}:
            return "pending"
        return value


@tool
def update_todo(items: list[TodoItem]) -> str:
    """
    Record and update the complete execution plan. Call once at the start of a round,
    then again whenever an item is completed. Use concise English workflow-stage names
    of at most two words, such as Analyze, Implement, Validate, Submit, or Fix.

    Args:
        items: Complete task list with content and pending, in_progress, or completed status.
    """
    warnings = []
    lines = []
    for i, t in enumerate(items, 1):
        content = t.content
        if len(content.split()) > 2:
            warnings.append(f"Item {i} uses more than two words; shorten it")
        if "(" in content or ":" in content:
            warnings.append(f"Item {i} contains punctuation or parentheses; remove them")
        status = t.status
        mark = {"completed": "[x]", "in_progress": "[~]", "pending": "[ ]"}.get(status, "[ ]")
        lines.append(f"{i}. {mark} {content}")
    result = "\n".join(lines) if lines else "(empty list)"
    if warnings:
        result += "\n\nWarning: " + "; ".join(warnings)
    return result

@tool
def submit_code(
    code: str,
    video_id: str = "",
    editor_state: dict | None = None,
    required_control_ids: list[str] | None = None,
) -> dict:
    """
    Submit final code through mandatory sequential-frame hard validation.
    Hard-valid code is recorded; invalid code returns errors for another repair attempt.

    Args:
        code: Complete JavaScript code containing class Effect.
        video_id: Video ID injected by the system for Pose-backed runtime validation.

    Returns:
        Success: {"submitted": True, "code": "..."}
        Failure: {"submitted": False, "errors": ["error 1", "error 2"]}
    """

    pose_path = Path(POSE_DATA_DIR) / video_id / "smoothed_landmark.json"
    validation = hard_validate_effect(
        code,
        pose_path,
        editor_state=editor_state,
        required_control_ids=set(required_control_ids or []),
    )
    if not validation.passed:
        return {"submitted": False, "errors": validation.errors}

    return {
        "submitted": True,
        "code": code,
    }


@tool
def validate(code: str, user_description: str = "") -> dict:
    """
    Soft-review code logic and confirm that it satisfies the user request with an LLM.
    Call this tool only for complex creation or modification.

    Args:
        code: Generated JavaScript code.
        user_description: Original user request.

    Returns:
        {"passed": true/false, "issues": [...], "suggestions": [...]}
    """
    result = call_llm_structured(
        model=CODE_AGENT_MODEL,
        system=VALIDATE_SYSTEM,
        user=f"User request:\n{user_description}\n\nCode:\n{code}",
        output_schema=ValidateOutput,
        temperature=0.2
    )
    return {
        "passed": result.passed,
        "issues": (result.issues or [])[:3],   # Return at most three issues.
        "suggestions": result.suggestions or []
    }


@tool
def get_pose_stats(video_id: str) -> dict:
    """
    Return pose-data statistics such as joint ranges and motion amplitude.

    Args:
        video_id: Video ID.
    """
    reader = PoseDataReader(video_id)
    return reader.get_stats()
