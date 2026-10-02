import os
import json
from pathlib import Path

import pytest

from agent.code_tools import update_todo, submit_code


# ============ update_todo 测试 ============

def test_update_todo_empty():
    result = update_todo.invoke({"items": []})
    assert result == "(empty list)"


def test_update_todo_normal():
    items = [
        {"content": "Analyze", "status": "completed"},
        {"content": "Implement", "status": "in_progress"},
        {"content": "Validate"},
    ]
    result = update_todo.invoke({"items": items})
    assert "[x] Analyze" in result
    assert "[~] Implement" in result
    assert "[ ] Validate" in result


def test_update_todo_exposes_a_structured_item_schema_to_the_model():
    schema = update_todo.args_schema.model_json_schema()
    item_schema = schema["$defs"]["TodoItem"]

    assert schema["properties"]["items"]["items"] == {"$ref": "#/$defs/TodoItem"}
    assert item_schema["required"] == ["content"]
    assert item_schema["properties"]["status"]["enum"] == [
        "pending",
        "in_progress",
        "completed",
    ]


def test_update_todo_unknown_status():
    items = [{"content": "Test", "status": "unknown"}]
    result = update_todo.invoke({"items": items})
    assert "[ ] Test" in result


# ============ submit_code 测试 ============

def _load_fixture(filename: str) -> str:
    """加载测试 fixture 文件"""
    fixture_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    with open(os.path.join(fixture_dir, filename), "r", encoding="utf-8") as f:
        return f.read()


def _effect_with_body(body: str) -> str:
    """Build an otherwise valid Effect V2 around one validation target."""
    return f'''class Effect {{
  static CONTRACT_VERSION = 2;
  static CONFIG = {{}};
  constructor() {{}}
  display(sketch, frameData, params) {{
    {body}
  }}
}}'''


def _effect_with_config(config: str) -> str:
    """Build an Effect V2 around one CONFIG validation target."""
    return f'''class Effect {{
  static CONTRACT_VERSION = 2;
  static CONFIG = {config};
  constructor() {{}}
  display(sketch, frameData, params) {{}}
}}'''


def test_submit_code_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    video_dir = tmp_path / "video-a"
    video_dir.mkdir()
    (video_dir / "smoothed_landmark.json").write_text(
        json.dumps({"0": [[100 + joint, 200 + joint] for joint in range(33)]}),
        encoding="utf-8",
    )
    monkeypatch.setattr("agent.code_tools.POSE_DATA_DIR", str(tmp_path))
    code = _load_fixture("sample_effect.js")
    result = submit_code.invoke({
        "code": code,
        "video_id": "video-a",
    })
    assert result["submitted"] is True
    assert result["code"] == code


def test_submit_code_invalid():
    code = _load_fixture("bad_effect.js")
    result = submit_code.invoke({
        "code": code,
    })
    assert result["submitted"] is False
    assert len(result["errors"]) > 0


def test_submit_code_rejects_runtime_failure_with_video_pose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """A statically valid Effect must not submit when real Pose rendering crashes."""
    video_dir = tmp_path / "video-a"
    video_dir.mkdir()
    pose_path = video_dir / "smoothed_landmark.json"
    pose_path.write_text(
        json.dumps({"0": [[100 + joint, 200 + joint] for joint in range(33)]}),
        encoding="utf-8",
    )
    monkeypatch.setattr("agent.code_tools.POSE_DATA_DIR", str(tmp_path), raising=False)
    code = _effect_with_body("sketch.nonexistentMethod();")

    result = submit_code.invoke({"code": code, "video_id": "video-a"})

    assert result["submitted"] is False
    assert any("nonexistentMethod" in error for error in result["errors"])


def test_submit_code_rejects_double_comma():
    """双逗号这类非法 JS 必须被 Node 语法检查拦截"""
    code = _load_fixture("sample_effect.js").replace(
        "type: 'range',", "type: 'range',,", 1
    )
    result = submit_code.invoke({"code": code})
    assert result["submitted"] is False
    assert any("syntax error" in e.lower() for e in result["errors"])


