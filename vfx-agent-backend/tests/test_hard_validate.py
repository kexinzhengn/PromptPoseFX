"""Executable hard-validation contract for generated Effects."""

import json
from pathlib import Path

import pytest

from agent.hard_validate import hard_validate_effect


def _write_pose(path: Path, frame_count: int = 3) -> None:
    """Write a minimal valid Pose timeline for runtime validation."""
    frames = {
        str(frame): [[100 + frame + joint, 200 + joint] for joint in range(33)]
        for frame in range(frame_count)
    }
    path.write_text(json.dumps(frames), encoding="utf-8")


def test_hard_validate_rejects_runtime_error(tmp_path: Path) -> None:
    """Static-valid code must fail when its display method crashes."""
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  display(sketch, frameData, params) {
    sketch.nonexistentMethod();
  }
}"""

    result = hard_validate_effect(code, pose_path, frames=3)

    assert result.passed is False
    assert any("nonexistentMethod is not a function" in error for error in result.errors)


def test_hard_validate_returns_params_and_render_summary(tmp_path: Path) -> None:
    """A valid Effect returns defaults and an observable render summary."""
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {
    size: {
      default: 12,
      type: 'range',
      min: 1,
      max: 30,
      step: 1,
      label: 'Size',
      description: 'Higher values create a larger marker'
    }
  };
  display(sketch, frameData, params) {
    sketch.ellipse(10, 10, params.size, params.size);
  }
}"""

    result = hard_validate_effect(code, pose_path, frames=3)

    assert result.passed is True
    assert result.errors == []
    assert result.params == {"size": 12}
    assert result.render_summary is not None
    assert result.render_summary.frames == 3
    assert result.render_summary.total_draw_calls == 3


def test_hard_validate_exposes_a_fixed_point_at_real_video_dimensions(
    tmp_path: Path,
) -> None:
    """Node validation and browser preview must use the shared control resolver."""
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  static CONTROL_BINDINGS = {
    anchor: { type: 'point', id: 'point-1' }
  };
  display(sketch, frameData, params) {
    const anchor = frameData.controls.getPoint('anchor');
    if (anchor.x !== 600 || anchor.y !== 150) {
      throw new Error(`Unexpected Fixed Point: ${anchor.x},${anchor.y}`);
    }
    sketch.ellipse(anchor.x, anchor.y, 10, 10);
  }
}"""
    editor_state = {
        "schema_version": 2,
        "video_id": "video-1",
        "active_interval": {"start_frame": 0, "end_frame": 2},
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

    result = hard_validate_effect(
        code,
        pose_path,
        frames=3,
        editor_state=editor_state,
        video_width=800,
        video_height=600,
    )

    assert result.passed is True, result.errors


def test_hard_validate_exposes_path_sampling_at_real_video_dimensions(
    tmp_path: Path,
) -> None:
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  static CONTROL_BINDINGS = {
    guide: { type: 'path', id: 'path-1' }
  };
  display(sketch, frameData, params) {
    const guide = frameData.controls.getPath('guide');
    const midpoint = guide.sample(0.5);
    if (guide.length !== 200 || midpoint.x !== 100 || midpoint.y !== 0) {
      throw new Error('Unexpected Path sample');
    }
    sketch.line(guide.points[0].x, guide.points[0].y, midpoint.x, midpoint.y);
  }
}"""
    editor_state = {
        "schema_version": 2,
        "video_id": "video-1",
        "active_interval": {"start_frame": 0, "end_frame": 2},
        "points": [],
        "paths": [{
            "id": "path-1",
            "alias": "path1",
            "points": [
                {"x": 0, "y": 0},
                {"x": 0.5, "y": 0},
                {"x": 0.5, "y": 1},
            ],
        }],
        "markers": [],
        "next_alias": {"point": 1, "marker": 1, "path": 2},
    }

    result = hard_validate_effect(
        code,
        pose_path,
        frames=3,
        editor_state=editor_state,
        video_width=200,
        video_height=100,
    )

    assert result.passed is True, result.errors


