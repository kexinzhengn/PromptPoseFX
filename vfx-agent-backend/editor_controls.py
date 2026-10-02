"""Validated editor-owned spatial and temporal control data."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator, model_validator


CONTROL_ID_PATTERN = r"^[A-Za-z0-9_-]{1,128}$"
POINT_ALIAS_PATTERN = r"^p[1-9][0-9]*$"
MARKER_ALIAS_PATTERN = r"^t[1-9][0-9]*$"
PATH_ALIAS_PATTERN = r"^path[1-9][0-9]*$"
POSE_JOINT_NAMES = frozenset({
    "nose",
    "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "left_mouth", "right_mouth",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky",
    "left_index", "right_index", "left_thumb", "right_thumb",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel",
    "left_foot_index", "right_foot_index",
})


class ActiveInterval(BaseModel):
    """Inclusive video-frame interval in which one Effect is rendered."""

    model_config = ConfigDict(extra="forbid")

    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> "ActiveInterval":
        if self.start_frame > self.end_frame:
            raise ValueError("active_interval start_frame must not exceed end_frame")
        return self


class FixedPointSource(BaseModel):
    """One position fixed in normalized video coordinates."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["fixed"] = "fixed"
    x: FiniteFloat = Field(ge=0, le=1)
    y: FiniteFloat = Field(ge=0, le=1)


class JointPointSource(BaseModel):
    """One position derived from a Pose joint plus normalized video offset."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["joint"] = "joint"
    joint: str
    offset_x: FiniteFloat = Field(ge=-1, le=1)
    offset_y: FiniteFloat = Field(ge=-1, le=1)

    @field_validator("joint")
    @classmethod
    def validate_joint_name(cls, value: str) -> str:
        if value not in POSE_JOINT_NAMES:
            raise ValueError("joint must be a supported MediaPipe Pose landmark")
        return value


class PointControl(BaseModel):
    """One stable spatial control owned by an Effect Workspace."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=CONTROL_ID_PATTERN)
    alias: str = Field(pattern=POINT_ALIAS_PATTERN)
    source: Annotated[
        FixedPointSource | JointPointSource,
        Field(discriminator="type"),
    ]


class NormalizedPosition(BaseModel):
    """One position in normalized video coordinates."""

    model_config = ConfigDict(extra="forbid")

    x: FiniteFloat = Field(ge=0, le=1)
    y: FiniteFloat = Field(ge=0, le=1)


class PathControl(BaseModel):
    """One ordered polyline drawn in normalized video coordinates."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=CONTROL_ID_PATTERN)
    alias: str = Field(pattern=PATH_ALIAS_PATTERN)
    points: list[NormalizedPosition] = Field(min_length=2, max_length=512)


class TimeMarker(BaseModel):
    """One stable video-frame marker."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=CONTROL_ID_PATTERN)
    alias: str = Field(pattern=MARKER_ALIAS_PATTERN)
    frame: int = Field(ge=0)


class NextAlias(BaseModel):
    """Monotonic counters for the next user-facing aliases."""

    model_config = ConfigDict(extra="forbid")

    point: int = Field(ge=1)
    marker: int = Field(ge=1)
    path: int = Field(default=1, ge=1)


class EditorState(BaseModel):
    """Complete replaceable editor state for one Effect Workspace."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    video_id: str = Field(min_length=1, max_length=128)
    active_interval: ActiveInterval
    points: list[PointControl] = Field(default_factory=list, max_length=32)
    paths: list[PathControl] = Field(default_factory=list, max_length=16)
    markers: list[TimeMarker] = Field(default_factory=list, max_length=64)
    next_alias: NextAlias = Field(default_factory=lambda: NextAlias(point=1, marker=1))

    @model_validator(mode="after")
    def validate_identity_and_references(self) -> "EditorState":
        all_ids = [
            *(point.id for point in self.points),
            *(path.id for path in self.paths),
            *(marker.id for marker in self.markers),
        ]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("control IDs must be unique within an Effect Workspace")

        point_aliases = [point.alias for point in self.points]
        path_aliases = [path.alias for path in self.paths]
        marker_aliases = [marker.alias for marker in self.markers]
        if len(point_aliases) != len(set(point_aliases)):
            raise ValueError("Point aliases must be unique within an Effect Workspace")
        if len(marker_aliases) != len(set(marker_aliases)):
            raise ValueError("Time Marker aliases must be unique within an Effect Workspace")
        if len(path_aliases) != len(set(path_aliases)):
            raise ValueError("Path aliases must be unique within an Effect Workspace")
        if path_aliases and self.next_alias.path <= max(
            int(alias[4:]) for alias in path_aliases
        ):
            raise ValueError("next_alias.path must be greater than every Path alias")
        if marker_aliases and self.next_alias.marker <= max(
            int(alias[1:]) for alias in marker_aliases
        ):
            raise ValueError("next_alias.marker must be greater than every Time Marker alias")

        marker_frames = [marker.frame for marker in self.markers]
        if len(marker_frames) != len(set(marker_frames)):
            raise ValueError("Time Markers must use different frames within an Effect Workspace")

        return self


class EditorSelection(BaseModel):
    """Transient editor selection sent with one chat request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    current_frame: int = Field(ge=0)
    selected_point_id: str | None = Field(default=None, pattern=CONTROL_ID_PATTERN)
    selected_path_id: str | None = Field(default=None, pattern=CONTROL_ID_PATTERN)


class EditorContextSnapshot(BaseModel):
    """Trusted editor context fixed before an Agent run starts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    effect_id: str = Field(pattern=CONTROL_ID_PATTERN)
    video_id: str = Field(min_length=1, max_length=128)
    editor_revision: int = Field(ge=0)
    editor_state: EditorState
    selection: EditorSelection


def resolve_required_control_ids(
    text: str,
    editor_context: dict,
) -> list[str]:
    """Resolve explicitly named pN/tN aliases to backend-owned Stable IDs."""
    if not editor_context:
        return []
    context = EditorContextSnapshot.model_validate(editor_context)
    controls = [
        *context.editor_state.points,
        *context.editor_state.paths,
        *context.editor_state.markers,
    ]
    required_ids = []
    for control in controls:
        alias_pattern = rf"(?<![A-Za-z0-9_]){re.escape(control.alias)}(?![A-Za-z0-9_])"
        if re.search(alias_pattern, text, flags=re.IGNORECASE):
            required_ids.append(control.id)
    return required_ids


def empty_editor_state(video_id: str, total_frames: int) -> EditorState:
    """Create the initial editor state for a processed video."""
    if total_frames < 1:
        raise ValueError("total_frames must be positive")
    return EditorState(
        video_id=video_id,
        active_interval=ActiveInterval(start_frame=0, end_frame=total_frames - 1),
    )
