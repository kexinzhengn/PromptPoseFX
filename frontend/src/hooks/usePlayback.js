import React from 'react';

import { createPlaybackClock } from '../utils/playbackClock.js';


/** Own the editor's single frame clock and expose controlled playback actions. */
export default function usePlayback({ totalFrames, fps = 30, resetKey = '', disabled = false }) {
  const [frameEvent, setFrameEvent] = React.useState({
    currentFrame: 0,
    deltaFrames: 0,
    discontinuity: 'none',
    sequence: 0,
    continuityId: 0,
    continuityReason: 'none',
  });
  const [isPlaying, setIsPlaying] = React.useState(false);
  const clockRef = React.useRef(null);
  const disabledRef = React.useRef(disabled);

  React.useEffect(() => {
    disabledRef.current = disabled;
  }, [disabled]);

  React.useEffect(() => {
    const clock = createPlaybackClock({
      fps,
      totalFrames: 1,
      onFrame: setFrameEvent,
    });
    clockRef.current = clock;

    return () => {
      clock.dispose();
      clockRef.current = null;
    };
  }, [fps]);

  React.useEffect(() => {
    clockRef.current?.setTotalFrames(totalFrames);
  }, [totalFrames]);

  const pause = React.useCallback(() => {
    clockRef.current?.pause();
    setIsPlaying(false);
  }, []);

  const play = React.useCallback(() => {
    if (disabledRef.current || !clockRef.current) return;
    clockRef.current.play();
    setIsPlaying(true);
  }, []);

  const toggle = React.useCallback(() => {
    if (clockRef.current?.getSnapshot().isPlaying) pause();
    else play();
  }, [pause, play]);

  const seek = React.useCallback((frame) => {
    clockRef.current?.seek(frame);
  }, []);

  React.useEffect(() => {
    pause();
    clockRef.current?.seek(0);
  }, [resetKey, pause]);

  React.useEffect(() => {
    if (disabled) pause();
  }, [disabled, pause]);

  return {
    currentFrame: frameEvent.currentFrame,
    frameEvent,
    isPlaying,
    play,
    pause,
    toggle,
    seek,
  };
}
