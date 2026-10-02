import { useEffect, useRef, useCallback, useState } from 'react';
import { PoseTimeline } from '../utils/poseTimeline.js';

/**
 * usePoseData — fetch smoothed_landmark.json and cache per-frame joints.
 *
 * Only fetches when `ready` is true (e.g. pose processing finished).
 *
 * Returns:
 *   getJointsAtFrame(frame)  — stable function returning { jointName: {x, y} }
 *   getJointHistory(jointName, currentFrame, lookbackFrames) — bounded motion history
 *   isLoading                 — true while fetching
 *   error                     — error message if fetch failed
 */
export default function usePoseData(videoId, ready = true) {
  const timelineRef = useRef(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!videoId || videoId === 'local' || !ready) {
      timelineRef.current = null;
      setIsLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    fetch(`/api/video/${videoId}/smoothed_landmark.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`Pose data not available (${r.status})`);
        return r.json();
      })
      .then((raw) => {
        if (cancelled) return;
        timelineRef.current = new PoseTimeline(raw);
        setIsLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e.message);
        setIsLoading(false);
      });

    return () => { cancelled = true; };
  }, [videoId, ready]);

  const getJointsAtFrame = useCallback((frame) => {
    return timelineRef.current?.getJointsAtFrame(frame) ?? {};
  }, []);

  const getJointHistory = useCallback((jointName, currentFrame, lookbackFrames) => {
    return timelineRef.current?.getJointHistory(
      jointName,
      currentFrame,
      lookbackFrames,
    ) ?? [];
  }, []);

  return { getJointsAtFrame, getJointHistory, isLoading, error };
}
