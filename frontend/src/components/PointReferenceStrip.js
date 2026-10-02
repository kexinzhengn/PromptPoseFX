import React from 'react';

export default function PointReferenceStrip({
  points = [],
  paths = [],
  selectedPointId = null,
  selectedPathId = null,
  onSelectPoint,
  onSelectPath,
}) {
  if (points.length === 0 && paths.length === 0) return null;
  const references = [
    ...points.map((point) => ({ ...point, referenceType: 'point' })),
    ...paths.map((path) => ({ ...path, referenceType: 'path' })),
  ];
  return React.createElement(
    'div',
    {
      'data-name': 'editor-reference-strip',
      role: 'toolbar',
      'aria-label': 'Editor references',
      className: 'flex min-w-0 items-center gap-2 overflow-x-auto',
    },
    references.map((reference) => {
      const isPath = reference.referenceType === 'path';
      const selected = isPath
        ? reference.id === selectedPathId
        : reference.id === selectedPointId;
      return React.createElement(
        'button',
        {
          key: `${reference.referenceType}-${reference.id}`,
          type: 'button',
          'data-reference-type': reference.referenceType,
          'aria-label': `Select ${reference.alias}`,
          'aria-pressed': selected,
          title: `${reference.alias} · ${isPath ? 'Path' : 'Point'}`,
          className: `editor-reference-token ${isPath ? 'editor-reference-token-path' : ''} flex-shrink-0 px-2.5 py-1 text-xs font-mono`,
          style: {
            color: selected ? 'var(--editor-text)' : 'var(--editor-muted)',
            backgroundColor: 'transparent',
            border: selected
              ? '1px solid var(--editor-selection)'
              : '1px solid var(--editor-line)',
          },
          onClick: () => {
            if (isPath) onSelectPath?.(reference.id);
            else onSelectPoint?.(reference.id);
          },
        },
        reference.alias,
      );
    }),
  );
}
