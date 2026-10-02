export function selectPointReference(pointId) {
  return { selectedPointId: pointId, selectedPathId: pointId ? null : undefined };
}

export function selectPathReference(pathId) {
  return { selectedPointId: pathId ? null : undefined, selectedPathId: pathId };
}
