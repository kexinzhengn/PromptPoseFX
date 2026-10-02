const VIEWPORT_MARGIN = 8;
const TOOLTIP_GAP = 8;

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum);
}

export function calculateTooltipPosition(anchor, tooltip, viewport) {
  const availableAbove = anchor.top - VIEWPORT_MARGIN;
  const availableBelow = viewport.height - anchor.bottom - VIEWPORT_MARGIN;
  const placement = availableAbove >= tooltip.height + TOOLTIP_GAP
    || availableAbove > availableBelow
    ? 'above'
    : 'below';

  const preferredTop = placement === 'above'
    ? anchor.top - tooltip.height - TOOLTIP_GAP
    : anchor.bottom + TOOLTIP_GAP;
  const maximumLeft = Math.max(VIEWPORT_MARGIN, viewport.width - tooltip.width - VIEWPORT_MARGIN);
  const maximumTop = Math.max(VIEWPORT_MARGIN, viewport.height - tooltip.height - VIEWPORT_MARGIN);

  return {
    left: clamp(anchor.left, VIEWPORT_MARGIN, maximumLeft),
    top: clamp(preferredTop, VIEWPORT_MARGIN, maximumTop),
    placement,
  };
}