def test_pre_validate_fails_closed_without_node(monkeypatch):
    """缺少 node 时语法检查必须显式失败，不能静默放行"""
    from agent.pre_validate import pre_validate

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("node not found")

    monkeypatch.setattr("agent.pre_validate.subprocess.run", fake_run)
    ok, errors = pre_validate(_load_fixture("sample_effect.js"))
    assert ok is False
    assert any("node" in e.lower() for e in errors)


def test_pre_validate_ignores_comments_outside_config():
    """CONFIG 检查只扫描 CONFIG 块：注释里的 { jointName: {x,y} } 不应被当作参数"""
    from agent.pre_validate import pre_validate

    code = '''class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = { size: { default: 20, type: 'range', min: 1, max: 50, step: 1, label: 'Size', description: 'Controls the size' } };
  constructor() {}
  display(sketch, frameData, params) {
    // 轨迹点 { jointName: {x,y} }
    sketch.line(1, 2, 3, 4);
  }
}
'''
    ok, errors = pre_validate(code)
    assert ok is True
    assert not any("jointName" in e for e in errors)


def test_pre_validate_still_rejects_missing_default():
    """CONFIG 参数缺少 default 仍然要报错"""
    from agent.pre_validate import pre_validate

    code = "class Effect { static CONFIG = { size: { type: 'range' } }; constructor() {} display(s, f, p) {} }"
    ok, errors = pre_validate(code)
    assert ok is False
    assert any("CONFIG.size" in e and "default" in e for e in errors)


def test_pre_validate_requires_effect_v2_contract():
    """未声明 V2 契约的旧 Effect 必须在本地预校验阶段被拒绝。"""
    from agent.pre_validate import pre_validate

    code = "class Effect { static CONFIG = {}; constructor() {} display(s, f, p) {} }"

    ok, errors = pre_validate(code)

    assert ok is False
    assert any("CONTRACT_VERSION" in error and "2" in error for error in errors)


