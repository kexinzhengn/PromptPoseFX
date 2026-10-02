import React from 'react';

/** Display clarification options returned by the agent. */
export default function ChatOptions({ header, options, onSelect, disabled = false }) {
  if (!Array.isArray(options) || options.length === 0) {
    return null;
  }

  return React.createElement(
    'div',
    {
      'aria-label': header || 'Available options',
      className: 'mt-4 space-y-2',
      'data-name': 'chat-options',
    },
    header
      ? React.createElement(
          'div',
          { className: 'text-xs font-medium', style: { color: 'var(--editor-muted)' } },
          header,
        )
      : null,
    ...options.map((option) => React.createElement(
      'button',
      {
        className: 'editor-chat-option block w-full px-3 py-2 text-left transition-opacity disabled:cursor-not-allowed disabled:opacity-50',
        disabled: disabled || !onSelect,
        key: option.id || `${option.label}-${option.description}`,
        onClick: () => onSelect?.(option),
        type: 'button',
      },
      React.createElement(
        'span',
        { className: 'block text-sm font-medium' },
        option.label,
      ),
      React.createElement(
        'span',
        { className: 'mt-1 block text-xs', style: { color: 'var(--editor-muted)' } },
        option.description,
      ),
    )),
  );
}
