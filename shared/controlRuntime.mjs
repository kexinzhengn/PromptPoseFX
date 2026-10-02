function requireFiniteDimension(value, name) {
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`${name} must be a positive finite number`);
  }
  return value;
}

/** Build the editor-control view exposed to one Effect render call. */
export function createFrameControls({
  bindings,
  editorState,
  width,
  height,
  currentFrame,
  getJointsAtFrame,
}) {
  const frameWidth = requireFiniteDimension(width, 'width');
  const frameHeight = requireFiniteDimension(height, 'height');
  const pointsById = new Map(
    (editorState?.points || []).map((point) => [point.id, point]),
  );
  const pathsById = new Map(
    (editorState?.paths || []).map((path) => [path.id, path]),
  );
  const markersById = new Map(
    (editorState?.markers || []).map((marker) => [marker.id, marker]),
  );
  for (const [bindingName, binding] of Object.entries(bindings || {})) {
    if (binding?.type === 'point' && !pointsById.has(binding.id)) {
      throw new Error(`Point binding references a missing control: ${bindingName}`);
    }
    if (binding?.type === 'path' && !pathsById.has(binding.id)) {
      throw new Error(`Path binding references a missing control: ${bindingName}`);
    }
    if (binding?.type === 'time_marker' && !markersById.has(binding.id)) {
      throw new Error(`Time Marker binding references a missing control: ${bindingName}`);
    }
    if (!['point', 'path', 'time_marker'].includes(binding?.type)) {
      throw new Error(`Unsupported control binding type: ${bindingName}`);
    }
  }

  function getPath(bindingName) {
    const binding = bindings?.[bindingName];
    if (!binding || binding.type !== 'path') {
      throw new Error(`Unknown Path binding: ${bindingName}`);
    }
    const path = pathsById.get(binding.id);
    if (!path) {
      throw new Error(`Path binding references a missing control: ${bindingName}`);
    }
    const points = path.points.map((point) => ({
      x: point.x * frameWidth,
      y: point.y * frameHeight,
    }));
    const segments = [];
    let length = 0;
    for (let index = 1; index < points.length; index += 1) {
      const start = points[index - 1];
      const end = points[index];
      const dx = end.x - start.x;
      const dy = end.y - start.y;
      const segmentLength = Math.hypot(dx, dy);
      if (segmentLength === 0) continue;
      segments.push({ start, dx, dy, length: segmentLength, offset: length });
      length += segmentLength;
    }

    function sample(progress) {
      if (!Number.isFinite(progress)) {
        throw new Error('Path sample progress must be finite');
      }
      if (segments.length === 0) {
        return {
          x: points[0]?.x ?? null,
          y: points[0]?.y ?? null,
          tangentX: 0,
          tangentY: 0,
          valid: false,
        };
      }
      const target = Math.max(0, Math.min(1, progress)) * length;
      const segment = segments.find(
        (candidate) => target <= candidate.offset + candidate.length,
      ) || segments[segments.length - 1];
      const localProgress = Math.max(
        0,
        Math.min(1, (target - segment.offset) / segment.length),
      );
      return {
        x: segment.start.x + segment.dx * localProgress,
        y: segment.start.y + segment.dy * localProgress,
        tangentX: segment.dx / segment.length,
        tangentY: segment.dy / segment.length,
        valid: true,
      };
    }

    return { points, length, sample };
  }

  function getPoint(bindingName, frame = currentFrame) {
    if (!Number.isInteger(frame) || frame < 0) {
      throw new Error(`Point frame must be a non-negative integer: ${frame}`);
    }
    const binding = bindings?.[bindingName];
    if (!binding || binding.type !== 'point') {
      throw new Error(`Unknown Point binding: ${bindingName}`);
    }
    const point = pointsById.get(binding.id);
    if (!point) {
      throw new Error(`Point binding references a missing control: ${bindingName}`);
    }
    if (point.source?.type === 'fixed') {
      return {
        x: point.source.x * frameWidth,
        y: point.source.y * frameHeight,
        vx: 0,
        vy: 0,
        speed: 0,
        valid: true,
        connected: frame > 0,
      };
    }
    if (point.source?.type === 'joint') {
      if (typeof getJointsAtFrame !== 'function') {
        throw new Error('Joint Point resolution requires getJointsAtFrame');
      }
      const position = getJointsAtFrame(frame)?.[point.source.joint];
      const previous = getJointsAtFrame(frame - 1)?.[point.source.joint];
      const valid = !!position && !(position.x === 0 && position.y === 0);
      const previousValid = !!previous && !(previous.x === 0 && previous.y === 0);
      const connected = valid && previousValid;
      const vx = connected ? position.x - previous.x : 0;
      const vy = connected ? position.y - previous.y : 0;
      return {
        x: valid ? position.x + point.source.offset_x * frameWidth : null,
        y: valid ? position.y + point.source.offset_y * frameHeight : null,
        vx,
        vy,
        speed: Math.hypot(vx, vy),
        valid,
        connected,
      };
    }
    throw new Error(`Unsupported Point source type: ${point.source?.type || 'missing'}`);
  }

  function getTimeMarker(bindingName) {
    const binding = bindings?.[bindingName];
    if (!binding || binding.type !== 'time_marker') {
      throw new Error(`Unknown Time Marker binding: ${bindingName}`);
    }
    const marker = markersById.get(binding.id);
    if (!marker) {
      throw new Error(`Time Marker binding references a missing control: ${bindingName}`);
    }
    return { frame: marker.frame };
  }

  return { getPoint, getPath, getTimeMarker };
}
