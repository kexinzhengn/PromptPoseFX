"""Effect PATCH API tests for deterministic metadata and parameter updates."""

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from effect_repository import EffectRepository
from tests.test_effect_repository import EFFECT_CODE, POINT_EFFECT_CODE, TIME_EFFECT_CODE


TIME_MARKER_EFFECT_CODE = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONTROL_BINDINGS = {
    event: { type: 'time_marker', id: 'marker-1' },
  };
  static CONFIG = {};
  display(sketch, frameData, params) {}
}"""

def test_create_pending_workspace_uses_trusted_video_metadata(
    isolated_chat_storage,
    tmp_path,
    monkeypatch,
):
    import app as app_module

    video_dir = tmp_path / "video-1"
    video_dir.mkdir()
    (video_dir / "metadata.json").write_text(
        json.dumps({"id": "video-1", "totalFrames": 230}),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))
    client = TestClient(app_module.app)

    response = client.post(
        "/api/effects",
        json={"effect_id": "workspace-1", "video_id": "video-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload.pop("created_at")
    assert payload.pop("updated_at")
    assert payload == {
        "effect_id": "workspace-1",
        "name": "Untitled Effect",
        "status": "pending",
        "code": "",
        "params": {},
        "parameter_ranges": {},
        "revision": 0,
        "generation_metadata": {},
        "video_id": "video-1",
        "total_frames": 230,
        "editor_revision": 0,
        "bound_control_ids": [],
        "editor_state": {
            "schema_version": 2,
            "video_id": "video-1",
            "active_interval": {"start_frame": 0, "end_frame": 229},
            "points": [],
            "paths": [],
            "markers": [],
            "next_alias": {"point": 1, "marker": 1, "path": 1},
        },
        "conversation": [],
    }

    detail = client.get("/api/effect/workspace-1")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload.pop("created_at")
    assert detail_payload.pop("updated_at")
    assert detail_payload == payload


def test_effect_detail_exposes_bound_point_ids_from_saved_code(
    isolated_chat_storage,
):
    import app as app_module

    EffectRepository(isolated_chat_storage).save_effect(
        "effect-1",
        POINT_EFFECT_CODE,
        {"size": 20},
        "Bound Point",
        status="active",
    )
    client = TestClient(app_module.app)

    response = client.get("/api/effect/effect-1")

    assert response.status_code == 200
    assert response.json()["bound_control_ids"] == ["point-1"]


def test_effect_detail_exposes_bound_time_marker_ids_from_saved_code(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    repository.save_effect(
        "marker-effect",
        TIME_MARKER_EFFECT_CODE,
        {},
        "Timed Event",
        status="active",
    )
    client = TestClient(app_module.app)

    marker_response = client.get("/api/effect/marker-effect")

    assert marker_response.status_code == 200
    assert marker_response.json()["bound_control_ids"] == ["marker-1"]


def test_put_editor_state_saves_a_fixed_point_and_returns_the_new_revision(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    repository.create_workspace("workspace-1", "video-1", total_frames=230)
    client = TestClient(app_module.app)
    editor_state = {
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
    }

    response = client.put(
        "/api/effect/workspace-1/editor-state",
        json={"expected_revision": 0, "editor_state": editor_state},
    )

    assert response.status_code == 200
    editor_state["paths"] = []
    editor_state["next_alias"]["path"] = 1
    assert response.json() == {
        "effect_id": "workspace-1",
        "editor_revision": 1,
        "editor_state": editor_state,
    }
    detail = client.get("/api/effect/workspace-1")
    assert detail.json()["editor_revision"] == 1
    assert detail.json()["editor_state"] == editor_state


def test_put_editor_state_saves_a_drawn_path_as_a_trusted_control(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["paths"] = [
        {
            "id": "path-1",
            "alias": "path1",
            "points": [
                {"x": 0.2, "y": 0.4},
                {"x": 0.5, "y": 0.2},
                {"x": 0.8, "y": 0.6},
            ],
        }
    ]
    editor_state["next_alias"]["path"] = 2
    client = TestClient(app_module.app)

    response = client.put(
        "/api/effect/workspace-1/editor-state",
        json={"expected_revision": 0, "editor_state": editor_state},
    )

    assert response.status_code == 200
    assert response.json()["editor_state"] == editor_state
    detail = client.get("/api/effect/workspace-1")
    assert detail.json()["editor_state"]["paths"] == editor_state["paths"]


def test_put_editor_state_rejects_an_invalid_drawn_path(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["paths"] = [
        {
            "id": "path-1",
            "alias": "path1",
            "points": [{"x": 1.2, "y": 0.4}],
        }
    ]
    editor_state["next_alias"]["path"] = 2
    client = TestClient(app_module.app)

    response = client.put(
        "/api/effect/workspace-1/editor-state",
        json={"expected_revision": 0, "editor_state": editor_state},
    )

    assert response.status_code == 422
    reloaded = repository.get("workspace-1")
    assert reloaded.editor_state.paths == []
    assert reloaded.editor_revision == 0


def test_put_editor_state_returns_conflict_without_overwriting_newer_data(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    first_state = created.editor_state.model_dump(mode="json")
    first_state["points"] = [
        {
            "id": "point-1",
            "alias": "p1",
            "source": {"type": "fixed", "x": 0.2, "y": 0.8},
        }
    ]
    first_state["next_alias"]["point"] = 2
    stale_state = {
        **first_state,
        "points": [
            {
                "id": "point-1",
                "alias": "p1",
                "source": {"type": "fixed", "x": 0.9, "y": 0.1},
            }
        ],
    }
    client = TestClient(app_module.app)

    first_response = client.put(
        "/api/effect/workspace-1/editor-state",
        json={"expected_revision": 0, "editor_state": first_state},
    )
    stale_response = client.put(
        "/api/effect/workspace-1/editor-state",
        json={"expected_revision": 0, "editor_state": stale_state},
    )

    assert first_response.status_code == 200
    assert stale_response.status_code == 409
    detail = client.get("/api/effect/workspace-1").json()
    assert detail["editor_revision"] == 1
    assert detail["editor_state"]["points"][0]["source"] == {
        "type": "fixed",
        "x": 0.2,
        "y": 0.8,
    }


def test_put_editor_state_rejects_out_of_bounds_points_without_partial_save(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    invalid_state = created.editor_state.model_dump(mode="json")
    invalid_state["points"] = [
        {
            "id": "point-1",
            "alias": "p1",
            "source": {"type": "fixed", "x": 1.25, "y": 0.5},
        }
    ]
    invalid_state["next_alias"]["point"] = 2
    client = TestClient(app_module.app)

    response = client.put(
        "/api/effect/workspace-1/editor-state",
        json={"expected_revision": 0, "editor_state": invalid_state},
    )

    assert response.status_code == 422
    reloaded = repository.get("workspace-1")
    assert reloaded.editor_revision == 0
    assert reloaded.editor_state.points == []


def test_put_editor_state_rejects_two_time_markers_on_the_same_frame(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["markers"] = [
        {"id": "marker-1", "alias": "t1", "frame": 90},
        {"id": "marker-2", "alias": "t2", "frame": 90},
    ]
    editor_state["next_alias"]["marker"] = 3
    client = TestClient(app_module.app)

    response = client.put(
        "/api/effect/workspace-1/editor-state",
        json={"expected_revision": 0, "editor_state": editor_state},
    )

    assert response.status_code == 422
    reloaded = repository.get("workspace-1")
    assert reloaded.editor_revision == 0
    assert reloaded.editor_state.markers == []


def test_put_editor_state_rejects_a_next_marker_alias_that_is_already_in_use(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["markers"] = [
        {"id": "marker-2", "alias": "t2", "frame": 120},
    ]
    editor_state["next_alias"]["marker"] = 2
    client = TestClient(app_module.app)

    response = client.put(
        "/api/effect/workspace-1/editor-state",
        json={"expected_revision": 0, "editor_state": editor_state},
    )

    assert response.status_code == 422
    assert repository.get("workspace-1").editor_revision == 0


def test_put_editor_state_does_not_reuse_a_deleted_time_marker_alias(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["markers"] = [
        {"id": "marker-1", "alias": "t1", "frame": 90},
    ]
    editor_state["next_alias"]["marker"] = 2
    saved = repository.replace_editor_state("workspace-1", 0, editor_state)
    deleted_state = saved.editor_state.model_dump(mode="json")
    deleted_state["markers"] = []
    deleted_state["next_alias"]["marker"] = 1
    client = TestClient(app_module.app)

    response = client.put(
        "/api/effect/workspace-1/editor-state",
        json={
            "expected_revision": saved.editor_revision,
            "editor_state": deleted_state,
        },
    )

    assert response.status_code == 422
    reloaded = repository.get("workspace-1")
    assert reloaded.editor_revision == saved.editor_revision
    assert reloaded.editor_state.markers[0].alias == "t1"


def test_put_editor_state_keeps_a_time_markers_alias_when_it_moves(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["markers"] = [
        {"id": "marker-1", "alias": "t1", "frame": 90},
    ]
    editor_state["next_alias"]["marker"] = 2
    saved = repository.replace_editor_state("workspace-1", 0, editor_state)
    changed_state = saved.editor_state.model_dump(mode="json")
    changed_state["markers"][0] = {
        "id": "marker-1",
        "alias": "t2",
        "frame": 120,
    }
    changed_state["next_alias"]["marker"] = 3
    client = TestClient(app_module.app)

    response = client.put(
        "/api/effect/workspace-1/editor-state",
        json={
            "expected_revision": saved.editor_revision,
            "editor_state": changed_state,
        },
    )

    assert response.status_code == 422
    reloaded = repository.get("workspace-1")
    assert reloaded.editor_revision == saved.editor_revision
    assert reloaded.editor_state.markers[0].alias == "t1"
    assert reloaded.editor_state.markers[0].frame == 90


def test_put_editor_state_rejects_deleting_a_bound_time_marker(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["markers"] = [
        {"id": "marker-1", "alias": "t1", "frame": 90},
    ]
    editor_state["next_alias"]["marker"] = 2
    saved = repository.replace_editor_state("workspace-1", 0, editor_state)
    repository.save_effect(
        "workspace-1",
        TIME_MARKER_EFFECT_CODE,
        {},
        "Timed Event",
        status="active",
    )
    deleted_state = saved.editor_state.model_dump(mode="json")
    deleted_state["markers"] = []
    client = TestClient(app_module.app)

    response = client.put(
        "/api/effect/workspace-1/editor-state",
        json={
            "expected_revision": saved.editor_revision,
            "editor_state": deleted_state,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Time Marker marker-1 cannot be deleted because the current Effect uses it"
    )
    reloaded = repository.get("workspace-1")
    assert reloaded.editor_revision == saved.editor_revision
    assert reloaded.editor_state.markers[0].id == "marker-1"


def test_put_editor_state_allows_moving_bound_interval_markers_and_trimming_the_clip(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["markers"] = [
        {"id": "marker-1", "alias": "t1", "frame": 60},
        {"id": "marker-2", "alias": "t2", "frame": 120},
    ]
    editor_state["next_alias"]["marker"] = 3
    saved = repository.replace_editor_state("workspace-1", 0, editor_state)
    repository.save_effect(
        "workspace-1",
        TIME_EFFECT_CODE,
        {},
        "Timed Period",
        status="active",
    )
    changed_state = saved.editor_state.model_dump(mode="json")
    changed_state["markers"][0]["frame"] = 75
    changed_state["active_interval"] = {"start_frame": 20, "end_frame": 200}
    client = TestClient(app_module.app)

    response = client.put(
        "/api/effect/workspace-1/editor-state",
        json={
            "expected_revision": saved.editor_revision,
            "editor_state": changed_state,
        },
    )

    assert response.status_code == 200
    assert response.json()["editor_revision"] == saved.editor_revision + 1
    detail = client.get("/api/effect/workspace-1").json()
    assert detail["editor_state"]["markers"][0]["frame"] == 75
    assert detail["editor_state"]["active_interval"] == {
        "start_frame": 20,
        "end_frame": 200,
    }


def test_put_editor_state_allows_deleting_an_unbound_marker(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["markers"] = [
        {"id": "marker-1", "alias": "t1", "frame": 60},
        {"id": "marker-2", "alias": "t2", "frame": 120},
    ]
    editor_state["next_alias"]["marker"] = 3
    saved = repository.replace_editor_state("workspace-1", 0, editor_state)
    deleted_state = saved.editor_state.model_dump(mode="json")
    deleted_state["markers"] = [deleted_state["markers"][1]]
    client = TestClient(app_module.app)

    response = client.put(
        "/api/effect/workspace-1/editor-state",
        json={
            "expected_revision": saved.editor_revision,
            "editor_state": deleted_state,
        },
    )

    assert response.status_code == 200
    assert response.json()["editor_state"]["markers"] == [
        {"id": "marker-2", "alias": "t2", "frame": 120}
    ]


def test_put_editor_state_rejects_deleting_a_point_used_by_the_active_effect(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["points"] = [
        {
            "id": "point-1",
            "alias": "p1",
            "source": {"type": "fixed", "x": 0.25, "y": 0.75},
        }
    ]
    editor_state["next_alias"]["point"] = 2
    saved = repository.replace_editor_state("workspace-1", 0, editor_state)
    repository.save_effect(
        "workspace-1",
        POINT_EFFECT_CODE,
        {"size": 20},
        "Bound Point",
        status="active",
    )
    deleted_state = saved.editor_state.model_dump(mode="json")
    deleted_state["points"] = []
    client = TestClient(app_module.app)

    response = client.put(
        "/api/effect/workspace-1/editor-state",
        json={
            "expected_revision": saved.editor_revision,
            "editor_state": deleted_state,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Point point-1 cannot be deleted because the current Effect uses it"
    )
    reloaded = repository.get("workspace-1")
    assert reloaded.editor_revision == saved.editor_revision
    assert [point.id for point in reloaded.editor_state.points] == ["point-1"]


def test_put_editor_state_rejects_changing_the_type_of_a_bound_point(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["points"] = [
        {
            "id": "point-1",
            "alias": "p1",
            "source": {"type": "fixed", "x": 0.25, "y": 0.75},
        }
    ]
    editor_state["next_alias"]["point"] = 2
    saved = repository.replace_editor_state("workspace-1", 0, editor_state)
    repository.save_effect(
        "workspace-1",
        POINT_EFFECT_CODE,
        {"size": 20},
        "Bound Point",
        status="draft",
    )
    changed_state = saved.editor_state.model_dump(mode="json")
    changed_state["points"][0]["source"] = {
        "type": "joint",
        "joint": "left_wrist",
        "offset_x": 0,
        "offset_y": 0,
    }
    client = TestClient(app_module.app)

    response = client.put(
        "/api/effect/workspace-1/editor-state",
        json={
            "expected_revision": saved.editor_revision,
            "editor_state": changed_state,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Point point-1 cannot change type because the current Effect uses it"
    )
    reloaded = repository.get("workspace-1")
    assert reloaded.editor_revision == saved.editor_revision
    assert reloaded.editor_state.points[0].source.type == "fixed"


def test_patch_effect_updates_name_and_params_without_agent_call(isolated_chat_storage):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    repository.save_effect(
        "effect-1",
        EFFECT_CODE,
        {"size": 20, "color": "#FF00AA", "enabled": True, "mode": 2},
        "Original",
    )
    client = TestClient(app_module.app)

    with patch.object(app_module, "process_user_message") as process_user_message:
        response = client.patch(
            "/api/effect/effect-1",
            json={"name": "  Renamed  ", "parameter_updates": {"size": 40}},
        )

    assert response.status_code == 200
    assert response.json()["effect_update"] == {
        "effect_id": "effect-1",
        "name": "Renamed",
        "params": {"size": 40, "color": "#FF00AA", "enabled": True, "mode": 2},
        "parameter_ranges": {},
        "status": "active",
    }
    process_user_message.assert_not_called()
    stored = repository.get("effect-1")
    assert stored.code == EFFECT_CODE
    assert stored.params["size"] == 40


def test_patch_effect_rejects_invalid_params_without_partial_rename(isolated_chat_storage):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    repository.save_effect("effect-1", EFFECT_CODE, {"size": 20}, "Original")
    client = TestClient(app_module.app)

    response = client.patch(
        "/api/effect/effect-1",
        json={"name": "Should Not Save", "parameter_updates": {"size": 100}},
    )

    assert response.status_code == 422
    stored = repository.get("effect-1")
    assert stored.name == "Original"
    assert stored.params == {"size": 20}


def test_patch_effect_saves_parameter_range_and_returns_it_in_detail(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    repository.save_effect("effect-1", EFFECT_CODE, {"size": 20}, "Original")
    client = TestClient(app_module.app)

    response = client.patch(
        "/api/effect/effect-1",
        json={"parameter_range_updates": {"size": {"min": 30, "max": 45}}},
    )

    assert response.status_code == 200
    assert response.json()["effect_update"]["params"]["size"] == 30
    assert response.json()["effect_update"]["parameter_ranges"] == {
        "size": {"min": 30.0, "max": 45.0}
    }
    detail = client.get("/api/effect/effect-1")
    assert detail.status_code == 200
    assert detail.json()["parameter_ranges"] == {
        "size": {"min": 30.0, "max": 45.0}
    }


def test_patch_effect_accepts_and_restores_range_outside_config_bounds(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    repository.save_effect("effect-1", EFFECT_CODE, {"size": 20}, "Original")
    client = TestClient(app_module.app)

    response = client.patch(
        "/api/effect/effect-1",
        json={"parameter_range_updates": {"size": {"min": 60, "max": 100}}},
    )

    assert response.status_code == 200
    assert response.json()["effect_update"]["params"]["size"] == 60
    assert response.json()["effect_update"]["parameter_ranges"] == {
        "size": {"min": 60.0, "max": 100.0}
    }
    detail = client.get("/api/effect/effect-1")
    assert detail.json()["parameter_ranges"] == {
        "size": {"min": 60.0, "max": 100.0}
    }


def test_chat_run_forwards_selected_option_id():
    import app as app_module

    client = TestClient(app_module.app)
    with patch.object(app_module._run_manager, "start", return_value="run-1") as start:
        response = client.post(
            "/api/chat/run",
            json={
                "video_id": "video-1",
                "user_input": "Orbiting rings",
                "thread_id": "workspace-1",
                "selected_option_id": "option-123",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"run_id": "run-1", "thread_id": "workspace-1"}
    assert start.call_args.kwargs["selected_option_id"] == "option-123"


def test_chat_run_passes_a_saved_editor_context_snapshot(isolated_chat_storage):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    editor_state = created.editor_state.model_dump(mode="json")
    editor_state["points"] = [
        {
            "id": "point-1",
            "alias": "p1",
            "source": {"type": "fixed", "x": 0.25, "y": 0.75},
        }
    ]
    editor_state["next_alias"]["point"] = 2
    repository.replace_editor_state("workspace-1", 0, editor_state)
    client = TestClient(app_module.app)

    with patch.object(app_module._run_manager, "start", return_value="run-1") as start:
        response = client.post(
            "/api/chat/run",
            json={
                "video_id": "video-1",
                "user_input": "Draw a circle at p1.",
                "thread_id": "workspace-1",
                "editor_revision": 1,
                "editor_selection": {
                    "current_frame": 42,
                    "selected_point_id": "point-1",
                },
            },
        )

    assert response.status_code == 200
    context = start.call_args.kwargs["editor_context"]
    assert context.model_dump(mode="json") == {
        "effect_id": "workspace-1",
        "video_id": "video-1",
        "editor_revision": 1,
        "editor_state": editor_state,
            "selection": {
                "current_frame": 42,
                "selected_point_id": "point-1",
                "selected_path_id": None,
            },
    }


def test_chat_run_rejects_a_stale_editor_revision_before_starting(
    isolated_chat_storage,
):
    import app as app_module

    repository = EffectRepository(isolated_chat_storage)
    created = repository.create_workspace("workspace-1", "video-1", total_frames=230)
    repository.replace_editor_state(
        "workspace-1",
        0,
        created.editor_state.model_dump(mode="json"),
    )
    client = TestClient(app_module.app)

    with patch.object(app_module._run_manager, "start", return_value="run-1") as start:
        response = client.post(
            "/api/chat/run",
            json={
                "video_id": "video-1",
                "user_input": "Draw at the selected Point.",
                "thread_id": "workspace-1",
                "editor_revision": 0,
                "editor_selection": {
                    "current_frame": 42,
                    "selected_point_id": None,
                },
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Expected editor revision 0, current revision is 1"
    start.assert_not_called()


def test_chat_run_rejects_editor_context_for_another_video(isolated_chat_storage):
    import app as app_module

    EffectRepository(isolated_chat_storage).create_workspace(
        "workspace-1",
        "video-1",
        total_frames=230,
    )
    client = TestClient(app_module.app)

    with patch.object(app_module._run_manager, "start", return_value="run-1") as start:
        response = client.post(
            "/api/chat/run",
            json={
                "video_id": "video-2",
                "user_input": "Draw at p1.",
                "thread_id": "workspace-1",
                "editor_revision": 0,
                "editor_selection": {"current_frame": 42},
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Effect Workspace belongs to another video"
    start.assert_not_called()


def test_chat_run_rejects_a_point_outside_the_workspace(isolated_chat_storage):
    import app as app_module

    EffectRepository(isolated_chat_storage).create_workspace(
        "workspace-1",
        "video-1",
        total_frames=230,
    )
    client = TestClient(app_module.app)

    with patch.object(app_module._run_manager, "start", return_value="run-1") as start:
        response = client.post(
            "/api/chat/run",
            json={
                "video_id": "video-1",
                "user_input": "Draw at the selected Point.",
                "thread_id": "workspace-1",
                "editor_revision": 0,
                "editor_selection": {
                    "current_frame": 42,
                    "selected_point_id": "point-missing",
                },
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Selected Point does not belong to the Effect Workspace"
    )
    start.assert_not_called()


def test_chat_run_does_not_accept_client_supplied_point_coordinates(
    isolated_chat_storage,
):
    import app as app_module

    EffectRepository(isolated_chat_storage).create_workspace(
        "workspace-1",
        "video-1",
        total_frames=230,
    )
    client = TestClient(app_module.app)

    with patch.object(app_module._run_manager, "start", return_value="run-1") as start:
        response = client.post(
            "/api/chat/run",
            json={
                "video_id": "video-1",
                "user_input": "Draw at p1.",
                "thread_id": "workspace-1",
                "editor_revision": 0,
                "editor_selection": {
                    "current_frame": 42,
                    "selected_point_id": None,
                    "alias": "p99",
                    "x": 0.9,
                    "y": 0.1,
                },
            },
        )

    assert response.status_code == 422
    start.assert_not_called()
