import { useEffect, useRef } from 'react';
import { dispatchCanvasMousePressed } from '../utils/p5PointerEvents.js';

export default function useP5Sketch({ containerRef, width, height, renderFrame, redrawToken, onMousePressed }) {
  const p5InstanceRef = useRef(null);
  const renderFrameRef = useRef(renderFrame);
  const onMousePressedRef = useRef(onMousePressed);

  useEffect(() => {
    void redrawToken;
    renderFrameRef.current = renderFrame;
    p5InstanceRef.current?.redraw();
  }, [renderFrame, redrawToken]);
  useEffect(() => { onMousePressedRef.current = onMousePressed; }, [onMousePressed]);

  useEffect(() => {
    if (!containerRef.current || !width || !height) return;

    let cancelled = false;
    let instance = null;

    const sketch = (p) => {
      p.setup = () => {
        p.createCanvas(width, height);
        p.noLoop();
      };

      p.draw = () => {
        p.clear();
        renderFrameRef.current?.(p);
      };

      p.mousePressed = (event) => {
        return dispatchCanvasMousePressed(
          p,
          event,
          onMousePressedRef.current,
        );
      };
    };

    import('p5')
      .then(({ default: P5 }) => {
        if (cancelled || !containerRef.current) return;
        instance = new P5(sketch, containerRef.current);
        p5InstanceRef.current = instance;
      })
      .catch((error) => {
        if (!cancelled) console.error('[useP5Sketch] failed to load p5:', error);
      });

    return () => {
      cancelled = true;
      instance?.remove();
      p5InstanceRef.current = null;
    };
  }, [containerRef, width, height]);

  return p5InstanceRef;
}
