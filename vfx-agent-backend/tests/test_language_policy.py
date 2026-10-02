"""Enforce the English-only policy for runtime agent source."""

import re
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parents[1] / "agent"
SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def test_runtime_agent_source_and_comments_use_english() -> None:
    """Agent prompts, user messages, tool descriptions, and comments stay English."""
    violations: list[str] = []
    runtime_paths = [*AGENT_ROOT.glob("*.py"), *SCRIPT_ROOT.glob("*.py")]
    for path in sorted(runtime_paths):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if CJK_PATTERN.search(line):
                violations.append(f"{path.name}:{line_number}")

    assert violations == []