def test_hard_validate_rejects_a_binding_to_a_missing_point(tmp_path: Path) -> None:
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  static CONTROL_BINDINGS = {
    anchor: { type: 'point', id: 'missing-point' }
  };
  display(sketch, frameData, params) {
    sketch.ellipse(10, 10, 10, 10);
  }
}"""

    result = hard_validate_effect(
        code,
        pose_path,
        frames=3,
        editor_state={"points": []},
    )

    assert result.passed is False
    assert any("missing control" in error for error in result.errors)


def test_hard_validate_resolves_a_joint_point_from_pose_history(tmp_path: Path) -> None:
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  static CONTROL_BINDINGS = {
    anchor: { type: 'point', id: 'point-1' }
  };
  display(sketch, frameData, params) {
    const anchor = frameData.controls.getPoint('anchor');
    const expectedX = 195 + frameData.currentFrame;
    if (!anchor.valid || anchor.x !== expectedX || anchor.y !== 95) {
      throw new Error(`Unexpected Joint Point: ${anchor.x},${anchor.y}`);
    }
    sketch.ellipse(anchor.x, anchor.y, 10, 10);
  }
}"""
    editor_state = {
        "schema_version": 2,
        "video_id": "video-1",
        "active_interval": {"start_frame": 0, "end_frame": 2},
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
    }

    result = hard_validate_effect(
        code,
        pose_path,
        frames=3,
        editor_state=editor_state,
        video_width=800,
        video_height=600,
    )

    assert result.passed is True, result.errors


def test_hard_validate_resolves_two_time_markers_as_a_live_interval(tmp_path: Path) -> None:
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  static CONTROL_BINDINGS = {
    start: { type: 'time_marker', id: 'marker-1' },
    end: { type: 'time_marker', id: 'marker-2' }
  };
  display(sketch, frameData, params) {
    const start = frameData.controls.getTimeMarker('start');
    const end = frameData.controls.getTimeMarker('end');
    if (frameData.currentFrame < start.frame || frameData.currentFrame > end.frame) return;
    sketch.ellipse(100, 100, 10, 10);
  }
}"""
    editor_state = {
        "schema_version": 2,
        "video_id": "video-1",
        "active_interval": {"start_frame": 0, "end_frame": 2},
        "points": [],
        "markers": [
            {"id": "marker-1", "alias": "t1", "frame": 0},
            {"id": "marker-2", "alias": "t2", "frame": 2},
        ],
        "next_alias": {"point": 1, "marker": 3},
    }

    result = hard_validate_effect(
        code,
        pose_path,
        frames=3,
        editor_state=editor_state,
        required_control_ids={"marker-1", "marker-2"},
    )

    assert result.passed is True, result.errors


def test_hard_validate_rejects_baking_required_markers_into_frame_literals(
    tmp_path: Path,
) -> None:
    """A user-referenced Marker must remain bound after its frame is moved."""
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path, frame_count=130)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  static CONTROL_BINDINGS = {
    startPoint: { type: 'point', id: 'point-1' },
    endPoint: { type: 'point', id: 'point-2' },
    startTime: { type: 'time_marker', id: 'marker-1' },
    endTime: { type: 'time_marker', id: 'marker-2' }
  };
  display(sketch, frameData, params) {
    const startFrame = 34;
    const endFrame = 121;
    if (frameData.currentFrame < startFrame || frameData.currentFrame > endFrame) return;
    sketch.ellipse(100, 100, 10, 10);
  }
}"""
    editor_state = {
        "points": [
            {
                "id": "point-1",
                "alias": "p1",
                "source": {"type": "fixed", "x": 0.2, "y": 0.5},
            },
            {
                "id": "point-2",
                "alias": "p2",
                "source": {"type": "fixed", "x": 0.8, "y": 0.5},
            },
        ],
        "markers": [
            {"id": "marker-1", "alias": "t1", "frame": 34},
            {"id": "marker-2", "alias": "t2", "frame": 121},
        ],
    }

    result = hard_validate_effect(
        code,
        pose_path,
        frames=3,
        editor_state=editor_state,
        required_control_ids={"marker-1", "marker-2"},
    )

    assert result.passed is False
    assert any("not read during rendering" in error for error in result.errors)


