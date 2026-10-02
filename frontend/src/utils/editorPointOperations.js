export function addJointPoint(editorState, { id, joint }) {
  const pointNumber = editorState.next_alias.point;
  return {
    ...editorState,
    points: [
      ...editorState.points,
      {
        id,
        alias: `p${pointNumber}`,
        source: {
          type: 'joint',
          joint,
          offset_x: 0,
          offset_y: 0,
        },
      },
    ],
    next_alias: {
      ...editorState.next_alias,
      point: pointNumber + 1,
    },
  };
}

export function movePointToPosition(editorState, {
  pointId,
  position,
  jointPosition,
}) {
  return {
    ...editorState,
    points: editorState.points.map((point) => {
      if (point.id !== pointId) return point;
      if (point.source.type === 'fixed') {
        return {
          ...point,
          source: { ...point.source, x: position.x, y: position.y },
        };
      }
      if (!jointPosition) {
        throw new Error('Joint Point movement requires its current joint position');
      }
      return {
        ...point,
        source: {
          ...point.source,
          offset_x: position.x - jointPosition.x,
          offset_y: position.y - jointPosition.y,
        },
      };
    }),
  };
}

export function removePoint(editorState, pointId) {
  return {
    ...editorState,
    points: editorState.points.filter((point) => point.id !== pointId),
  };
}

export function getPointDeletionError(pointId, boundControlIds = []) {
  if (!boundControlIds.includes(pointId)) return null;
  return 'This Point cannot be deleted because the current Effect uses it.';
}
