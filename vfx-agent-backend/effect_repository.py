"""Authoritative file-backed storage for Effect code, parameters, and metadata."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.config_contract import validate_static_config
from agent.control_bindings import extract_control_bindings
from editor_controls import (
    EditorContextSnapshot,
    EditorSelection,
    EditorState,
    empty_editor_state,
)


_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


@dataclass(frozen=True)
class EffectSnapshot:
    """One consistent Effect revision returned by the repository."""

    effect_id: str
    name: str
    status: str
    code: str
    params: dict[str, Any]
    created_at: str
    updated_at: str
    revision: int
    parameter_ranges: dict[str, dict[str, float]] = field(default_factory=dict)
    generation_metadata: dict[str, Any] = field(default_factory=dict)
    video_id: str = ""
    total_frames: int = 0
    editor_revision: int = 0
    editor_state: EditorState | None = None


class EffectNotFoundError(KeyError):
    """Raised when a requested Effect does not exist."""


class EffectParameterError(ValueError):
    """Raised when parameter updates do not satisfy the current Effect CONFIG."""


class EffectEditorStateError(ValueError):
    """Raised when editor state does not belong to the Effect Workspace."""


class EffectEditorRevisionError(EffectEditorStateError):
    """Raised when an editor update is based on an obsolete revision."""


class EffectRepository:
    """Coordinate Effect reads and writes through one process-wide storage lock."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = _lock_for(self.data_dir)

    def create_workspace(
        self,
        effect_id: str,
        video_id: str,
        total_frames: int,
    ) -> EffectSnapshot:
        """Create or return one pending Effect Workspace before code exists."""
        with self._lock:
            index = self._read_index()
            if effect_id in index:
                current = self._read_snapshot(effect_id, index)
                if current.editor_state is None and not current.video_id:
                    state = empty_editor_state(video_id, total_frames)
                    metadata = {
                        **index[effect_id],
                        "video_id": video_id,
                        "total_frames": total_frames,
                        "editor_revision": 0,
                        "editor_updated_at": datetime.now().isoformat(),
                    }
                    self._write_editor_state(effect_id, state, revision=0)
                    index[effect_id] = metadata
                    self._write_json_atomic(self._index_path(), index)
                    return self._snapshot(
                        effect_id,
                        current.code,
                        current.params,
                        metadata,
                        state,
                    )
                if current.video_id and current.video_id != video_id:
                    raise EffectEditorStateError("Effect Workspace belongs to another video")
                if current.total_frames and current.total_frames != total_frames:
                    raise EffectEditorStateError(
                        "Effect Workspace belongs to a different video frame range"
                    )
                return current

            state = empty_editor_state(video_id, total_frames)
            now = datetime.now().isoformat()
            metadata = {
                "name": self._allocate_unique_name("Untitled Effect", effect_id, index),
                "status": "pending",
                "created_at": now,
                "updated_at": now,
                "revision": 0,
                "generation_metadata": {},
                "video_id": video_id,
                "total_frames": total_frames,
                "editor_revision": 0,
            }
            self._write_editor_state(effect_id, state, revision=0)
            index[effect_id] = metadata
            self._write_json_atomic(self._index_path(), index)
            return self._snapshot(effect_id, "", {}, metadata, state)

    def replace_editor_state(
        self,
        effect_id: str,
        expected_revision: int,
        editor_state: EditorState | dict[str, Any],
    ) -> EffectSnapshot:
        """Replace complete editor state when the caller owns the current revision."""
        requested = EditorState.model_validate(editor_state)
        with self._lock:
            index = self._read_index()
            current = self._read_snapshot(effect_id, index)
            if requested.video_id != current.video_id:
                raise EffectEditorStateError("EditorState video_id does not match the Workspace")
            if requested.active_interval.end_frame >= current.total_frames:
                raise EffectEditorStateError("active_interval exceeds the video frame range")
            if any(marker.frame >= current.total_frames for marker in requested.markers):
                raise EffectEditorStateError("Time Marker exceeds the video frame range")
            if expected_revision != current.editor_revision:
                raise EffectEditorRevisionError(
                    f"Expected editor revision {expected_revision}, current revision is "
                    f"{current.editor_revision}"
                )
            if (
                current.editor_state is not None
                and requested.next_alias.marker < current.editor_state.next_alias.marker
            ):
                raise EffectEditorStateError("next_alias.marker cannot decrease")
            if current.editor_state is not None:
                current_control_types = {
                    **{point.id: "point" for point in current.editor_state.points},
                    **{path.id: "path" for path in current.editor_state.paths},
                    **{marker.id: "time_marker" for marker in current.editor_state.markers},
                }
                requested_control_types = {
                    **{point.id: "point" for point in requested.points},
                    **{path.id: "path" for path in requested.paths},
                    **{marker.id: "time_marker" for marker in requested.markers},
                }
                for control_id in current_control_types.keys() & requested_control_types.keys():
                    if current_control_types[control_id] != requested_control_types[control_id]:
                        raise EffectEditorStateError(
                            f"Control {control_id} cannot change type"
                        )
                current_markers = {
                    marker.id: marker for marker in current.editor_state.markers
                }
                for marker in requested.markers:
                    previous = current_markers.get(marker.id)
                    if previous is not None and marker.alias != previous.alias:
                        raise EffectEditorStateError(
                            f"Time Marker {marker.id} cannot change alias"
                        )
            self._validate_existing_control_dependencies(current, requested)

            next_revision = current.editor_revision + 1
            self._write_editor_state(effect_id, requested, revision=next_revision)
            metadata = {
                **index[effect_id],
                "editor_revision": next_revision,
                "editor_updated_at": datetime.now().isoformat(),
            }
            index[effect_id] = metadata
            self._write_json_atomic(self._index_path(), index)
            return self._snapshot(
                effect_id,
                current.code,
                current.params,
                metadata,
                requested,
            )

    @staticmethod
    def _validate_existing_control_dependencies(
        current: EffectSnapshot,
        requested: EditorState,
    ) -> None:
        """Keep controls required by saved Effect code structurally available."""
        if current.status not in {"active", "draft"}:
            return
        bindings, errors = extract_control_bindings(current.code)
        if errors:
            raise EffectEditorStateError("; ".join(errors))
        current_state = current.editor_state
        current_controls = {
            "point": {
                point.id: point for point in (current_state.points if current_state else [])
            },
            "path": {
                path.id: path for path in (current_state.paths if current_state else [])
            },
            "time_marker": {
                marker.id: marker for marker in (current_state.markers if current_state else [])
            },
        }
        requested_controls = {
            "point": {point.id: point for point in requested.points},
            "path": {path.id: path for path in requested.paths},
            "time_marker": {marker.id: marker for marker in requested.markers},
        }
        control_labels = {
            "point": "Point",
            "path": "Path",
            "time_marker": "Time Marker",
        }
        for binding in bindings.values():
            binding_type = binding["type"]
            control_id = binding["id"]
            requested_control = requested_controls[binding_type].get(control_id)
            if requested_control is None:
                raise EffectEditorStateError(
                    f"{control_labels[binding_type]} {control_id} cannot be deleted because "
                    "the current Effect uses it"
                )
            current_point = current_controls["point"].get(control_id)
            if (
                binding_type == "point"
                and current_point is not None
                and requested_control.source.type != current_point.source.type
            ):
                raise EffectEditorStateError(
                    f"Point {control_id} cannot change type because the current Effect uses it"
                )

    def get_editor_context_snapshot(
        self,
        effect_id: str,
        video_id: str,
        expected_revision: int,
        selection: EditorSelection | dict[str, Any],
    ) -> EditorContextSnapshot:
        """Fix one validated editor context before an Agent run starts."""
        requested_selection = EditorSelection.model_validate(selection)
        with self._lock:
            current = self._read_snapshot(effect_id, self._read_index())
            if current.editor_state is None or not current.video_id:
                raise EffectEditorStateError("Effect Workspace has no editor state")
            if video_id != current.video_id:
                raise EffectEditorStateError("Effect Workspace belongs to another video")
            if expected_revision != current.editor_revision:
                raise EffectEditorRevisionError(
                    f"Expected editor revision {expected_revision}, current revision is "
                    f"{current.editor_revision}"
                )
            if requested_selection.current_frame >= current.total_frames:
                raise EffectEditorStateError("Current frame exceeds the video frame range")
            point_ids = {point.id for point in current.editor_state.points}
            selected_point_id = requested_selection.selected_point_id
            if selected_point_id is not None and selected_point_id not in point_ids:
                raise EffectEditorStateError(
                    "Selected Point does not belong to the Effect Workspace"
                )
            path_ids = {path.id for path in current.editor_state.paths}
            selected_path_id = requested_selection.selected_path_id
            if selected_path_id is not None and selected_path_id not in path_ids:
                raise EffectEditorStateError(
                    "Selected Path does not belong to the Effect Workspace"
                )
            return EditorContextSnapshot(
                effect_id=effect_id,
                video_id=current.video_id,
                editor_revision=current.editor_revision,
                editor_state=current.editor_state.model_copy(deep=True),
                selection=requested_selection.model_copy(deep=True),
            )

    def save_effect(
        self,
        effect_id: str,
        code: str,
        params: dict[str, Any],
        requested_name: str,
        status: str = "active",
        generation_metadata: dict[str, Any] | None = None,
    ) -> EffectSnapshot:
        """Create or replace an Effect while allocating a globally unique name."""
        with self._lock:
            index = self._read_index()
            existing = index.get(effect_id, {})
            editor_state = self._read_editor_state(effect_id) if existing else None
            now = datetime.now().isoformat()
            name = self._allocate_unique_name(requested_name, effect_id, index)
            metadata = {
                **existing,
                "name": name,
                "status": status,
                "created_at": existing.get("created_at", now),
                "updated_at": now,
                "revision": int(existing.get("revision", 0)) + 1,
                "generation_metadata": generation_metadata or existing.get(
                    "generation_metadata", {}
                ),
                "parameter_ranges": {},
            }
            self._write_effect_files(effect_id, code, params)
            index[effect_id] = metadata
            self._write_json_atomic(self._index_path(), index)
            return self._snapshot(effect_id, code, params, metadata, editor_state)

    def patch_effect(
        self,
        effect_id: str,
        requested_name: str | None = None,
        parameter_updates: dict[str, Any] | None = None,
        parameter_range_updates: dict[str, dict[str, float]] | None = None,
    ) -> EffectSnapshot:
        """Update Effect metadata or parameters without replacing its code."""
        with self._lock:
            index = self._read_index()
            current = self._read_snapshot(effect_id, index)
            range_updates = self._validate_parameter_range_updates(
                current.code,
                parameter_range_updates or {},
            )
            parameter_ranges = {**current.parameter_ranges, **range_updates}
            updates = self._validate_parameter_updates(
                current.code,
                parameter_updates or {},
                parameter_ranges,
            )
            params = {**current.params, **updates}
            params = self._clamp_params_to_ranges(params, parameter_ranges)
            name = current.name
            if requested_name is not None:
                name = self._allocate_unique_name(requested_name, effect_id, index)
            now = datetime.now().isoformat()
            metadata = {
                **index[effect_id],
                "name": name,
                "updated_at": now,
                "revision": current.revision + 1,
                "parameter_ranges": parameter_ranges,
            }
            if updates or range_updates:
                self._write_json_atomic(self._effect_dir(effect_id) / "params.json", params)
            index[effect_id] = metadata
            self._write_json_atomic(self._index_path(), index)
            return self._snapshot(
                effect_id,
                current.code,
                params,
                metadata,
                current.editor_state,
            )

    def save_generated_effect(
        self,
        effect_id: str,
        code: str,
        requested_name: str,
        base_name: str = "",
        explicit_parameter_updates: dict[str, Any] | None = None,
        status: str = "active",
        generation_metadata: dict[str, Any] | None = None,
        editor_context: EditorContextSnapshot | None = None,
    ) -> EffectSnapshot:
        """Save generated code while preserving compatible edits made during generation."""
        with self._lock:
            config, errors = validate_static_config(code)
            if errors:
                raise EffectParameterError(f"Effect CONFIG is invalid: {'; '.join(errors)}")
            explicit_updates = self._validate_parameter_updates(
                code,
                explicit_parameter_updates or {},
            )

            index = self._read_index()
            try:
                current = self._read_snapshot(effect_id, index)
            except EffectNotFoundError:
                current = None
            self._validate_generated_control_dependencies(
                code,
                current,
                editor_context,
            )
            parameter_ranges = self._compatible_parameter_ranges(
                code,
                current.parameter_ranges if current is not None else {},
            )

            params = {
                key: metadata["default"]
                for key, metadata in config.items()
            }
            if current is not None:
                current_config, current_config_errors = validate_static_config(current.code)
                if current_config_errors:
                    current_config = {}
                for key, value in current.params.items():
                    if key not in config:
                        continue
                    if current_config.get(key, {}).get("type") != config[key].get("type"):
                        continue
                    try:
                        self._validate_parameter_updates(
                            code,
                            {key: value},
                            parameter_ranges,
                        )
                    except EffectParameterError:
                        continue
                    params[key] = value
            params.update(explicit_updates)

            for key, value in explicit_updates.items():
                bounds = parameter_ranges.get(key)
                if bounds is not None and not bounds["min"] <= value <= bounds["max"]:
                    parameter_ranges.pop(key)
            params = self._clamp_params_to_ranges(params, parameter_ranges)

            name_candidate = requested_name
            if (
                current is not None
                and current.status != "pending"
                and current.name != base_name
            ):
                name_candidate = current.name
            name = self._allocate_unique_name(name_candidate, effect_id, index)

            now = datetime.now().isoformat()
            previous_metadata = index.get(effect_id, {})
            metadata = {
                **previous_metadata,
                "name": name,
                "status": status,
                "created_at": previous_metadata.get("created_at", now),
                "updated_at": now,
                "revision": int(previous_metadata.get("revision", 0)) + 1,
                "generation_metadata": generation_metadata or {},
                "parameter_ranges": parameter_ranges,
            }
            self._write_effect_files(effect_id, code, params)
            index[effect_id] = metadata
            self._write_json_atomic(self._index_path(), index)
            return self._snapshot(
                effect_id,
                code,
                params,
                metadata,
                current.editor_state if current is not None else None,
            )

    @staticmethod
    def _validate_generated_control_dependencies(
        code: str,
        current: EffectSnapshot | None,
        editor_context: EditorContextSnapshot | None,
    ) -> None:
        bindings, errors = extract_control_bindings(code)
        if errors:
            raise EffectEditorStateError("; ".join(errors))
        if not bindings:
            return
        if current is None or current.editor_state is None or editor_context is None:
            raise EffectEditorStateError(
                "Generated Effect control bindings have no trusted Editor context"
            )

        started_controls = {
            "point": {
                point.id: point for point in editor_context.editor_state.points
            },
            "path": {
                path.id: path for path in editor_context.editor_state.paths
            },
            "time_marker": {
                marker.id: marker for marker in editor_context.editor_state.markers
            },
        }
        current_controls = {
            "point": {
                point.id: point for point in current.editor_state.points
            },
            "path": {
                path.id: path for path in current.editor_state.paths
            },
            "time_marker": {
                marker.id: marker for marker in current.editor_state.markers
            },
        }
        control_labels = {
            "point": "Point",
            "path": "Path",
            "time_marker": "Time Marker",
        }
        for binding in bindings.values():
            binding_type = binding["type"]
            control_id = binding["id"]
            label = control_labels[binding_type]
            started_control = started_controls[binding_type].get(control_id)
            if started_control is None:
                raise EffectEditorStateError(
                    f"Generated Effect references an unauthorized {label}: {control_id}"
                )
            current_control = current_controls[binding_type].get(control_id)
            if current_control is None:
                raise EffectEditorStateError(
                    f"Generated Effect references a {label} that no longer exists: "
                    f"{control_id}"
                )
            if (
                binding_type == "point"
                and current_control.source.type != started_control.source.type
            ):
                raise EffectEditorStateError(
                    f"Generated Effect Point changed type during generation: {control_id}"
                )

    def save_draft_effect(
        self,
        effect_id: str,
        code: str,
        requested_name: str,
        base_name: str = "",
        generation_metadata: dict[str, Any] | None = None,
        editor_context: EditorContextSnapshot | None = None,
    ) -> EffectSnapshot:
        """Save the best generated draft and merge edits when its CONFIG is usable."""
        try:
            return self.save_generated_effect(
                effect_id=effect_id,
                code=code,
                requested_name=requested_name,
                base_name=base_name,
                status="draft",
                generation_metadata=generation_metadata,
                editor_context=editor_context,
            )
        except EffectParameterError:
            pass

        with self._lock:
            index = self._read_index()
            try:
                current = self._read_snapshot(effect_id, index)
            except EffectNotFoundError:
                current = None
            self._validate_generated_control_dependencies(
                code,
                current,
                editor_context,
            )
            name_candidate = requested_name
            if current is not None and current.name != base_name:
                name_candidate = current.name
            name = self._allocate_unique_name(name_candidate, effect_id, index)
            now = datetime.now().isoformat()
            previous_metadata = index.get(effect_id, {})
            metadata = {
                **previous_metadata,
                "name": name,
                "status": "draft",
                "created_at": previous_metadata.get("created_at", now),
                "updated_at": now,
                "revision": int(previous_metadata.get("revision", 0)) + 1,
                "generation_metadata": generation_metadata or {},
                "parameter_ranges": {},
            }
            self._write_effect_files(effect_id, code, {})
            index[effect_id] = metadata
            self._write_json_atomic(self._index_path(), index)
            return self._snapshot(
                effect_id,
                code,
                {},
                metadata,
                current.editor_state if current is not None else None,
            )

    @staticmethod
    def _validate_parameter_updates(
        code: str,
        updates: dict[str, Any],
        parameter_ranges: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, Any]:
        if not updates:
            return {}
        config, errors = validate_static_config(code)
        if errors:
            raise EffectParameterError(f"Effect CONFIG is invalid: {'; '.join(errors)}")

        for key, value in updates.items():
            metadata = config.get(key)
            if metadata is None:
                raise EffectParameterError(f"Unknown Effect parameter: {key}")
            param_type = metadata["type"]
            if param_type == "range":
                if not EffectRepository._is_number(value):
                    raise EffectParameterError(f"Parameter {key} must be a finite number")
                bounds = (parameter_ranges or {}).get(key, metadata)
                if value < bounds["min"] or value > bounds["max"]:
                    raise EffectParameterError(
                        f"Parameter {key} must be between {bounds['min']} and {bounds['max']}"
                    )
            elif param_type == "color":
                if not isinstance(value, str) or re.fullmatch(r"#[0-9A-Fa-f]{6}", value) is None:
                    raise EffectParameterError(f"Parameter {key} must be a #RRGGBB color")
            elif param_type == "boolean":
                if not isinstance(value, bool):
                    raise EffectParameterError(f"Parameter {key} must be a boolean")
            elif param_type == "select":
                option_values = [option["value"] for option in metadata["options"]]
                if not any(
                    EffectRepository._same_primitive(value, option_value)
                    for option_value in option_values
                ):
                    raise EffectParameterError(
                        f"Parameter {key} must match one configured option value"
                    )
        return dict(updates)

    @staticmethod
    def _validate_parameter_range_updates(
        code: str,
        updates: dict[str, dict[str, float]],
    ) -> dict[str, dict[str, float]]:
        if not updates:
            return {}
        config, errors = validate_static_config(code)
        if errors:
            raise EffectParameterError(f"Effect CONFIG is invalid: {'; '.join(errors)}")

        validated: dict[str, dict[str, float]] = {}
        for key, bounds in updates.items():
            metadata = config.get(key)
            if metadata is None:
                raise EffectParameterError(f"Unknown Effect parameter: {key}")
            if metadata["type"] != "range":
                raise EffectParameterError(f"Parameter {key} does not support a slider range")
            if not isinstance(bounds, dict):
                raise EffectParameterError(f"Slider range {key} must contain min and max")
            minimum = bounds.get("min")
            maximum = bounds.get("max")
            if not EffectRepository._is_number(minimum) or not EffectRepository._is_number(maximum):
                raise EffectParameterError(f"Slider range {key} must use finite numbers")
            if minimum >= maximum:
                raise EffectParameterError(f"Slider range {key} min must be less than max")
            validated[key] = {"min": minimum, "max": maximum}
        return validated

    @staticmethod
    def _compatible_parameter_ranges(
        code: str,
        ranges: dict[str, dict[str, float]],
    ) -> dict[str, dict[str, float]]:
        compatible: dict[str, dict[str, float]] = {}
        for key, bounds in ranges.items():
            try:
                compatible.update(
                    EffectRepository._validate_parameter_range_updates(code, {key: bounds})
                )
            except EffectParameterError:
                continue
        return compatible

    @staticmethod
    def _clamp_params_to_ranges(
        params: dict[str, Any],
        ranges: dict[str, dict[str, float]],
    ) -> dict[str, Any]:
        clamped = dict(params)
        for key, bounds in ranges.items():
            value = clamped.get(key)
            if EffectRepository._is_number(value):
                clamped[key] = min(bounds["max"], max(bounds["min"], value))
        return clamped

    @staticmethod
    def _is_number(value: Any) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )

    @staticmethod
    def _same_primitive(first: Any, second: Any) -> bool:
        if EffectRepository._is_number(first) and EffectRepository._is_number(second):
            return first == second
        return type(first) is type(second) and first == second

    def get(self, effect_id: str) -> EffectSnapshot | None:
        """Return the latest Effect snapshot or None when it does not exist."""
        with self._lock:
            try:
                return self._read_snapshot(effect_id, self._read_index())
            except EffectNotFoundError:
                return None

    def list(self) -> list[EffectSnapshot]:
        """Return the latest snapshot for every complete Effect."""
        with self._lock:
            index = self._read_index()
            snapshots = []
            for effect_id in index:
                try:
                    snapshots.append(self._read_snapshot(effect_id, index))
                except EffectNotFoundError:
                    continue
            return snapshots

    def delete(self, effect_id: str) -> bool:
        """Delete one Effect directory and its index entry."""
        with self._lock:
            index = self._read_index()
            effect_dir = self._effect_dir(effect_id)
            if effect_id not in index and not effect_dir.exists():
                return False
            if effect_dir.exists():
                import shutil

                shutil.rmtree(effect_dir)
            index.pop(effect_id, None)
            self._write_json_atomic(self._index_path(), index)
            return True

    def _allocate_unique_name(
        self,
        requested_name: str,
        effect_id: str,
        index: dict[str, dict[str, Any]],
    ) -> str:
        base = requested_name.strip() or "Untitled Effect"
        used = {
            str(metadata.get("name", "")).strip().casefold()
            for other_id, metadata in index.items()
            if other_id != effect_id
        }
        if base.casefold() not in used:
            return base
        suffix = 2
        while f"{base} {suffix}".casefold() in used:
            suffix += 1
        return f"{base} {suffix}"

    def _read_snapshot(
        self,
        effect_id: str,
        index: dict[str, dict[str, Any]],
    ) -> EffectSnapshot:
        metadata = index.get(effect_id)
        effect_dir = self._effect_dir(effect_id)
        try:
            if metadata is None:
                raise EffectNotFoundError(effect_id)
            if metadata.get("status") == "pending":
                code = ""
                params = {}
            else:
                code = (effect_dir / "code.js").read_text(encoding="utf-8")
                params = json.loads((effect_dir / "params.json").read_text(encoding="utf-8"))
            editor_state = self._read_editor_state(effect_id)
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            raise EffectNotFoundError(effect_id) from None
        if not isinstance(params, dict):
            raise EffectNotFoundError(effect_id)
        return self._snapshot(effect_id, code, params, metadata, editor_state)

    @staticmethod
    def _snapshot(
        effect_id: str,
        code: str,
        params: dict[str, Any],
        metadata: dict[str, Any],
        editor_state: EditorState | None = None,
    ) -> EffectSnapshot:
        return EffectSnapshot(
            effect_id=effect_id,
            name=str(metadata.get("name", "Untitled Effect")),
            status=str(metadata.get("status", "active")),
            code=code,
            params=dict(params),
            parameter_ranges={
                key: dict(bounds)
                for key, bounds in metadata.get("parameter_ranges", {}).items()
            },
            created_at=str(metadata.get("created_at", "")),
            updated_at=str(metadata.get("updated_at", "")),
            revision=int(metadata.get("revision", 0)),
            generation_metadata=dict(metadata.get("generation_metadata", {})),
            video_id=str(metadata.get("video_id", "")),
            total_frames=int(metadata.get("total_frames", 0)),
            editor_revision=int(metadata.get("editor_revision", 0)),
            editor_state=editor_state,
        )

    def _read_editor_state(self, effect_id: str) -> EditorState | None:
        path = self._effect_dir(effect_id) / "editor_state.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("EditorState must be an object")
        payload.pop("revision", None)
        payload.pop("spans", None)
        if payload.get("schema_version") == 1:
            payload["schema_version"] = 2
        return EditorState.model_validate(payload)

    def _write_editor_state(
        self,
        effect_id: str,
        editor_state: EditorState,
        revision: int,
    ) -> None:
        payload = editor_state.model_dump(mode="json")
        payload["revision"] = revision
        self._write_json_atomic(
            self._effect_dir(effect_id) / "editor_state.json",
            payload,
        )

    def _write_effect_files(
        self,
        effect_id: str,
        code: str,
        params: dict[str, Any],
    ) -> None:
        effect_dir = self._effect_dir(effect_id)
        effect_dir.mkdir(parents=True, exist_ok=True)
        self._write_text_atomic(effect_dir / "code.js", code)
        self._write_json_atomic(effect_dir / "params.json", params)

    def _read_index(self) -> dict[str, dict[str, Any]]:
        try:
            value = json.loads(self._index_path().read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _index_path(self) -> Path:
        return self.data_dir / "effect_index.json"

    def _effect_dir(self, effect_id: str) -> Path:
        return self.data_dir / effect_id

    @staticmethod
    def _write_json_atomic(path: Path, value: Any) -> None:
        text = json.dumps(value, ensure_ascii=False, indent=2)
        EffectRepository._write_text_atomic(path, text)

    @staticmethod
    def _write_text_atomic(path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
                temporary_file.write(value)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, path)
        except Exception:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
            raise
