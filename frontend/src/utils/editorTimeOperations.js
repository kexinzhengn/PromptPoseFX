export function addTimeMarker(editorState, { id, frame }) {
  if (editorState.markers.some((marker) => marker.frame === frame)) {
    throw new Error(`A Time Marker already exists at frame ${frame}.`);
  }
  const markerNumber = editorState.next_alias.marker;
  return {
    ...editorState,
    markers: [
      ...editorState.markers,
      { id, alias: `t${markerNumber}`, frame },
    ],
    next_alias: {
      ...editorState.next_alias,
      marker: markerNumber + 1,
    },
  };
}

export function moveTimeMarker(editorState, markerId, frame) {
  if (editorState.markers.some((marker) => (
    marker.id !== markerId && marker.frame === frame
  ))) {
    return editorState;
  }
  return {
    ...editorState,
    markers: editorState.markers.map((marker) => (
      marker.id === markerId ? { ...marker, frame } : marker
    )),
  };
}

export function removeTimeMarker(editorState, markerId) {
  return {
    ...editorState,
    markers: editorState.markers.filter((marker) => marker.id !== markerId),
  };
}

export function getTimeMarkerDeletionError(
  editorState,
  markerId,
  boundControlIds = [],
) {
  if (boundControlIds.includes(markerId)) {
    return 'This Time Marker cannot be deleted because the current Effect uses it.';
  }
  return null;
}

export function trimEffectClip(editorState, edge, frame) {
  if (edge !== 'start' && edge !== 'end') {
    throw new Error(`Unsupported Effect Clip edge: ${edge}`);
  }
  if (edge === 'end') {
    return {
      ...editorState,
      active_interval: {
        ...editorState.active_interval,
        end_frame: Math.max(frame, editorState.active_interval.start_frame),
      },
    };
  }
  return {
    ...editorState,
    active_interval: {
      ...editorState.active_interval,
      start_frame: Math.min(frame, editorState.active_interval.end_frame),
    },
  };
}
