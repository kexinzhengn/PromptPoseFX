export function getTimelineFrame(clientX, rect, totalFrames) {
  if (totalFrames <= 1 || rect.width <= 0) return 0;
  const position = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
  return Math.round(position * (totalFrames - 1));
}
