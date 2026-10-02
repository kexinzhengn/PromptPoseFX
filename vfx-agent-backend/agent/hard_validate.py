"""Mandatory static and sequential-frame validation for PromptPoseFX Effects."""

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._runtime_simulator import run_node_render
from .control_bindings import extract_control_bindings
from .extract_config import extract_config
from .pre_validate import pre_validate


@dataclass(frozen=True)
class RenderSummary:
    """Observable result of simulated rendering."""

    frames: int
    draw_calls: dict[str, int]

    @property
    def total_draw_calls(self) -> int:
        return sum(self.draw_calls.values())


@dataclass(frozen=True)
class HardValidationResult:
    """Complete result returned by the hard-validation module."""

    passed: bool
    errors: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    render_summary: RenderSummary | None = None


def hard_validate_effect(
    code: str,
    pose_path: str | Path,
    *,
    frames: int = 60,
    timeout_seconds: float = 10.0,
    editor_state: dict[str, Any] | None = None,
    required_control_ids: set[str] | None = None,
    video_width: int = 640,
    video_height: int = 360,
) -> HardValidationResult:
    """Validate one Effect from source code through simulated Pose rendering."""
    static_passed, static_errors = pre_validate(code)
    if not static_passed:
        return HardValidationResult(passed=False, errors=static_errors)

    if required_control_ids:
        bindings, binding_errors = extract_control_bindings(code)
        if binding_errors:
            return HardValidationResult(passed=False, errors=binding_errors)
        bound_ids = {binding["id"] for binding in bindings.values()}
        state = editor_state or {}
        markers_by_id = {
            marker.get("id"): marker
            for marker in state.get("markers", [])
        }
        missing_ids = sorted(required_control_ids - bound_ids)
        if missing_ids:
            aliases_by_id = {
                control.get("id"): control.get("alias", control.get("id"))
                for control in [
                    *state.get("points", []),
                    *state.get("paths", []),
                    *markers_by_id.values(),
                ]
            }
            missing_labels = [
                aliases_by_id.get(control_id, control_id)
                for control_id in missing_ids
            ]
            return HardValidationResult(
                passed=False,
                errors=[
                    "CONTROL_BINDINGS is missing required editor controls: "
                    + ", ".join(missing_labels)
                ],
            )

    resolved_pose_path = Path(pose_path)
    if not resolved_pose_path.is_file():
        return HardValidationResult(
            passed=False,
            errors=[f"Pose data not found: {resolved_pose_path}"],
        )

    config_passed, params_json = extract_config(code)
    if not config_passed:
        return HardValidationResult(
            passed=False,
            errors=["CONFIG extraction failed"],
        )
    params = json.loads(params_json)

    code_fd, code_path = tempfile.mkstemp(suffix=".js", prefix="hard_validate_code_")
    params_fd, params_path = tempfile.mkstemp(suffix=".json", prefix="hard_validate_params_")
    editor_fd, editor_path = tempfile.mkstemp(
        suffix=".json",
        prefix="hard_validate_editor_",
    )
    os.close(code_fd)
    os.close(params_fd)
    os.close(editor_fd)
    try:
        Path(code_path).write_text(code, encoding="utf-8")
        Path(params_path).write_text(params_json, encoding="utf-8")
        Path(editor_path).write_text(
            json.dumps(editor_state or {"points": []}),
            encoding="utf-8",
        )
        render_result = run_node_render(
            code_path,
            params_path,
            str(resolved_pose_path),
            frames,
            timeout_seconds=timeout_seconds,
            editor_state_path=editor_path,
            video_width=video_width,
            video_height=video_height,
            required_control_ids=required_control_ids,
        )
    finally:
        for temporary_path in (code_path, params_path, editor_path):
            try:
                os.remove(temporary_path)
            except OSError:
                pass

    if render_result.get("error"):
        return HardValidationResult(
            passed=False,
            errors=[f"Runtime validation failed: {render_result['error']}"],
            params=params,
        )
    if render_result.get("sequentialFrameError"):
        return HardValidationResult(
            passed=False,
            errors=[str(render_result["sequentialFrameError"])],
            params=params,
        )
    if render_result.get("controlAccessError"):
        return HardValidationResult(
            passed=False,
            errors=[str(render_result["controlAccessError"])],
            params=params,
        )
    if render_result.get("controlSensitivityError"):
        return HardValidationResult(
            passed=False,
            errors=[str(render_result["controlSensitivityError"])],
            params=params,
        )

    summary = RenderSummary(
        frames=int(render_result.get("frames", frames)),
        draw_calls={
            name: int(count)
            for name, count in render_result.get("count", {}).items()
        },
    )
    if summary.total_draw_calls == 0:
        return HardValidationResult(
            passed=False,
            errors=["Runtime validation produced no draw calls"],
            params=params,
            render_summary=summary,
        )
    return HardValidationResult(
        passed=True,
        params=params,
        render_summary=summary,
    )
