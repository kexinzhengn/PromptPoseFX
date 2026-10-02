const MIN_SAMPLE_DISTANCE_PX = 4;
const MAX_PATH_POINTS = 512;

function clampNormalized(value) {
  if (!Number.isFinite(value)) {
    throw new Error('Path coordinates must be finite');
  }
  return Math.max(0, Math.min(1, value));
}

function normalizePathPoints(points) {
  if (points.length < 2) {
    throw new Error('Draw a longer Path before releasing the pointer.');
  }
  return points.map((point) => ({
    x: clampNormalized(point.x),
    y: clampNormalized(point.y),
  }));
}

export function appendDraftPathPoint(
  points,
  position,
  width,
  height,
  minDistancePx = MIN_SAMPLE_DISTANCE_PX,
) {
  if (!Number.isFinite(width) || width <= 0 || !Number.isFinite(height) || height <= 0) {
    throw new Error('Path drawing requires positive canvas dimensions');
  }
  if (points.length >= MAX_PATH_POINTS) return points;
  const nextPoint = {
    x: clampNormalized(position.x),
    y: clampNormalized(position.y),
  };
  const previous = points[points.length - 1];
  if (previous) {
    const distance = Math.hypot(
      (nextPoint.x - previous.x) * width,
      (nextPoint.y - previous.y) * height,
    );
    if (distance < minDistancePx) return points;
  }
  return [...points, nextPoint];
}

export function addDrawnPath(editorState, { id, points }) {
  const pathNumber = editorState.next_alias.path ?? 1;
  return {
    ...editorState,
    paths: [
      ...(editorState.paths || []),
      {
        id,
        alias: `path${pathNumber}`,
        points: normalizePathPoints(points),
      },
    ],
    next_alias: {
      ...editorState.next_alias,
      path: pathNumber + 1,
    },
  };
}

export function removePath(editorState, pathId) {
  return {
    ...editorState,
    paths: (editorState.paths || []).filter((path) => path.id !== pathId),
  };
}

export function getPathDeletionError(pathId, boundControlIds = []) {
  if (!boundControlIds.includes(pathId)) return null;
  return 'This Path cannot be deleted because the current Effect uses it.';
}

export function replacePathPoints(editorState, pathId, points) {
  const normalizedPoints = normalizePathPoints(points);
  let found = false;
  const paths = (editorState.paths || []).map((path) => {
    if (path.id !== pathId) return path;
    found = true;
    return { ...path, points: normalizedPoints };
  });
  if (!found) throw new Error('The selected Path no longer exists.');
  return { ...editorState, paths };
}
