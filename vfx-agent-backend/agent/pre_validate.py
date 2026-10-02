import os
import re
import subprocess
import tempfile
from typing import Tuple

from .config_contract import validate_static_config
from .control_bindings import extract_control_bindings


def pre_validate(code: str) -> Tuple[bool, list[str]]:
    """
    Run static pre-validation on generated effect code.

    Args:
        code: P5.js effect code.

    Returns:
        A passed flag and validation errors.
    """
    errors = []

    # JavaScript syntax errors are fatal and return immediately.
    syntax_ok, syntax_errors = _check_js_syntax(code)
    if not syntax_ok:
        return False, syntax_errors

    # Require the Effect class.
    if not re.search(r'class\s+Effect\s*\{', code):
        errors.append("Missing class Effect definition")

    # Require the sequential-frame V2 contract.
    if not re.search(r'static\s+CONTRACT_VERSION\s*=\s*2\s*;', code):
        errors.append("Effect must declare static CONTRACT_VERSION = 2")

    # Validate static CONFIG metadata.
    config_ok, config_errors = _check_static_config(code)
    errors.extend(config_errors)

    # Validate optional editor-control bindings without executing generated code.
    _, binding_errors = extract_control_bindings(code)
    errors.extend(binding_errors)

    # Require the display method.
    if not re.search(r'display\s*\(', code):
        errors.append("Missing display() method")

    # Reject APIs managed by the host runtime.
    forbidden_ok, forbidden_errors = _check_forbidden_apis(code)
    errors.extend(forbidden_errors)

    return len(errors) == 0, errors


