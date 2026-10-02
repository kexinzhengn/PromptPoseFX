"""verify_effect.py 冒烟测试：合法案例通过，非法代码被拦截。"""
import os
import subprocess
import sys


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(BACKEND_DIR, "scripts", "verify_effect.py")


def test_verify_effect_passes_v2_history_fixture(pose_timeline_path):
    """使用 Pose 历史的 V2 金标准案例应通过三步验证（不保存）。"""
    code = os.path.join(BACKEND_DIR, "tests", "fixtures", "sample_effect_v2_history.js")
    proc = subprocess.run(
        [
            sys.executable,
            SCRIPT,
            code,
            "--frames",
            "30",
            "--pose-data",
            str(pose_timeline_path),
        ],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Static validation" in proc.stdout
    assert "Simulated rendering" in proc.stdout
    assert "✅" in proc.stdout


def test_verify_effect_rejects_bad_code(tmp_path):
    """使用 background() 的代码必须在静态校验阶段被拦截"""
    bad = tmp_path / "bad.js"
    bad.write_text(
        "class Effect { static CONFIG = {}; constructor() {} "
        "display(s, f, p) { s.background(0); } }",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, SCRIPT, str(bad), "--frames", "10"],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode != 0
    assert "Do not use background" in proc.stdout


def test_verify_effect_supports_transforms_and_console_log(tmp_path, pose_timeline_path):
    """Supported transforms and console logging must render successfully."""
    code = tmp_path / "transform.js"
    code.write_text(
        """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {
    size: { default: 10, type: 'range', min: 1, max: 100, step: 1, label: 'Size', description: 'Higher values make the shape more visible' },
  };
  constructor() {}
  display(sketch, frameData, params) {
    sketch.push();
    sketch.translate(320, 180);
    sketch.rotate(0.1);
    sketch.scale(1);
    sketch.noStroke();
    sketch.fill(255, 0, 0, 100);
    sketch.ellipse(0, 0, params.size, params.size);
    sketch.pop();
    console.log('debug output should not break parser');
  }
}
""",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            SCRIPT,
            str(code),
            "--frames",
            "5",
            "--pose-data",
            str(pose_timeline_path),
        ],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "frames completed" in proc.stdout


def test_verify_effect_rejects_unsupported_p5_color_copy(tmp_path, pose_timeline_path):
    """The simulator must not provide Color.copy(), which p5 2.3 lacks."""
    code = tmp_path / "unsupported-color-copy.js"
    code.write_text(
        """class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  constructor() {}
  display(sketch, frameData, params) {
    const tint = sketch.color('#ff0000');
    sketch.fill(tint.copy());
    sketch.ellipse(10, 10, 5, 5);
  }
}
""",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            SCRIPT,
            str(code),
            "--frames",
            "1",
            "--pose-data",
            str(pose_timeline_path),
        ],
        capture_output=True, text=True, timeout=120,
    )

    assert proc.returncode != 0
    assert "copy is not a function" in proc.stdout