def test_hard_validate_rejects_time_controls_read_only_on_new_frames(
    tmp_path: Path,
) -> None:
    """Passive redraw must resolve current Marker values without advancing state."""
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path, frame_count=5)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  static CONTROL_BINDINGS = {
    event: { type: 'time_marker', id: 'marker-1' }
  };
  display(sketch, frameData, params) {
    if (frameData.isNewFrame) {
      this.eventFrame = frameData.controls.getTimeMarker('event').frame;
    }
    sketch.ellipse(100, 100, 10, 10);
  }
}"""
    editor_state = {
        "active_interval": {"start_frame": 0, "end_frame": 4},
        "points": [],
        "markers": [{"id": "marker-1", "alias": "t1", "frame": 2}],
    }

    result = hard_validate_effect(
        code,
        pose_path,
        frames=5,
        editor_state=editor_state,
        required_control_ids={"marker-1"},
    )

    assert result.passed is False
    assert any("passive redraw" in error for error in result.errors)


def test_hard_validate_accepts_marker_access_on_new_and_passive_draws(
    tmp_path: Path,
) -> None:
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path, frame_count=5)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  static CONTROL_BINDINGS = {
    event: { type: 'time_marker', id: 'marker-1' }
  };
  display(sketch, frameData, params) {
    const event = frameData.controls.getTimeMarker('event');
    if (frameData.currentFrame >= event.frame) {
      sketch.ellipse(100, 100, 10, 10);
    }
  }
}"""
    editor_state = {
        "active_interval": {"start_frame": 0, "end_frame": 4},
        "points": [],
        "markers": [{"id": "marker-1", "alias": "t1", "frame": 2}],
    }

    result = hard_validate_effect(
        code,
        pose_path,
        frames=5,
        editor_state=editor_state,
        required_control_ids={"marker-1"},
    )

    assert result.passed is True, result.errors


def test_hard_validate_rejects_time_values_that_never_affect_drawing(
    tmp_path: Path,
) -> None:
    """Calling the control API is insufficient when its result is discarded."""
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path, frame_count=20)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  static CONTROL_BINDINGS = {
    event: { type: 'time_marker', id: 'marker-1' }
  };
  constructor() {
    this.offset = 0;
  }
  display(sketch, frameData, params) {
    const ignoredEvent = frameData.controls.getTimeMarker('event');
    if (frameData.isNewFrame) this.offset = sketch.random(-5, 5);
    sketch.ellipse(100 + this.offset, 100, 10, 10);
  }
}"""
    editor_state = {
        "active_interval": {"start_frame": 0, "end_frame": 19},
        "points": [],
        "markers": [{"id": "marker-1", "alias": "t1", "frame": 5}],
    }

    result = hard_validate_effect(
        code,
        pose_path,
        frames=20,
        editor_state=editor_state,
        required_control_ids={"marker-1"},
    )

    assert result.passed is False
    assert any("did not affect drawing" in error for error in result.errors)


@pytest.mark.parametrize(
    ("binding", "expected_error"),
    [
        (
            "event: { type: 'time_marker', id: 'missing-marker' }",
            "Time Marker binding references a missing control: event",
        ),
    ],
)
def test_hard_validate_rejects_missing_time_controls(
    tmp_path: Path,
    binding: str,
    expected_error: str,
) -> None:
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path)
    code = f"""class Effect {{
  static CONTRACT_VERSION = 2;
  static CONFIG = {{}};
  static CONTROL_BINDINGS = {{
    {binding}
  }};
  display(sketch, frameData, params) {{
    sketch.ellipse(100, 100, 10, 10);
  }}
}}"""

    result = hard_validate_effect(
        code,
        pose_path,
        frames=3,
        editor_state={"points": [], "markers": []},
    )

    assert result.passed is False
    assert any(expected_error in error for error in result.errors)


def test_hard_validate_rejects_removed_time_span_binding_type(tmp_path: Path) -> None:
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  static CONTROL_BINDINGS = {
    period: { type: 'time_span', id: 'old-interval' }
  };
  display(sketch, frameData, params) {
    sketch.ellipse(100, 100, 10, 10);
  }
}"""

    result = hard_validate_effect(code, pose_path)

    assert result.passed is False
    assert any(
        "CONTROL_BINDINGS.period.type must be one of: path, point, time_marker" in error
        for error in result.errors
    )


