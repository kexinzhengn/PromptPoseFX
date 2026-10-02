export function formatSelectedOptionMessage(option) {
  const label = typeof option?.label === 'string' ? option.label.trim() : '';
  const description = typeof option?.description === 'string'
    ? option.description.trim()
    : '';
  if (!description || description === label) return label;
  return [label, description].filter(Boolean).join('\n');
}
