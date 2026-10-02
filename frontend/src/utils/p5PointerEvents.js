export function dispatchCanvasMousePressed(p, event, onMousePressed) {
  if (event?.target !== p.canvas) return undefined;
  return onMousePressed?.(p);
}