def test_hard_validate_calls_effect_only_inside_its_active_interval(
    tmp_path: Path,
) -> None:
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path, frame_count=6)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  display(sketch, frameData, params) {
    if (frameData.currentFrame < 2 || frameData.currentFrame > 3) {
      throw new Error('Effect rendered outside its Clip');
    }
    sketch.ellipse(100, 100, 10, 10);
  }
}"""
    editor_state = {
        "active_interval": {"start_frame": 2, "end_frame": 3},
        "points": [],
        "markers": [],
    }

    result = hard_validate_effect(
        code,
        pose_path,
        frames=6,
        editor_state=editor_state,
    )

    assert result.passed is True, result.errors
    assert result.render_summary is not None
    assert result.render_summary.frames == 2


def test_hard_validate_samples_a_used_marker_beyond_the_base_window(
    tmp_path: Path,
) -> None:
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path, frame_count=170)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  static CONTROL_BINDINGS = {
    event: { type: 'time_marker', id: 'marker-1' }
  };
  display(sketch, frameData, params) {
    const event = frameData.controls.getTimeMarker('event');
    if (frameData.currentFrame >= event.frame) {
      sketch.ellipse(100, 100, 10, 10);
    }
  }
}"""
    editor_state = {
        "active_interval": {"start_frame": 0, "end_frame": 169},
        "points": [],
        "markers": [{"id": "marker-1", "alias": "t1", "frame": 150}],
    }

    result = hard_validate_effect(
        code,
        pose_path,
        frames=60,
        editor_state=editor_state,
    )

    assert result.passed is True, result.errors
    assert result.render_summary is not None
    assert result.render_summary.total_draw_calls > 0


def test_hard_validate_samples_the_middle_between_two_used_markers(
    tmp_path: Path,
) -> None:
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path, frame_count=170)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  static CONTROL_BINDINGS = {
    start: { type: 'time_marker', id: 'marker-1' },
    end: { type: 'time_marker', id: 'marker-2' }
  };
  display(sketch, frameData, params) {
    const start = frameData.controls.getTimeMarker('start').frame;
    const end = frameData.controls.getTimeMarker('end').frame;
    const progress = (frameData.currentFrame - start) / (end - start);
    if (progress >= 0.45 && progress <= 0.55) {
      sketch.ellipse(100, 100, 10, 10);
    }
  }
}"""
    editor_state = {
        "active_interval": {"start_frame": 0, "end_frame": 169},
        "points": [],
        "markers": [
            {"id": "marker-1", "alias": "t1", "frame": 100},
            {"id": "marker-2", "alias": "t2", "frame": 140},
        ],
    }

    result = hard_validate_effect(
        code,
        pose_path,
        frames=60,
        editor_state=editor_state,
    )

    assert result.passed is True, result.errors
    assert result.render_summary is not None
    assert result.render_summary.total_draw_calls > 0


def test_hard_validate_executes_a_forward_skip_across_a_used_marker(
    tmp_path: Path,
) -> None:
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path, frame_count=100)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  static CONTROL_BINDINGS = {
    event: { type: 'time_marker', id: 'marker-1' }
  };
  display(sketch, frameData, params) {
    const event = frameData.controls.getTimeMarker('event');
    if (
      frameData.currentFrame > event.frame
      && frameData.deltaFrames > 1
      && frameData.discontinuity === 'none'
    ) {
      throw new Error('Observed forward skip across Time Marker');
    }
    sketch.ellipse(100, 100, 10, 10);
  }
}"""
    editor_state = {
        "active_interval": {"start_frame": 0, "end_frame": 99},
        "points": [],
        "markers": [{"id": "marker-1", "alias": "t1", "frame": 80}],
    }

    result = hard_validate_effect(
        code,
        pose_path,
        frames=60,
        editor_state=editor_state,
    )

    assert result.passed is False
    assert any(
        "Observed forward skip across Time Marker" in error
        for error in result.errors
    )


