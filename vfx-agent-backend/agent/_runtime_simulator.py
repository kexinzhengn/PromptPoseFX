"""Internal Node adapter used by the hard-validation module."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


JOINT_NAMES = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer", "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "left_mouth", "right_mouth", "left_shoulder", "right_shoulder", "left_elbow",
    "right_elbow", "left_wrist", "right_wrist", "left_pinky", "right_pinky", "left_index", "right_index",
    "left_thumb", "right_thumb", "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle",
    "left_heel", "right_heel", "left_foot_index", "right_foot_index",
]

_JOINT_NAMES_JS = json.dumps(JOINT_NAMES)

_NODE_RENDERER = r"""
const fs = require('fs');
const { pathToFileURL } = require('url');

(async () => {
const [,, codePath, paramsPath, posePath, framesArg, editorStatePath, controlRuntimePath, widthArg, heightArg, requiredControlIdsArg] = process.argv;
const { createFrameControls } = await import(pathToFileURL(controlRuntimePath).href);
const code = fs.readFileSync(codePath, 'utf-8');
let params = {};
try { params = JSON.parse(fs.readFileSync(paramsPath, 'utf-8')); } catch (e) {}
const editorState = JSON.parse(fs.readFileSync(editorStatePath, 'utf-8'));
const raw = JSON.parse(fs.readFileSync(posePath, 'utf-8'));
const JOINT_NAMES = __JOINT_NAMES__;
const frameWidth = Number(widthArg);
const frameHeight = Number(heightArg);
const requiredControlIds = new Set(JSON.parse(requiredControlIdsArg || '[]'));

function getJointsAtFrame(frame) {
  const landmarks = raw[String(frame)] || [];
  const joints = {};
  for (let index = 0; index < landmarks.length && index < JOINT_NAMES.length; index++) {
    joints[JOINT_NAMES[index]] = { x: landmarks[index][0], y: landmarks[index][1] };
  }
  return joints;
}

function isValid(position) {
  return !!position && !(position.x === 0 && position.y === 0);
}

function getJointHistory(jointName, currentFrame, lookbackFrames) {
  if (!JOINT_NAMES.includes(jointName)) return [];
  const requested = Number.isFinite(lookbackFrames) ? Math.floor(lookbackFrames) : 1;
  const count = Math.min(120, Math.max(1, requested));
  const startFrame = Math.max(0, currentFrame - count + 1);
  const history = [];

  for (let frame = startFrame; frame <= currentFrame; frame++) {
    const position = getJointsAtFrame(frame)[jointName];
    const previous = getJointsAtFrame(frame - 1)[jointName];
    const valid = isValid(position);
    const connected = valid && isValid(previous);
    const vx = connected ? position.x - previous.x : 0;
    const vy = connected ? position.y - previous.y : 0;
    history.push({
      frame,
      x: valid ? position.x : null,
      y: valid ? position.y : null,
      vx,
      vy,
      speed: Math.hypot(vx, vy),
      valid,
      connected,
    });
  }
  return history;
}

function makeColor(...values) {
  if (values.length === 0 || values[0] === undefined) throw new Error('color(undefined)');
  return {
    _isColor: true,
    values,
    alpha: 255,
    setAlpha(a) { this.alpha = a; return this; },
  };
}

function normalize(value) {
  if (typeof value === 'number' && !Number.isFinite(value)) return String(value);
  if (value && value._isColor) {
    return { color: value.values.map(normalize), alpha: normalize(value.alpha) };
  }
  if (value && value._isGraphics) {
    return { graphics: value._commands.map(normalize) };
  }
  if (Array.isArray(value)) return value.map(normalize);
  if (value && typeof value === 'object') {
    const normalized = {};
    for (const key of Object.keys(value).sort()) {
      if (typeof value[key] !== 'function') {
        normalized[key] = normalize(value[key]);
      }
    }
    return normalized;
  }
  return value;
}

let activeTrace = null;
let activeControlAccesses = null;
let countDrawCalls = true;
const count = {
  line: 0, ellipse: 0, arc: 0, rect: 0, point: 0, triangle: 0,
  quad: 0, bezier: 0, image: 0, text: 0, shape: 0,
};

function recordCommand(name, args) {
  const command = [name, ...Array.from(args).map(normalize)];
  if (activeTrace) activeTrace.push(command);
  return command;
}

function recordDraw(name, args, traceName = name) {
  if (countDrawCalls) count[name]++;
  return recordCommand(traceName, args);
}

function makeGraphics() {
  const graphics = {
    _isGraphics: true,
    _commands: [],
    width: 640,
    height: 360,
  };
  const recordGraphics = (name, args, drawName = null) => {
    const command = [name, ...Array.from(args).map(normalize)];
    graphics._commands.push(command);
    if (drawName && countDrawCalls) count[drawName]++;
    if (activeTrace) activeTrace.push([`graphics.${name}`, ...Array.from(args).map(normalize)]);
  };
  Object.assign(graphics, {
    push(...args) { recordGraphics('push', args); },
    pop(...args) { recordGraphics('pop', args); },
    background(...args) { graphics._commands = []; recordGraphics('background', args); },
    clear(...args) { graphics._commands = []; recordGraphics('clear', args); },
    color: (...values) => values[0]?._isColor ? values[0] : makeColor(...values),
    lerpColor: (first, second, amount) => makeColor({ lerp: [normalize(first), normalize(second), amount] }),
    stroke(...args) { recordGraphics('stroke', args); },
    noStroke(...args) { recordGraphics('noStroke', args); },
    fill(...args) { recordGraphics('fill', args); },
    noFill(...args) { recordGraphics('noFill', args); },
    strokeWeight(...args) { recordGraphics('strokeWeight', args); },
    blendMode(...args) { recordGraphics('blendMode', args); },
    translate(...args) { recordGraphics('translate', args); },
    rotate(...args) { recordGraphics('rotate', args); },
    scale(...args) { recordGraphics('scale', args); },
    angleMode(...args) { recordGraphics('angleMode', args); },
    rectMode(...args) { recordGraphics('rectMode', args); },
    ellipseMode(...args) { recordGraphics('ellipseMode', args); },
    colorMode(...args) { recordGraphics('colorMode', args); },
    strokeCap(...args) { recordGraphics('strokeCap', args); },
    strokeJoin(...args) { recordGraphics('strokeJoin', args); },
    line(...args) { recordGraphics('line', args, 'line'); },
    ellipse(...args) { recordGraphics('ellipse', args, 'ellipse'); },
    arc(...args) { recordGraphics('arc', args, 'arc'); },
    rect(...args) { recordGraphics('rect', args, 'rect'); },
    point(...args) { recordGraphics('point', args, 'point'); },
    triangle(...args) { recordGraphics('triangle', args, 'triangle'); },
    quad(...args) { recordGraphics('quad', args, 'quad'); },
    bezier(...args) { recordGraphics('bezier', args, 'bezier'); },
    beginShape(...args) { recordGraphics('beginShape', args); },
    endShape(...args) { recordGraphics('endShape', args, 'shape'); },
    vertex(...args) { recordGraphics('vertex', args); },
    curveVertex(...args) { recordGraphics('curveVertex', args); },
    text(...args) { recordGraphics('text', args, 'text'); },
    textSize(...args) { recordGraphics('textSize', args); },
    textAlign(...args) { recordGraphics('textAlign', args); },
    textFont(...args) { recordGraphics('textFont', args); },
  });
  return graphics;
}

const sketch = {
  push(...args) { recordCommand('push', args); },
  pop(...args) { recordCommand('pop', args); },
  color: (...values) => values[0]?._isColor ? values[0] : makeColor(...values),
  lerpColor: (first, second, amount) => makeColor({ lerp: [normalize(first), normalize(second), amount] }),
  noise: () => 0.5,
  stroke(...args) { recordCommand('stroke', args); },
  noStroke(...args) { recordCommand('noStroke', args); },
  fill(...args) { recordCommand('fill', args); },
  noFill(...args) { recordCommand('noFill', args); },
  strokeWeight(...args) { recordCommand('strokeWeight', args); },
  blendMode(...args) { recordCommand('blendMode', args); },
  createGraphics: (...args) => { recordCommand('createGraphics', args); return makeGraphics(); },
  image(...args) { recordDraw('image', args); },
  translate(...args) { recordCommand('translate', args); },
  rotate(...args) { recordCommand('rotate', args); },
  scale(...args) { recordCommand('scale', args); },
  angleMode(...args) { recordCommand('angleMode', args); },
  rectMode(...args) { recordCommand('rectMode', args); },
  ellipseMode(...args) { recordCommand('ellipseMode', args); },
  colorMode(...args) { recordCommand('colorMode', args); },
  strokeCap(...args) { recordCommand('strokeCap', args); },
  strokeJoin(...args) { recordCommand('strokeJoin', args); },
  red: () => 128, green: () => 128, blue: () => 128, alpha: () => 128,
  hue: () => 128, saturation: () => 128, brightness: () => 128,
  map: (v, a, b, c, d) => c + ((v - a) / ((b - a) || 1)) * (d - c),
  constrain: (v, lo, hi) => Math.min(hi, Math.max(lo, v)),
  lerp: (a, b, t) => a + (b - a) * t,
  dist: (x1, y1, x2, y2) => Math.hypot(x2 - x1, y2 - y1),
  norm: (v, a, b) => (v - a) / ((b - a) || 1),
  degrees: (r) => r * 180 / Math.PI,
  radians: (d) => d * Math.PI / 180,
  line(...args) { recordDraw('line', args); },
  ellipse(...args) { recordDraw('ellipse', args); },
  arc(...args) { recordDraw('arc', args); },
  rect(...args) { recordDraw('rect', args); },
  point(...args) { recordDraw('point', args); },
  triangle(...args) { recordDraw('triangle', args); },
  quad(...args) { recordDraw('quad', args); },
  bezier(...args) { recordDraw('bezier', args); },
  beginShape(...args) { recordCommand('beginShape', args); },
  endShape(...args) { recordDraw('shape', args, 'endShape'); },
  vertex(...args) { recordCommand('vertex', args); },
  curveVertex(...args) { recordCommand('curveVertex', args); },
  text(...args) { recordDraw('text', args); },
  textSize(...args) { recordCommand('textSize', args); },
  textAlign(...args) { recordCommand('textAlign', args); },
  textFont(...args) { recordCommand('textFont', args); },
  noLoop(...args) { recordCommand('noLoop', args); },
  background() { throw new Error('background() is forbidden'); },
  clear() { throw new Error('clear() is forbidden'); },
  random(minimum, maximum) {
    if (minimum === undefined) return Math.random();
    if (maximum === undefined) return Math.random() * minimum;
    return minimum + Math.random() * (maximum - minimum);
  },
  randomSeed() { throw new Error('randomSeed() is forbidden'); },
  noiseSeed() { throw new Error('noiseSeed() is forbidden'); },
};

const baseFrameCount = Math.max(0, Math.floor(Number(framesArg)));
let error = null;

function createEffectClass() {
  return new Function(`${code}\nreturn Effect;`)();
}

function buildFrameData(frame, metadata = {}, activeEditorState = editorState) {
  const bindings = EffectClass.CONTROL_BINDINGS || {};
  const controls = createFrameControls({
    bindings,
    editorState: activeEditorState,
    width: frameWidth,
    height: frameHeight,
    currentFrame: frame,
    getJointsAtFrame,
  });
  const recordBinding = (bindingName) => {
    const binding = bindings[bindingName];
    if (binding?.id) activeControlAccesses?.add(binding.id);
  };
  return {
    joints: getJointsAtFrame(frame),
    currentFrame: frame,
    width: frameWidth,
    height: frameHeight,
    isNewFrame: metadata.isNewFrame ?? true,
    deltaFrames: metadata.deltaFrames ?? (frame === 0 ? 0 : 1),
    discontinuity: metadata.discontinuity ?? 'none',
    getJointHistory: (jointName, lookbackFrames) => (
      getJointHistory(jointName, frame, lookbackFrames)
    ),
    controls: {
      getPoint(bindingName, requestedFrame) {
        recordBinding(bindingName);
        return controls.getPoint(bindingName, requestedFrame);
      },
      getPath(bindingName) {
        recordBinding(bindingName);
        return controls.getPath(bindingName);
      },
      getTimeMarker(bindingName) {
        recordBinding(bindingName);
        return controls.getTimeMarker(bindingName);
      },
    },
  };
}

function renderFrame(
  effect,
  frame,
  collectCounts,
  metadata = {},
  activeEditorState = editorState,
) {
  const previousTrace = activeTrace;
  const previousCountMode = countDrawCalls;
  const previousControlAccesses = activeControlAccesses;
  activeTrace = [];
  activeControlAccesses = new Set();
  countDrawCalls = collectCounts;
  try {
    effect.display(sketch, buildFrameData(frame, metadata, activeEditorState), params);
    return { trace: activeTrace, accesses: [...activeControlAccesses], error: null };
  } catch (renderError) {
    return {
      trace: activeTrace,
      accesses: [...activeControlAccesses],
      error: `frame ${frame}: ${renderError.message}`,
    };
  } finally {
    activeTrace = previousTrace;
    activeControlAccesses = previousControlAccesses;
    countDrawCalls = previousCountMode;
  }
}

const EffectClass = createEffectClass();

function buildValidationWindows() {
  const poseFrames = Object.keys(raw)
    .map(Number)
    .filter(Number.isInteger)
    .sort((first, second) => first - second);
  if (poseFrames.length === 0 || baseFrameCount === 0) return [];

  const poseStart = poseFrames[0];
  const poseEnd = poseFrames[poseFrames.length - 1];
  const activeInterval = editorState?.active_interval;
  const clipStart = Math.max(poseStart, activeInterval?.start_frame ?? poseStart);
  const clipEnd = Math.min(poseEnd, activeInterval?.end_frame ?? poseEnd);
  if (clipStart > clipEnd) return [];

  const windows = [];
  const addWindow = (start, end) => {
    const boundedStart = Math.max(clipStart, Math.floor(start));
    const boundedEnd = Math.min(clipEnd, Math.floor(end));
    if (boundedStart <= boundedEnd) windows.push({ start: boundedStart, end: boundedEnd });
  };
  const addAnchor = (frame) => addWindow(frame - 1, frame + 1);

  addWindow(clipStart, clipStart + baseFrameCount - 1);
  if (activeInterval) addWindow(clipEnd - 1, clipEnd);

  const bindings = EffectClass.CONTROL_BINDINGS || {};
  const markersById = new Map(
    (editorState?.markers || []).map((marker) => [marker.id, marker]),
  );
  const markerFrames = new Set();
  for (const binding of Object.values(bindings)) {
    if (binding?.type === 'time_marker') {
      const marker = markersById.get(binding.id);
      if (marker) markerFrames.add(marker.frame);
    }
  }
  const sortedMarkerFrames = Array.from(markerFrames).sort((first, second) => first - second);
  for (let index = 0; index < sortedMarkerFrames.length; index++) {
    addAnchor(sortedMarkerFrames[index]);
    if (index > 0) {
      addAnchor(Math.floor((sortedMarkerFrames[index - 1] + sortedMarkerFrames[index]) / 2));
    }
  }

  windows.sort((first, second) => first.start - second.start || first.end - second.end);
  const merged = [];
  for (const window of windows) {
    const previous = merged[merged.length - 1];
    if (previous && window.start <= previous.end + 1) {
      previous.end = Math.max(previous.end, window.end);
    } else {
      merged.push({ ...window });
    }
  }
  return merged;
}

function buildForwardSkipPairs() {
  const poseFrames = Object.keys(raw).map(Number).filter(Number.isInteger);
  if (poseFrames.length === 0) return [];
  const poseStart = Math.min(...poseFrames);
  const poseEnd = Math.max(...poseFrames);
  const activeInterval = editorState?.active_interval;
  const clipStart = Math.max(poseStart, activeInterval?.start_frame ?? poseStart);
  const clipEnd = Math.min(poseEnd, activeInterval?.end_frame ?? poseEnd);
  const markersById = new Map(
    (editorState?.markers || []).map((marker) => [marker.id, marker]),
  );
  const markerFrames = new Set();
  for (const binding of Object.values(EffectClass.CONTROL_BINDINGS || {})) {
    if (binding?.type === 'time_marker') {
      const marker = markersById.get(binding.id);
      if (marker) markerFrames.add(marker.frame);
    }
  }
  return Array.from(markerFrames)
    .sort((first, second) => first - second)
    .map((frame) => ({
      start: Math.max(clipStart, frame - 2),
      end: Math.min(clipEnd, frame + 1),
    }))
    .filter((pair) => pair.end - pair.start > 1);
}

const validationWindows = buildValidationWindows();
const forwardSkipPairs = buildForwardSkipPairs();
let sequentialFrameError = null;
const newFrameControlAccesses = new Set();
const passiveControlAccesses = new Set();
let sampledFrames = 0;
for (const window of validationWindows) {
  const effect = new EffectClass();
  for (let frame = window.start; frame <= window.end; frame++) {
    const firstFrame = frame === window.start;
    const result = renderFrame(effect, frame, true, {
      isNewFrame: true,
      deltaFrames: firstFrame ? 0 : 1,
      discontinuity: firstFrame && frame > 0 ? 'seek' : 'none',
    });
    sampledFrames++;
    for (const controlId of result.accesses) newFrameControlAccesses.add(controlId);
    if (result.error) {
      error = result.error;
      break;
    }
    const stateBeforeRepeat = JSON.stringify(normalize(effect));
    const repeated = renderFrame(effect, frame, false, {
      isNewFrame: false,
      deltaFrames: 0,
      discontinuity: 'none',
    });
    for (const controlId of repeated.accesses) passiveControlAccesses.add(controlId);
    if (repeated.error) {
      sequentialFrameError = `Repeated rendering failed at frame ${frame}: ${repeated.error}`;
    } else if (JSON.stringify(repeated.trace) !== JSON.stringify(result.trace)) {
      sequentialFrameError = (
        `Sequential-frame validation failed at frame ${frame}: ` +
        `repeated drawing commands changed while frameData.isNewFrame was false`
      );
    } else {
      const stateAfterRepeat = JSON.stringify(normalize(effect));
      if (stateAfterRepeat !== stateBeforeRepeat) {
        sequentialFrameError = (
          `Sequential-frame validation failed at frame ${frame}: ` +
          `Effect state changed while frameData.isNewFrame was false`
        );
      }
    }
    if (sequentialFrameError) break;
  }
  if (error || sequentialFrameError) break;

  const seekResult = renderFrame(effect, window.end, false, {
      isNewFrame: true,
      deltaFrames: 0,
      discontinuity: 'seek',
    });
    if (seekResult.error) {
      sequentialFrameError = `Seek reset failed at frame ${window.end}: ${seekResult.error}`;
      break;
    }
  }

if (!error && !sequentialFrameError) {
  for (const pair of forwardSkipPairs) {
    const effect = new EffectClass();
    const startResult = renderFrame(effect, pair.start, false, {
      isNewFrame: true,
      deltaFrames: 0,
      discontinuity: pair.start > 0 ? 'seek' : 'none',
    });
    if (startResult.error) {
      error = startResult.error;
      break;
    }
    const skipResult = renderFrame(effect, pair.end, false, {
      isNewFrame: true,
      deltaFrames: pair.end - pair.start,
      discontinuity: 'none',
    });
    if (skipResult.error) {
      error = skipResult.error;
      break;
    }
  }
}

const markerIds = new Set((editorState?.markers || []).map((marker) => marker.id));
const requiredTimeControlIds = [...requiredControlIds].filter((id) => markerIds.has(id));
const missingNewFrameControls = requiredTimeControlIds.filter(
  (id) => !newFrameControlAccesses.has(id),
);
const missingPassiveControls = requiredTimeControlIds.filter(
  (id) => !passiveControlAccesses.has(id),
);
let controlAccessError = null;
if (missingNewFrameControls.length > 0) {
  controlAccessError = (
    `Required Time Markers were not read during rendering: ${missingNewFrameControls.join(', ')}`
  );
} else if (missingPassiveControls.length > 0) {
  controlAccessError = (
    `Required Time Markers were not read during passive redraw: ${missingPassiveControls.join(', ')}`
  );
}

function makeSeededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state = (1664525 * state + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

function findMovedFrame(marker, activeEditorState, clipStart, clipEnd) {
  const occupied = new Set(
    (activeEditorState?.markers || [])
      .filter((item) => item.id !== marker.id)
      .map((item) => item.frame),
  );
  const distance = Math.max(2, Math.floor((clipEnd - clipStart + 1) / 4));
  const candidates = [
    marker.frame + distance,
    marker.frame - distance,
    marker.frame + 2,
    marker.frame - 2,
    marker.frame + 1,
    marker.frame - 1,
  ];
  return candidates.find((frame) => (
    frame >= clipStart
    && frame <= clipEnd
    && frame !== marker.frame
    && !occupied.has(frame)
  ));
}

function renderSensitivitySequence(activeEditorState, frames) {
  const effect = new EffectClass();
  const originalRandom = Math.random;
  Math.random = makeSeededRandom(0x5eed1234);
  const traces = [];
  let previousFrame = null;
  try {
    for (const frame of frames) {
      const result = renderFrame(effect, frame, false, {
        isNewFrame: true,
        deltaFrames: previousFrame === null ? 0 : frame - previousFrame,
        discontinuity: previousFrame === null && frame > 0 ? 'seek' : 'none',
      }, activeEditorState);
      if (result.error) return { traces, error: result.error };
      traces.push(result.trace);
      previousFrame = frame;
    }
    return { traces, error: null };
  } finally {
    Math.random = originalRandom;
  }
}

function checkTimeControlSensitivity() {
  if (requiredTimeControlIds.length === 0) return null;
  const poseFrames = Object.keys(raw).map(Number).filter(Number.isInteger);
  if (poseFrames.length === 0) return null;
  const poseStart = Math.min(...poseFrames);
  const poseEnd = Math.max(...poseFrames);
  const clipStart = Math.max(
    poseStart,
    editorState?.active_interval?.start_frame ?? poseStart,
  );
  const clipEnd = Math.min(
    poseEnd,
    editorState?.active_interval?.end_frame ?? poseEnd,
  );
  const markersById = new Map(
    (editorState?.markers || []).map((marker) => [marker.id, marker]),
  );

  for (const markerId of requiredTimeControlIds) {
    const marker = markersById.get(markerId);
    if (!marker) continue;
    const movedFrame = findMovedFrame(marker, editorState, clipStart, clipEnd);
    if (movedFrame === undefined) continue;
    const movedEditorState = JSON.parse(JSON.stringify(editorState));
    const movedMarker = movedEditorState.markers.find((item) => item.id === markerId);
    movedMarker.frame = movedFrame;
    const midpoint = Math.floor((marker.frame + movedFrame) / 2);
    const sampleFrames = [...new Set([
      marker.frame - 1,
      marker.frame,
      marker.frame + 1,
      movedFrame - 1,
      movedFrame,
      movedFrame + 1,
      midpoint,
    ])]
      .filter((frame) => frame >= clipStart && frame <= clipEnd)
      .sort((first, second) => first - second);
    const originalResult = renderSensitivitySequence(editorState, sampleFrames);
    const movedResult = renderSensitivitySequence(movedEditorState, sampleFrames);
    if (originalResult.error || movedResult.error) {
      return originalResult.error || movedResult.error;
    }
    if (JSON.stringify(originalResult.traces) === JSON.stringify(movedResult.traces)) {
      return `Required Time Marker did not affect drawing when moved: ${markerId}`;
    }
  }
  return null;
}

const controlSensitivityError = (
  !error && !sequentialFrameError && !controlAccessError
    ? checkTimeControlSensitivity()
    : null
);

console.log('__VERIFY_JSON__' + JSON.stringify({
  error,
  sequentialFrameError,
  controlAccessError,
  controlSensitivityError,
  frames: sampledFrames,
  count,
}));
})().catch((error) => {
  console.error(error?.stack || error?.message || String(error));
  process.exitCode = 1;
});
"""

_NODE_RENDERER = _NODE_RENDERER.replace("__JOINT_NAMES__", _JOINT_NAMES_JS)


def run_node_render(
    code_path: str,
    params_path: str,
    pose_path: str,
    frames: int,
    timeout_seconds: float,
    editor_state_path: str,
    video_width: int,
    video_height: int,
    required_control_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Run generated code inside the local Node rendering adapter."""
    descriptor, node_path = tempfile.mkstemp(suffix=".cjs", prefix="hard_validate_runtime_")
    os.close(descriptor)
    try:
        with open(node_path, "w", encoding="utf-8") as runtime_file:
            runtime_file.write(_NODE_RENDERER)
        process = subprocess.run(
            [
                "node",
                node_path,
                code_path,
                params_path,
                pose_path,
                str(frames),
                editor_state_path,
                str(Path(__file__).resolve().parents[2] / "shared" / "controlRuntime.mjs"),
                str(video_width),
                str(video_height),
                json.dumps(sorted(required_control_ids or set())),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if process.returncode != 0:
            return {"error": (process.stderr or process.stdout or "").strip()[:500]}
        lines = process.stdout.strip().splitlines()
        payload = next(
            (line for line in reversed(lines) if line.startswith("__VERIFY_JSON__")),
            None,
        )
        if payload is None:
            return {"error": "No render result was received from Node"}
        try:
            return json.loads(payload[len("__VERIFY_JSON__"):])
        except json.JSONDecodeError as error:
            return {"error": f"Failed to parse the render result: {error}"}
    except FileNotFoundError:
        return {"error": "Node.js is unavailable; install it before running validation"}
    except subprocess.TimeoutExpired:
        return {"error": f"Simulated rendering exceeded {timeout_seconds:g} seconds"}
    finally:
        try:
            os.remove(node_path)
        except OSError:
            pass