def test_pre_validate_allows_implicit_default_constructor():
    """A stateless V2 Effect may use JavaScript's implicit default constructor."""
    from agent.pre_validate import pre_validate

    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  display(sketch, frameData, params) {
    sketch.ellipse(10, 10, 5, 5);
  }
}"""

    passed, errors = pre_validate(code)

    assert passed, errors


def test_pre_validate_rejects_nested_control_binding_containers():
    from agent.pre_validate import pre_validate

    code = """class Effect {
  static CONTRACT_VERSION = 2;
  static CONTROL_BINDINGS = {
    timeMarkers: {
      event: { type: 'time_marker', id: 'marker-1' }
    }
  };
  static CONFIG = {};
  display(sketch, frameData, params) {}
}"""

    passed, errors = pre_validate(code)

    assert passed is False
    assert any(
        "CONTROL_BINDINGS.timeMarkers must contain only type and id" in error
        for error in errors
    )


def test_pre_validate_accepts_bounded_sequential_frame_state():
    """V2 Effect may retain bounded state when frame metadata controls updates and resets."""
    from agent.pre_validate import pre_validate

    code = '''class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  constructor() { this.particles = []; }
  display(sketch, frameData, params) {
    if (frameData.discontinuity !== 'none') this.particles = [];
    if (frameData.isNewFrame) {
      this.particles.push({ x: 10, y: 10, life: 30 });
      for (const particle of this.particles) particle.life -= frameData.deltaFrames || 1;
      this.particles = this.particles.filter((particle) => particle.life > 0).slice(-120);
    }
    for (const particle of this.particles) sketch.ellipse(particle.x, particle.y, 4, 4);
  }
}'''

    ok, errors = pre_validate(code)

    assert ok is True, errors


def test_pre_validate_accepts_frame_pure_effect_v2():
    """通过 Pose 历史重建轨迹的 V2 Effect 应通过本地预校验。"""
    from agent.pre_validate import pre_validate

    code = '''class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  constructor() {}
  display(sketch, frameData, params) {
    const trail = frameData.getJointHistory('left_wrist', 30);
    this._drawTrail(sketch, trail);
  }
  _drawTrail(sketch, trail) {
    for (let index = 1; index < trail.length; index++) {
      if (trail[index].connected) sketch.line(
        trail[index - 1].x, trail[index - 1].y,
        trail[index].x, trail[index].y
      );
    }
  }
}'''

    ok, errors = pre_validate(code)

    assert ok is True, errors


def test_pre_validate_requires_english_config_ui_copy():
    """CONFIG labels and descriptions containing Chinese are rejected."""
    from agent.pre_validate import pre_validate

    chinese_code = '''class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {
    size: { default: 10, type: 'range', min: 1, max: 50, step: 1, label: '大小', description: '控制粒子大小' },
  };
  constructor() {}
  display(sketch, frameData, params) {}
}'''
    english_code = chinese_code.replace("控制粒子大小", "Controls particle size").replace("大小", "Size")

    passed, errors = pre_validate(chinese_code)
    english_passed, english_errors = pre_validate(english_code)

    assert passed is False
    assert any("English" in error for error in errors)
    assert english_passed is True, english_errors


def test_pre_validate_accepts_only_the_four_supported_config_types():
    """CONFIG supports range, color, boolean, and select—no implicit fifth type."""
    from agent.pre_validate import pre_validate

    supported_configs = [
        "{ size: { default: 4, type: 'range', min: 1, max: 10, step: 1, label: 'Size', description: 'Controls the size' } }",
        "{ color: { default: '#12ABEF', type: 'color', label: 'Color', description: 'Controls the color' } }",
        "{ enabled: { default: true, type: 'boolean', label: 'Enabled', description: 'Shows the detail' } }",
        "{ mode: { default: 2, type: 'select', label: 'Mode', description: 'Chooses the mode', options: [{ label: 'Soft', value: 1 }, { label: 'Bold', value: 2 }] } }",
    ]

    for config in supported_configs:
        passed, errors = pre_validate(_effect_with_config(config))
        assert passed is True, errors

    passed, errors = pre_validate(_effect_with_config(
        "{ text: { default: 'hello', type: 'text', label: 'Text', description: 'Controls the text' } }"
    ))

    assert passed is False
    assert any("type" in error.lower() and "range" in error.lower() for error in errors), errors


@pytest.mark.parametrize(
    ("config", "error_fragment"),
    [
        (
            "{ size: { default: 4, type: 'range', min: 1, max: 10, step: 1, description: 'Controls the size' } }",
            "label",
        ),
        (
            "{ size: { default: 4, type: 'range', min: 1, max: 10, step: 1, label: 'Size' } }",
            "description",
        ),
        (
            "{ size: { default: 4, type: 'range', min: 1, max: 10, step: 1, label: '', description: 'Controls the size' } }",
            "label",
        ),
        (
            "{ size: { default: 4, type: 'range', min: 1, max: 10, step: 1, label: 'サイズ', description: 'Controls the size' } }",
            "English",
        ),
        (
            "{ size: { default: '4', type: 'range', min: 1, max: 10, step: 1, label: 'Size', description: 'Controls the size' } }",
            "number",
        ),
        (
            "{ size: { default: 4, type: 'range', min: 10, max: 1, step: 1, label: 'Size', description: 'Controls the size' } }",
            "min",
        ),
        (
            "{ size: { default: 12, type: 'range', min: 1, max: 10, step: 1, label: 'Size', description: 'Controls the size' } }",
            "default",
        ),
        (
            "{ size: { default: 4, type: 'range', min: 1, max: 10, step: 0, label: 'Size', description: 'Controls the size' } }",
            "step",
        ),
        (
            "{ tint: { default: '#123', type: 'color', label: 'Tint', description: 'Controls the tint' } }",
            "#RRGGBB",
        ),
        (
            "{ enabled: { default: 1, type: 'boolean', label: 'Enabled', description: 'Shows the detail' } }",
            "boolean",
        ),
        (
            "{ mode: { default: 'soft', type: 'select', label: 'Mode', description: 'Chooses the mode', options: [] } }",
            "options",
        ),
        (
            "{ mode: { default: 'soft', type: 'select', label: 'Mode', description: 'Chooses the mode', options: [{ label: 'Soft' }] } }",
            "value",
        ),
        (
            "{ mode: { default: 'soft', type: 'select', label: 'Mode', description: 'Chooses the mode', options: [{ label: 'Soft', value: 'soft' }, { label: 'Soft again', value: 'soft' }] } }",
            "unique",
        ),
        (
            "{ mode: { default: 1, type: 'select', label: 'Mode', description: 'Chooses the mode', options: [{ label: 'One as text', value: '1' }] } }",
            "default",
        ),
        (
            "{ mode: { default: buildMode(), type: 'select', label: 'Mode', description: 'Chooses the mode', options: [{ label: 'Soft', value: 'soft' }] } }",
            "literal",
        ),
    ],
)
def test_pre_validate_rejects_malformed_type_specific_config(config, error_fragment):
    """Every CONFIG type must provide complete metadata the frontend can render."""
    from agent.pre_validate import pre_validate

    passed, errors = pre_validate(_effect_with_config(config))

    assert passed is False
    assert any(error_fragment.lower() in error.lower() for error in errors), errors


def test_extract_config_preserves_four_control_default_types():
    """Default extraction must preserve primitive types from validated CONFIG."""
    from agent.extract_config import extract_config

    code = _effect_with_config("""{
      size: { default: 4, type: 'range', min: 1, max: 10, step: 1, label: 'Size', description: 'Controls the size' },
      tint: { default: '#12ABEF', type: 'color', label: 'Tint', description: 'Controls the tint' },
      enabled: { default: true, type: 'boolean', label: 'Enabled', description: 'Shows the detail' },
      mode: { default: 2, type: 'select', label: 'Mode', description: 'Chooses the mode', options: [{ label: 'Soft', value: 1 }, { label: 'Bold', value: 2 }] },
    }""")

    passed, params_json = extract_config(code)

    assert passed is True
    assert json.loads(params_json) == {
        "size": 4,
        "tint": "#12ABEF",
        "enabled": True,
        "mode": 2,
    }


def test_extract_config_rejects_non_primitive_default():
    """Default extraction cannot silently accept a value the validator rejects."""
    from agent.extract_config import extract_config

    code = _effect_with_config(
        "{ mode: { default: ['soft'], type: 'select', label: 'Mode', description: 'Chooses the mode', options: [{ label: 'Soft', value: 'soft' }] } }"
    )

    passed, error = extract_config(code)

    assert passed is False
    assert "default" in error.lower()


def test_pre_validate_ignores_fake_config_declarations_in_comments():
    """A comment cannot hide a later dynamic CONFIG assignment."""
    from agent.pre_validate import pre_validate

    code = '''class Effect {
  // static CONFIG = {};
  static CONTRACT_VERSION = 2;
  static CONFIG = buildConfig();
  constructor() {}
  display(sketch, frameData, params) {}
}'''

    passed, errors = pre_validate(code)

    assert passed is False
    assert any("literal" in error.lower() for error in errors), errors


@pytest.mark.parametrize(
    ("statement", "api_name"),
    [
        ("sketch.clear();", "clear"),
        ("sketch.background(0);", "background"),
        ("sketch.erase();", "erase"),
        ("sketch.noErase();", "noErase"),
        ("sketch.createCanvas(640, 360);", "createCanvas"),
        ("sketch.resizeCanvas(320, 180);", "resizeCanvas"),
        ("sketch.remove();", "remove"),
        ("sketch.loop();", "loop"),
        ("sketch.noLoop();", "noLoop"),
        ("sketch.redraw();", "redraw"),
        ("sketch.frameRate(30);", "frameRate"),
    ],
    ids=lambda value: value if isinstance(value, str) and "(" not in value else None,
)
def test_pre_validate_rejects_host_managed_p5_apis(statement, api_name):
    """An Effect must not control the shared canvas or the host render loop."""
    from agent.pre_validate import pre_validate

    passed, errors = pre_validate(_effect_with_body(statement))

    assert passed is False
    assert any(api_name.lower() in error.lower() for error in errors), errors


@pytest.mark.parametrize(
    ("statement", "api_name"),
    [
        ("eval('1 + 1');", "eval"),
        ("const build = new Function('return 1'); build();", "Function"),
    ],
)
def test_pre_validate_rejects_dynamic_code_execution(statement, api_name):
    """Generated code must not create executable code that bypasses validation."""
    from agent.pre_validate import pre_validate

    passed, errors = pre_validate(_effect_with_body(statement))

    assert passed is False
    assert any(api_name.lower() in error.lower() for error in errors), errors


@pytest.mark.parametrize(
    ("statement", "api_name"),
    [
        ("fetch('/api/health');", "fetch"),
        ("const request = new XMLHttpRequest();", "XMLHttpRequest"),
        ("const socket = new WebSocket('wss://example.com');", "WebSocket"),
        ("const events = new EventSource('/events');", "EventSource"),
        ("navigator.sendBeacon('/log', 'x');", "sendBeacon"),
        ("import('https://example.com/effect.js');", "import"),
    ],
)
def test_pre_validate_rejects_network_access(statement, api_name):
    """An Effect must not perform external or same-origin network I/O."""
    from agent.pre_validate import pre_validate

    passed, errors = pre_validate(_effect_with_body(statement))

    assert passed is False
    assert any(api_name.lower() in error.lower() for error in errors), errors


@pytest.mark.parametrize(
    ("statement", "api_name"),
    [
        ("document.querySelector('canvas');", "document"),
        ("window.localStorage.setItem('x', '1');", "localStorage"),
        ("globalThis.sessionStorage.getItem('x');", "sessionStorage"),
    ],
)
def test_pre_validate_rejects_dom_and_browser_storage(statement, api_name):
    """Effect code must stay inside the p5 and frame-data capability boundary."""
    from agent.pre_validate import pre_validate

    passed, errors = pre_validate(_effect_with_body(statement))

    assert passed is False
    assert any(api_name.lower() in error.lower() for error in errors), errors


@pytest.mark.parametrize(
    ("statement", "api_name"),
    [
        ("const now = Date.now();", "Date.now"),
        ("const now = new Date();", "Date"),
        ("const now = performance.now();", "performance.now"),
        ("const now = sketch.millis();", "millis"),
        ("setTimeout(() => {}, 10);", "setTimeout"),
        ("setInterval(() => {}, 10);", "setInterval"),
        ("requestAnimationFrame(() => {});", "requestAnimationFrame"),
        ("queueMicrotask(() => {});", "queueMicrotask"),
    ],
)
def test_pre_validate_rejects_wall_clock_and_async_scheduling(statement, api_name):
    """All animation must advance synchronously from host-owned video time."""
    from agent.pre_validate import pre_validate

    passed, errors = pre_validate(_effect_with_body(statement))

    assert passed is False
    assert any(api_name.lower() in error.lower() for error in errors), errors


@pytest.mark.parametrize(
    ("statement", "api_name"),
    [
        ("const value = crypto.getRandomValues(new Uint32Array(1));", "getRandomValues"),
        ("const value = crypto.randomUUID();", "randomUUID"),
        ("sketch.randomSeed(10);", "randomSeed"),
        ("sketch.noiseSeed(10);", "noiseSeed"),
    ],
)
def test_pre_validate_rejects_nondeterministic_randomness(statement, api_name):
    """Shared seeds and unnecessary entropy capabilities remain unavailable."""
    from agent.pre_validate import pre_validate

    passed, errors = pre_validate(_effect_with_body(statement))

    assert passed is False
    assert any(api_name.lower() in error.lower() for error in errors), errors


@pytest.mark.parametrize(
    "expression",
    ["Math.random()", "sketch.random(0, 1)"],
)
def test_pre_validate_allows_random_values_saved_on_new_frames(expression):
    """Sequential particles may sample randomness once and retain the result."""
    from agent.pre_validate import pre_validate

    code = _effect_with_body(f"""
      if (frameData.isNewFrame) this.value = {expression};
      sketch.ellipse(this.value || 0, 10, 4, 4);
    """)

    passed, errors = pre_validate(code)

    assert passed is True, errors


def test_pre_validate_allows_non_canvas_collection_clear():
    """The clear rule must not reject an unrelated local Map operation."""
    from agent.pre_validate import pre_validate

    code = _effect_with_body("const localValues = new Map(); localValues.clear();")

    passed, errors = pre_validate(code)

    assert passed is True, errors


def test_pre_validate_allows_frame_hash_and_frame_driven_noise():
    """Pure frame variation and session-stable frame-driven noise remain valid."""
    from agent.pre_validate import pre_validate

    code = _effect_with_body("""
      const seed = frameData.currentFrame * 1103515245 + 12345;
      const variation = ((seed >>> 0) % 1000) / 1000;
      const drift = sketch.noise(0.2, 0.7, frameData.currentFrame * 0.05);
      sketch.ellipse(20 + variation, 20 + drift, 4, 4);
    """)

    passed, errors = pre_validate(code)

    assert passed is True, errors
