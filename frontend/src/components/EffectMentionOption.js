import React from 'react';

export default function EffectMentionOption({ effect, onSelect }) {
  return React.createElement(
    'button',
    {
      type: 'button',
      className: 'block w-full px-3 py-2 text-left text-sm hover:bg-white/5',
      style: { color: 'var(--editor-text)' },
      onClick: () => onSelect(effect),
    },
    effect.name,
  );
}
