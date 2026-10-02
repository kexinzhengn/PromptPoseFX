"""EffectRepository tests for atomic Effect metadata and parameter updates."""

import json

import pytest

from editor_controls import empty_editor_state
from effect_repository import (
    EffectEditorRevisionError,
    EffectEditorStateError,
    EffectParameterError,
    EffectRepository,
)


EFFECT_CODE = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {
    size: { default: 20, type: 'range', min: 5, max: 50, step: 1, label: 'Size', description: 'Controls the size' },
    color: { default: '#FF00AA', type: 'color', label: 'Color', description: 'Controls the color' },
    enabled: { default: true, type: 'boolean', label: 'Enabled', description: 'Shows the effect' },
    mode: {
      default: 2,
      type: 'select',
      label: 'Mode',
      description: 'Controls the rendering mode',
      options: [{ label: 'Soft', value: 1 }, { label: 'Bold', value: 2 }],
    },
  };
  constructor() {}
  display(sketch, frameData, params) {}
}"""

UPDATED_EFFECT_CODE = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {
    size: { default: 12, type: 'range', min: 5, max: 50, step: 1, label: 'Size', description: 'Controls the size' },
    color: {
      default: 'soft',
      type: 'select',
      label: 'Style',
      description: 'Controls the visual style',
      options: [
        { label: 'Soft', value: 'soft' },
        { label: 'Legacy Color', value: '#FF00AA' },
      ],
    },
    strength: { default: 3, type: 'range', min: 1, max: 10, step: 1, label: 'Strength', description: 'Controls the strength' },
  };
  constructor() {}
  display(sketch, frameData, params) {}
}"""

POINT_EFFECT_CODE = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONTROL_BINDINGS = {
    anchor: { type: 'point', id: 'point-1' },
  };
  static CONFIG = {
    size: { default: 20, type: 'range', min: 5, max: 50, step: 1, label: 'Size', description: 'Controls the size' },
  };
  display(sketch, frameData, params) {
    const anchor = frameData.controls.getPoint('anchor');
    sketch.ellipse(anchor.x, anchor.y, params.size, params.size);
  }
}"""

TIME_EFFECT_CODE = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONTROL_BINDINGS = {
    start: { type: 'time_marker', id: 'marker-1' },
    end: { type: 'time_marker', id: 'marker-2' },
  };
  static CONFIG = {};
  display(sketch, frameData, params) {
    const start = frameData.controls.getTimeMarker('start');
    const end = frameData.controls.getTimeMarker('end');
    if (frameData.currentFrame >= start.frame && frameData.currentFrame <= end.frame) {
      sketch.ellipse(10, 10, 5, 5);
    }
  }
}"""