def test_hard_validate_rejects_effect_with_no_draw_calls(tmp_path: Path) -> None:
    """An Effect that renders nothing across all sampled frames is unusable."""
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  display(sketch, frameData, params) {
    sketch.push();
    sketch.pop();
  }
}"""

    result = hard_validate_effect(code, pose_path, frames=3)

    assert result.passed is False
    assert any("no draw calls" in error.lower() for error in result.errors)


def test_hard_validate_times_out_infinite_render_loop(tmp_path: Path) -> None:
    """Generated code cannot block validation indefinitely."""
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  display(sketch, frameData, params) {
    while (true) {}
  }
}"""

    result = hard_validate_effect(
        code,
        pose_path,
        frames=1,
        timeout_seconds=0.2,
    )

    assert result.passed is False
    assert any("exceeded 0.2 seconds" in error for error in result.errors)


def test_hard_validate_accepts_bounded_sequential_frame_state(tmp_path: Path) -> None:
    """State may depend on prior frames when repeated rendering stays passive."""
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path, frame_count=5)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  constructor() {
    this.phase = 0;
    this.particles = [];
  }
  display(sketch, frameData, params) {
    if (frameData.discontinuity !== 'none') {
      this.phase = 0;
      this.particles = [];
    }
    if (frameData.isNewFrame) {
      this.phase += frameData.deltaFrames || 1;
      this.particles.push({ x: sketch.random(0, 100), life: 3 });
      this.particles = this.particles.slice(-3);
    }
    for (const particle of this.particles) {
      sketch.ellipse(particle.x + this.phase, 10, 5, 5);
    }
  }
}"""

    result = hard_validate_effect(code, pose_path, frames=5)

    assert result.passed is True, result.errors


def test_hard_validate_rejects_same_frame_repeat_difference(tmp_path: Path) -> None:
    """Passive redraws of the current frame must emit identical commands."""
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path, frame_count=5)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  constructor() {
    this.seen = -1;
  }
  display(sketch, frameData, params) {
    const tint = this.seen === frameData.currentFrame ? 200 : 50;
    this.seen = frameData.currentFrame;
    sketch.fill(tint, 0, 0);
    sketch.ellipse(10, 10, 5, 5);
  }
}"""

    result = hard_validate_effect(code, pose_path, frames=5)

    assert result.passed is False
    assert any("isNewFrame was false" in error for error in result.errors)


def test_hard_validate_checks_passive_redraw_on_every_sampled_frame(tmp_path: Path) -> None:
    """A repeat bug on an early frame cannot hide behind a safe final frame."""
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path, frame_count=5)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  constructor() {
    this.count = 0;
  }
  display(sketch, frameData, params) {
    if (frameData.currentFrame === 0) this.count += 1;
    sketch.ellipse(this.count, 10, 5, 5);
  }
}"""

    result = hard_validate_effect(code, pose_path, frames=5)

    assert result.passed is False
    assert any(
        "frame 0" in error and "isNewFrame was false" in error
        for error in result.errors
    ), result.errors


def test_hard_validate_allows_forward_frame_delta_response(tmp_path: Path) -> None:
    """A normal forward skip may produce a different sequential state."""
    pose_path = tmp_path / "pose.json"
    _write_pose(pose_path, frame_count=5)
    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  constructor() {
    this.size = 5;
  }
  display(sketch, frameData, params) {
    if (frameData.discontinuity !== 'none') this.size = 5;
    if (frameData.isNewFrame) this.size = frameData.deltaFrames > 1 ? 20 : 5;
    sketch.ellipse(10, 10, this.size, this.size);
  }
}"""

    result = hard_validate_effect(code, pose_path, frames=5)

    assert result.passed is True, result.errors