def _check_js_syntax(code: str) -> Tuple[bool, list[str]]:
    """Check modern JavaScript syntax with Node."""
    try:
        fd, path = tempfile.mkstemp(suffix=".js", prefix="vfx_prevalidate_")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
            proc = subprocess.run(
                ["node", "--check", path],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if proc.returncode == 0:
                return True, []
            detail = (proc.stderr or proc.stdout or "").strip()
            return False, [f"JavaScript syntax error: {detail[:300]}"]
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
    except FileNotFoundError:
        return False, ["Cannot check JavaScript syntax because Node.js is unavailable"]
    except subprocess.TimeoutExpired:
        return False, ["JavaScript syntax check timed out"]


def _check_static_config(code: str) -> Tuple[bool, list[str]]:
    """Validate static CONFIG without executing generated code."""
    _, errors = validate_static_config(code)
    return len(errors) == 0, errors


def _check_forbidden_apis(code: str) -> Tuple[bool, list[str]]:
    """Reject host, external-I/O, clock, and shared-seed capabilities."""
    errors = []
    executable = _mask_js_comments_and_strings(code)

    forbidden_patterns: list[tuple[str, str]] = [
        # The frontend owns the shared canvas and render loop.
        (r'\bsetup\s*\(', 'Do not use setup(); use constructor()'),
        (r'\bdraw\s*\(', 'Do not use draw(); use display()'),
        (r'\bcreateCanvas\s*\(', 'Do not use createCanvas(); the host runtime manages the canvas'),
        (r'\bresizeCanvas\s*\(', 'Do not use resizeCanvas(); the host runtime manages canvas size'),
        (r'\bbackground\s*\(', 'Do not use background(); it clears other effects'),
        (r'\bsketch\s*\.\s*clear\s*\(', 'Do not use sketch.clear(); the host runtime clears the shared canvas'),
        (r'\bsketch\s*\.\s*erase\s*\(', 'Do not use sketch.erase(); it can erase other effects'),
        (r'\bsketch\s*\.\s*noErase\s*\(', 'Do not use sketch.noErase(); erase mode is owned by the host runtime'),
        (r'\bsketch\s*\.\s*remove\s*\(', 'Do not use sketch.remove(); the host runtime owns the canvas'),
        (r'\bsketch\s*\.\s*loop\s*\(', 'Do not use sketch.loop(); the host runtime owns playback'),
        (r'\bsketch\s*\.\s*noLoop\s*\(', 'Do not use sketch.noLoop(); the host runtime owns playback'),
        (r'\bsketch\s*\.\s*redraw\s*\(', 'Do not use sketch.redraw(); the host runtime schedules rendering'),
        (r'\bsketch\s*\.\s*frameRate\s*\(', 'Do not use sketch.frameRate(); the host runtime owns playback timing'),

        # Dynamic code can bypass every other static rule.
        (r'\beval\s*\(', 'Do not use eval(); dynamic code execution is forbidden'),
        (r'(?<![\w$.])(?:new\s+)?Function\s*\(', 'Do not use Function(); dynamic code execution is forbidden'),

        # Effect code is a local renderer and must not perform network I/O.
        (r'(?<![\w$.])fetch\s*\(', 'Do not use fetch(); network access is forbidden'),
        (r'\bnew\s+XMLHttpRequest\s*\(', 'Do not use XMLHttpRequest; network access is forbidden'),
        (r'\bnew\s+WebSocket\s*\(', 'Do not use WebSocket; network access is forbidden'),
        (r'\bnew\s+EventSource\s*\(', 'Do not use EventSource; network access is forbidden'),
        (r'\bnavigator\s*\.\s*sendBeacon\s*\(', 'Do not use sendBeacon; network access is forbidden'),
        (r'\bimport\s*\(', 'Do not use import(); external code loading is forbidden'),

        # Browser globals escape the p5/frameData/params capability boundary.
        (r'(?<![\w$.])document\b', 'Do not access document; DOM access is forbidden'),
        (r'\b(?:window|globalThis)\s*\.\s*localStorage\b|(?<![\w$.])localStorage\b', 'Do not access localStorage; browser storage is forbidden'),
        (r'\b(?:window|globalThis)\s*\.\s*sessionStorage\b|(?<![\w$.])sessionStorage\b', 'Do not access sessionStorage; browser storage is forbidden'),
        (r'(?<![\w$.])window\b', 'Do not access window; browser-global access is forbidden'),
        (r'(?<![\w$.])globalThis\b', 'Do not access globalThis; browser-global access is forbidden'),

        # The host runtime owns video time and render scheduling.
        (r'\bDate\s*\.\s*now\s*\(', 'Do not use Date.now(); use frameData.currentFrame'),
        (r'\bnew\s+Date\s*\(', 'Do not use Date; use frameData.currentFrame'),
        (r'\bperformance\s*\.\s*now\s*\(', 'Do not use performance.now(); use frameData.currentFrame'),
        (r'\b(?:sketch\s*\.\s*)?millis\s*\(', 'Do not use millis(); use frameData.currentFrame'),
        (r'\bsetTimeout\s*\(', 'Do not use setTimeout(); rendering must stay synchronous'),
        (r'\bsetInterval\s*\(', 'Do not use setInterval(); rendering must stay synchronous'),
        (r'\brequestAnimationFrame\s*\(', 'Do not use requestAnimationFrame(); the host runtime schedules rendering'),
        (r'\bqueueMicrotask\s*\(', 'Do not use queueMicrotask(); rendering must stay synchronous'),

        # Shared mutable seeds can change the output of other Effects.
        (r'\bcrypto\s*\.\s*getRandomValues\s*\(', 'Do not use crypto.getRandomValues(); sample Math.random() or sketch.random() during a new-frame update'),
        (r'\bcrypto\s*\.\s*randomUUID\s*\(', 'Do not use crypto.randomUUID(); sample Math.random() or sketch.random() during a new-frame update'),
        (r'\b(?:sketch\s*\.\s*)?randomSeed\s*\(', 'Do not use randomSeed(); it mutates shared random state'),
        (r'\b(?:sketch\s*\.\s*)?noiseSeed\s*\(', 'Do not use noiseSeed(); it mutates shared noise state'),
    ]

    for pattern, message in forbidden_patterns:
        if re.search(pattern, executable):
            errors.append(message)

    return len(errors) == 0, errors


def _mask_js_comments_and_strings(code: str) -> str:
    """Mask comments and literal text while preserving executable expressions."""
    output = list(code)
    length = len(code)
    index = 0
    modes: list[dict[str, int | str]] = [{"kind": "code"}]

    def mask(start: int, end: int) -> None:
        for position in range(start, end):
            if output[position] not in "\r\n":
                output[position] = " "

    while index < length:
        mode = modes[-1]
        kind = mode["kind"]

        if kind == "template":
            if code[index] == "\\":
                mask(index, min(index + 2, length))
                index += 2
                continue
            if code[index] == "`":
                mask(index, index + 1)
                modes.pop()
                index += 1
                continue
            if code.startswith("${", index):
                mask(index, index + 2)
                modes.append({"kind": "template_expression", "depth": 1})
                index += 2
                continue
            mask(index, index + 1)
            index += 1
            continue

        if code.startswith("//", index):
            end = code.find("\n", index + 2)
            end = length if end == -1 else end
            mask(index, end)
            index = end
            continue

        if code.startswith("/*", index):
            closing = code.find("*/", index + 2)
            end = length if closing == -1 else closing + 2
            mask(index, end)
            index = end
            continue

        if code[index] in "'\"":
            quote = code[index]
            start = index
            index += 1
            while index < length:
                if code[index] == "\\":
                    index += 2
                    continue
                if code[index] == quote:
                    index += 1
                    break
                index += 1
            mask(start, min(index, length))
            continue

        if code[index] == "`":
            mask(index, index + 1)
            modes.append({"kind": "template"})
            index += 1
            continue

        if kind == "template_expression":
            if code[index] == "{":
                mode["depth"] = int(mode["depth"]) + 1
            elif code[index] == "}":
                mode["depth"] = int(mode["depth"]) - 1
                if mode["depth"] == 0:
                    mask(index, index + 1)
                    modes.pop()
                    index += 1
                    continue

        index += 1

    return "".join(output)