PATH_EFFECT_CODE = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONTROL_BINDINGS = {
    guide: { type: 'path', id: 'path-1' },
  };
  static CONFIG = {};
  display(sketch, frameData, params) {
    const guide = frameData.controls.getPath('guide');
    const point = guide.sample(0.5);
    sketch.ellipse(point.x, point.y, 5, 5);
  }
}"""


def test_repository_reads_legacy_editor_state_as_marker_only_schema(tmp_path):
    repository = EffectRepository(tmp_path)
    repository.create_workspace("legacy", "video-1", 180)
    state_path = tmp_path / "legacy" / "editor_state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload.update({
        "schema_version": 1,
        "markers": [
            {"id": "marker-1", "alias": "t1", "frame": 30},
            {"id": "marker-2", "alias": "t2", "frame": 90},
        ],
        "spans": [{
            "id": "span-1",
            "start_marker_id": "marker-1",
            "end_marker_id": "marker-2",
        }],
        "next_alias": {"point": 1, "marker": 3},
    })
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = EffectRepository(tmp_path).get("legacy")

    assert loaded.editor_state.schema_version == 2
    assert [marker.alias for marker in loaded.editor_state.markers] == ["t1", "t2"]
    assert not hasattr(loaded.editor_state, "spans")


def test_bound_path_can_be_redrawn_but_not_deleted(tmp_path):
    repository = EffectRepository(tmp_path)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=180)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["paths"] = [{
        "id": "path-1",
        "alias": "path1",
        "points": [{"x": 0.1, "y": 0.2}, {"x": 0.8, "y": 0.7}],
    }]
    editor_state["next_alias"]["path"] = 2
    saved = repository.replace_editor_state("workspace-1", 0, editor_state)
    context = repository.get_editor_context_snapshot(
        "workspace-1",
        "video-1",
        saved.editor_revision,
        {"current_frame": 0},
    )
    repository.save_generated_effect(
        "workspace-1",
        PATH_EFFECT_CODE,
        "Path Effect",
        editor_context=context,
    )

    redrawn = saved.editor_state.model_dump(mode="json")
    redrawn["paths"][0]["points"] = [
        {"x": 0.2, "y": 0.8},
        {"x": 0.7, "y": 0.3},
    ]
    updated = repository.replace_editor_state(
        "workspace-1",
        saved.editor_revision,
        redrawn,
    )

    assert updated.editor_state.paths[0].id == "path-1"
    assert updated.editor_state.paths[0].alias == "path1"

    deleted = updated.editor_state.model_dump(mode="json")
    deleted["paths"] = []
    with pytest.raises(
        EffectEditorStateError,
        match="Path path-1 cannot be deleted because the current Effect uses it",
    ):
        repository.replace_editor_state(
            "workspace-1",
            updated.editor_revision,
            deleted,
        )


def test_names_are_unique_across_active_draft_and_repository_instances(tmp_path):
    first = EffectRepository(tmp_path)
    second = EffectRepository(tmp_path)

    saved_first = first.save_effect("active-1", "code-a", {}, "  Aurora  ", "active")
    saved_second = second.save_effect("draft-1", "code-b", {}, "aurora", "draft")
    renamed = first.patch_effect("draft-1", requested_name=" AURORA ")

    assert saved_first.name == "Aurora"
    assert saved_second.name == "aurora 2"
    assert renamed.name == "AURORA 2"
    generated = second.save_generated_effect(
        "active-2",
        EFFECT_CODE,
        "aurora",
    )
    assert generated.name == "aurora 3"


def test_parameter_patch_validates_config_and_never_changes_code(tmp_path):
    repository = EffectRepository(tmp_path)
    repository.save_effect(
        "effect-1",
        EFFECT_CODE,
        {"size": 20, "color": "#FF00AA", "enabled": True, "mode": 2},
        "Adjustable",
    )

    updated = repository.patch_effect(
        "effect-1",
        parameter_updates={
            "size": 40,
            "color": "#00AAFF",
            "enabled": False,
            "mode": 1,
        },
    )

    assert updated.params == {
        "size": 40,
        "color": "#00AAFF",
        "enabled": False,
        "mode": 1,
    }
    assert updated.code == EFFECT_CODE

    invalid_updates = [
        {"size": "40"},
        {"size": 51},
        {"color": "blue"},
        {"enabled": 1},
        {"mode": True},
        {"mode": 3},
        {"missing": 1},
    ]
    for parameter_updates in invalid_updates:
        with pytest.raises(EffectParameterError):
            repository.patch_effect("effect-1", parameter_updates=parameter_updates)

    assert repository.get("effect-1").params == updated.params


def test_parameter_range_patch_persists_and_clamps_the_current_value(tmp_path):
    repository = EffectRepository(tmp_path)
    repository.save_effect(
        "effect-1",
        EFFECT_CODE,
        {"size": 20, "color": "#FF00AA", "enabled": True, "mode": 2},
        "Adjustable",
    )

    updated = repository.patch_effect(
        "effect-1",
        parameter_range_updates={"size": {"min": 30, "max": 45}},
    )

    assert updated.parameter_ranges == {"size": {"min": 30, "max": 45}}
    assert updated.params["size"] == 30
    reloaded = EffectRepository(tmp_path).get("effect-1")
    assert reloaded.parameter_ranges == updated.parameter_ranges
    assert reloaded.params["size"] == 30


def test_parameter_range_may_extend_beyond_config_and_becomes_the_effective_bounds(tmp_path):
    repository = EffectRepository(tmp_path)
    repository.save_effect("effect-1", EFFECT_CODE, {"size": 20}, "Adjustable")

    ranged = repository.patch_effect(
        "effect-1",
        parameter_range_updates={"size": {"min": 60, "max": 100}},
    )
    updated = repository.patch_effect(
        "effect-1",
        parameter_updates={"size": 75},
    )

    assert ranged.parameter_ranges == {"size": {"min": 60, "max": 100}}
    assert ranged.params["size"] == 60
    assert updated.params["size"] == 75
    assert EffectRepository(tmp_path).get("effect-1").parameter_ranges == ranged.parameter_ranges


@pytest.mark.parametrize(
    "range_updates",
    [
        {"size": {"min": 30, "max": 30}},
        {"size": {"min": True, "max": 40}},
        {"size": {"min": float("-inf"), "max": 40}},
        {"color": {"min": 0, "max": 1}},
        {"missing": {"min": 0, "max": 1}},
    ],
)
def test_parameter_range_patch_rejects_invalid_ranges_without_partial_save(
    tmp_path,
    range_updates,
):
    repository = EffectRepository(tmp_path)
    repository.save_effect("effect-1", EFFECT_CODE, {"size": 20}, "Original")

    with pytest.raises(EffectParameterError):
        repository.patch_effect(
            "effect-1",
            requested_name="Should Not Save",
            parameter_range_updates=range_updates,
        )

    stored = repository.get("effect-1")
    assert stored.name == "Original"
    assert stored.params == {"size": 20}
    assert stored.parameter_ranges == {}


def test_generation_save_keeps_only_compatible_parameter_ranges(tmp_path):
    repository = EffectRepository(tmp_path)
    repository.save_effect(
        "effect-1",
        EFFECT_CODE,
        {"size": 20, "color": "#FF00AA", "enabled": True, "mode": 2},
        "Original",
    )
    repository.patch_effect(
        "effect-1",
        parameter_range_updates={"size": {"min": 10, "max": 45}},
    )

    compatible = repository.save_generated_effect(
        "effect-1",
        UPDATED_EFFECT_CODE,
        "Updated",
    )
    assert compatible.parameter_ranges == {"size": {"min": 10, "max": 45}}

    regenerated_code = UPDATED_EFFECT_CODE.replace(
        "default: 12, type: 'range', min: 5, max: 50",
        "default: 25, type: 'range', min: 20, max: 40",
    )
    preserved = repository.save_generated_effect(
        "effect-1",
        regenerated_code,
        "Updated Again",
    )
    assert preserved.parameter_ranges == {"size": {"min": 10, "max": 45}}


def test_generation_save_merges_new_code_with_latest_user_edits(tmp_path):
    repository = EffectRepository(tmp_path)
    repository.save_effect(
        "effect-1",
        EFFECT_CODE,
        {"size": 20, "color": "#FF00AA", "enabled": True, "mode": 2},
        "Original",
    )
    repository.patch_effect("effect-1", requested_name="Renamed by user")
    repository.patch_effect("effect-1", parameter_updates={"size": 40})

    merged = repository.save_generated_effect(
        effect_id="effect-1",
        code=UPDATED_EFFECT_CODE,
        requested_name="Generated Name",
        base_name="Original",
        explicit_parameter_updates={"strength": 7},
        status="active",
        generation_metadata={"request_id": "run-1"},
    )

    assert merged.name == "Renamed by user"
    assert merged.code == UPDATED_EFFECT_CODE
    assert merged.params == {"size": 40, "color": "soft", "strength": 7}
    assert merged.generation_metadata == {"request_id": "run-1"}


def test_generation_save_accepts_a_bound_point_moved_after_run_start(tmp_path):
    repository = EffectRepository(tmp_path)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    initial_state = created.editor_state.model_dump(mode="json")
    initial_state["points"] = [{
        "id": "point-1",
        "alias": "p1",
        "source": {"type": "fixed", "x": 0.2, "y": 0.3},
    }]
    initial_state["next_alias"]["point"] = 2
    saved_point = repository.replace_editor_state("workspace-1", 0, initial_state)
    run_context = repository.get_editor_context_snapshot(
        "workspace-1",
        "video-1",
        saved_point.editor_revision,
        {"current_frame": 42, "selected_point_id": "point-1"},
    )
    moved_state = saved_point.editor_state.model_dump(mode="json")
    moved_state["points"][0]["source"]["x"] = 0.8
    repository.replace_editor_state(
        "workspace-1",
        saved_point.editor_revision,
        moved_state,
    )

    generated = repository.save_generated_effect(
        effect_id="workspace-1",
        code=POINT_EFFECT_CODE,
        requested_name="Moving Point",
        editor_context=run_context,
    )

    assert generated.status == "active"
    assert generated.editor_revision == 2
    assert generated.editor_state.points[0].source.x == 0.8


def test_generation_save_rejects_a_bound_point_deleted_after_run_start(tmp_path):
    repository = EffectRepository(tmp_path)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    initial_state = created.editor_state.model_dump(mode="json")
    initial_state["points"] = [{
        "id": "point-1",
        "alias": "p1",
        "source": {"type": "fixed", "x": 0.2, "y": 0.3},
    }]
    initial_state["next_alias"]["point"] = 2
    saved_point = repository.replace_editor_state("workspace-1", 0, initial_state)
    run_context = repository.get_editor_context_snapshot(
        "workspace-1",
        "video-1",
        saved_point.editor_revision,
        {"current_frame": 42, "selected_point_id": "point-1"},
    )
    deleted_state = saved_point.editor_state.model_dump(mode="json")
    deleted_state["points"] = []
    repository.replace_editor_state(
        "workspace-1",
        saved_point.editor_revision,
        deleted_state,
    )

    with pytest.raises(
        EffectEditorStateError,
        match="Generated Effect references a Point that no longer exists: point-1",
    ):
        repository.save_generated_effect(
            effect_id="workspace-1",
            code=POINT_EFFECT_CODE,
            requested_name="Missing Point",
            editor_context=run_context,
        )

    current = repository.get("workspace-1")
    assert current.status == "pending"
    assert current.code == ""
    assert current.editor_revision == 2


def test_generation_save_accepts_authorized_time_marker_bindings(tmp_path):
    repository = EffectRepository(tmp_path)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["markers"] = [
        {"id": "marker-1", "alias": "t1", "frame": 80},
        {"id": "marker-2", "alias": "t2", "frame": 140},
    ]
    editor_state["next_alias"]["marker"] = 3
    saved_controls = repository.replace_editor_state(
        "workspace-1",
        created.editor_revision,
        editor_state,
    )
    run_context = repository.get_editor_context_snapshot(
        "workspace-1",
        "video-1",
        saved_controls.editor_revision,
        {"current_frame": 100},
    )

    generated = repository.save_generated_effect(
        effect_id="workspace-1",
        code=TIME_EFFECT_CODE,
        requested_name="Timed Effect",
        editor_context=run_context,
    )

    assert generated.status == "active"
    assert generated.code == TIME_EFFECT_CODE


def test_generation_save_rejects_a_time_marker_deleted_after_run_start(tmp_path):
    repository = EffectRepository(tmp_path)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["markers"] = [
        {"id": "marker-1", "alias": "t1", "frame": 80},
        {"id": "marker-2", "alias": "t2", "frame": 140},
    ]
    editor_state["next_alias"]["marker"] = 3
    saved_controls = repository.replace_editor_state(
        "workspace-1",
        created.editor_revision,
        editor_state,
    )
    run_context = repository.get_editor_context_snapshot(
        "workspace-1",
        "video-1",
        saved_controls.editor_revision,
        {"current_frame": 100},
    )
    deleted_state = saved_controls.editor_state.model_dump(mode="json")
    deleted_state["markers"] = [deleted_state["markers"][0]]
    repository.replace_editor_state(
        "workspace-1",
        saved_controls.editor_revision,
        deleted_state,
    )

    with pytest.raises(
        EffectEditorStateError,
        match="Generated Effect references a Time Marker that no longer exists: marker-2",
    ):
        repository.save_generated_effect(
            effect_id="workspace-1",
            code=TIME_EFFECT_CODE,
            requested_name="Missing Marker",
            editor_context=run_context,
        )


def test_generation_rejects_explicit_update_missing_from_new_config(tmp_path):
    repository = EffectRepository(tmp_path)
    repository.save_effect("effect-1", EFFECT_CODE, {"size": 20}, "Original")

    with pytest.raises(EffectParameterError):
        repository.save_generated_effect(
            effect_id="effect-1",
            code=UPDATED_EFFECT_CODE,
            requested_name="Original",
            base_name="Original",
            explicit_parameter_updates={"missing": 1},
        )

    current = repository.get("effect-1")
    assert current.code == EFFECT_CODE
    assert current.params == {"size": 20}


def test_draft_save_preserves_compatible_edits_made_during_generation(tmp_path):
    repository = EffectRepository(tmp_path)
    repository.save_effect("effect-1", EFFECT_CODE, {"size": 20}, "Original")
    repository.patch_effect(
        "effect-1",
        requested_name="Live Rename",
        parameter_updates={"size": 40},
    )

    draft = repository.save_draft_effect(
        effect_id="effect-1",
        code=EFFECT_CODE,
        requested_name="Original",
        base_name="Original",
        generation_metadata={"failure": "runtime"},
    )

    assert draft.status == "draft"
    assert draft.name == "Live Rename"
    assert draft.params["size"] == 40


def test_pending_workspace_persists_a_fixed_point_without_effect_code(tmp_path):
    repository = EffectRepository(tmp_path)
    created = repository.create_workspace(
        effect_id="workspace-1",
        video_id="video-1",
        total_frames=230,
    )

    assert created.status == "pending"
    assert created.code == ""
    assert created.params == {}
    assert created.editor_revision == 0

    updated = repository.replace_editor_state(
        effect_id="workspace-1",
        expected_revision=0,
        editor_state={
            "schema_version": 2,
            "video_id": "video-1",
            "active_interval": {"start_frame": 0, "end_frame": 229},
            "points": [
                {
                    "id": "point-1",
                    "alias": "p1",
                    "source": {"type": "fixed", "x": 0.75, "y": 0.25},
                }
            ],
            "markers": [],
            "next_alias": {"point": 2, "marker": 1},
        },
    )

    assert updated.editor_revision == 1
    assert updated.editor_state.points[0].alias == "p1"
    assert updated.editor_state.points[0].source.x == 0.75

    reloaded = EffectRepository(tmp_path).get("workspace-1")
    assert reloaded is not None
    assert reloaded.status == "pending"
    assert reloaded.code == ""
    assert reloaded.params == {}
    assert reloaded.editor_revision == 1
    assert reloaded.editor_state == updated.editor_state


def test_generated_effect_promotes_pending_workspace_without_losing_editor_state(tmp_path):
    repository = EffectRepository(tmp_path)
    repository.create_workspace("workspace-1", "video-1", total_frames=230)
    edited = repository.replace_editor_state(
        "workspace-1",
        expected_revision=0,
        editor_state={
            "schema_version": 2,
            "video_id": "video-1",
            "active_interval": {"start_frame": 0, "end_frame": 229},
            "points": [
                {
                    "id": "point-1",
                    "alias": "p1",
                    "source": {"type": "fixed", "x": 0.2, "y": 0.8},
                }
            ],
            "markers": [],
            "next_alias": {"point": 2, "marker": 1},
        },
    )

    promoted = repository.save_generated_effect(
        effect_id="workspace-1",
        code=EFFECT_CODE,
        requested_name="Orbit Point",
    )

    assert promoted.status == "active"
    assert promoted.name == "Orbit Point"
    assert promoted.editor_revision == edited.editor_revision
    assert promoted.editor_state == edited.editor_state

    reloaded = EffectRepository(tmp_path).get("workspace-1")
    assert reloaded is not None
    assert reloaded.name == "Orbit Point"
    assert reloaded.editor_state == edited.editor_state


def test_stale_editor_revision_cannot_overwrite_a_newer_fixed_point(tmp_path):
    repository = EffectRepository(tmp_path)
    initial = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    first_client_state = initial.editor_state.model_dump(mode="json")
    first_client_state["points"].append(
        {
            "id": "point-1",
            "alias": "p1",
            "source": {"type": "fixed", "x": 0.2, "y": 0.8},
        }
    )
    second_client_state = initial.editor_state.model_dump(mode="json")
    second_client_state["points"].append(
        {
            "id": "point-1",
            "alias": "p1",
            "source": {"type": "fixed", "x": 0.9, "y": 0.1},
        }
    )

    saved = repository.replace_editor_state(
        "workspace-1",
        expected_revision=0,
        editor_state=first_client_state,
    )

    with pytest.raises(EffectEditorRevisionError):
        repository.replace_editor_state(
            "workspace-1",
            expected_revision=0,
            editor_state=second_client_state,
        )

    reloaded = EffectRepository(tmp_path).get("workspace-1")
    assert reloaded.editor_revision == 1
    assert reloaded.editor_state == saved.editor_state
    assert reloaded.editor_state.points[0].source.x == 0.2


def test_existing_workspace_rejects_a_different_video_shape(tmp_path):
    repository = EffectRepository(tmp_path)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)

    with pytest.raises(EffectEditorStateError):
        repository.create_workspace("workspace-1", "video-1", total_frames=300)

    reloaded = repository.get("workspace-1")
    assert reloaded.total_frames == 230
    assert reloaded.editor_state == created.editor_state


def test_renaming_a_pending_workspace_returns_its_current_editor_state(tmp_path):
    repository = EffectRepository(tmp_path)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)

    renamed = repository.patch_effect("workspace-1", requested_name="Orbit Point")

    assert renamed.name == "Orbit Point"
    assert renamed.status == "pending"
    assert renamed.editor_revision == 0
    assert renamed.editor_state == created.editor_state


def test_invalid_generated_draft_preserves_the_workspace_editor_state(tmp_path):
    repository = EffectRepository(tmp_path)
    repository.create_workspace("workspace-1", "video-1", total_frames=230)
    edited = repository.replace_editor_state(
        "workspace-1",
        expected_revision=0,
        editor_state={
            "schema_version": 2,
            "video_id": "video-1",
            "active_interval": {"start_frame": 0, "end_frame": 229},
            "points": [
                {
                    "id": "point-1",
                    "alias": "p1",
                    "source": {"type": "fixed", "x": 0.4, "y": 0.6},
                }
            ],
            "markers": [],
            "next_alias": {"point": 2, "marker": 1},
        },
    )

    draft = repository.save_draft_effect(
        effect_id="workspace-1",
        code="class Effect {}",
        requested_name="Broken Orbit",
        generation_metadata={"failure": "hard_validation"},
    )

    assert draft.status == "draft"
    assert draft.video_id == "video-1"
    assert draft.total_frames == 230
    assert draft.editor_revision == edited.editor_revision
    assert draft.editor_state == edited.editor_state

    reloaded = EffectRepository(tmp_path).get("workspace-1")
    assert reloaded.editor_state == edited.editor_state


def test_saving_an_effect_returns_the_existing_workspace_editor_state(tmp_path):
    repository = EffectRepository(tmp_path)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)

    saved = repository.save_effect(
        effect_id="workspace-1",
        code=EFFECT_CODE,
        params={"size": 20},
        requested_name="Orbit Point",
    )

    assert saved.status == "active"
    assert saved.video_id == "video-1"
    assert saved.editor_state == created.editor_state


def test_enabling_controls_on_a_legacy_effect_preserves_the_saved_effect(tmp_path):
    repository = EffectRepository(tmp_path)
    legacy = repository.save_effect(
        effect_id="effect-1",
        code=EFFECT_CODE,
        params={"size": 20},
        requested_name="Legacy Orbit",
    )

    enabled = repository.create_workspace("effect-1", "video-1", total_frames=230)

    assert enabled.name == legacy.name
    assert enabled.status == "active"
    assert enabled.code == EFFECT_CODE
    assert enabled.params == {"size": 20}
    assert enabled.video_id == "video-1"
    assert enabled.total_frames == 230
    assert enabled.editor_revision == 0
    assert enabled.editor_state == empty_editor_state("video-1", 230)


def test_workspace_persists_a_joint_point_with_normalized_offset(tmp_path):
    repository = EffectRepository(tmp_path)
    repository.create_workspace("workspace-1", "video-1", total_frames=230)

    saved = repository.replace_editor_state(
        "workspace-1",
        expected_revision=0,
        editor_state={
            "schema_version": 2,
            "video_id": "video-1",
            "active_interval": {"start_frame": 0, "end_frame": 229},
            "points": [
                {
                    "id": "point-1",
                    "alias": "p1",
                    "source": {
                        "type": "joint",
                        "joint": "left_wrist",
                        "offset_x": 0.1,
                        "offset_y": -0.2,
                    },
                }
            ],
            "markers": [],
            "next_alias": {"point": 2, "marker": 1},
        },
    )

    source = saved.editor_state.points[0].source
    assert source.type == "joint"
    assert source.joint == "left_wrist"
    assert source.offset_x == 0.1
    assert source.offset_y == -0.2
    assert EffectRepository(tmp_path).get("workspace-1").editor_state == saved.editor_state


@pytest.mark.parametrize(
    "source",
    [
        {
            "type": "joint",
            "joint": "unknown_joint",
            "offset_x": 0,
            "offset_y": 0,
        },
        {
            "type": "joint",
            "joint": "left_wrist",
            "offset_x": 1.01,
            "offset_y": 0,
        },
    ],
)
def test_workspace_rejects_invalid_joint_point_sources_without_saving(
    tmp_path,
    source,
):
    repository = EffectRepository(tmp_path)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["points"] = [{"id": "point-1", "alias": "p1", "source": source}]
    editor_state["next_alias"]["point"] = 2

    with pytest.raises(ValueError):
        repository.replace_editor_state("workspace-1", 0, editor_state)

    reloaded = repository.get("workspace-1")
    assert reloaded.editor_revision == 0
    assert reloaded.editor_state.points == []
