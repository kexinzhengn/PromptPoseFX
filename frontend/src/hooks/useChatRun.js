import React from 'react';
import { ApiError, createRun, subscribeRun, cancelRun } from '../api/api.js';

const IDLE_RUN = { runId: null, events: [], isRunning: false, isCancelling: false, busy: false };

/**
 * Keep an independent run state for each effect thread.
 * Different threads may run concurrently, while the backend enforces one run per thread.
 */
export default function useChatRun() {
  const [runs, setRuns] = React.useState({});       // threadId -> run state
  const esRef = React.useRef({});                   // threadId -> EventSource
  const timerRef = React.useRef({});                // threadId -> timeout timer
  const runIdRef = React.useRef({});                // threadId -> run_id

  const clearRun = React.useCallback((threadId) => {
    if (timerRef.current[threadId]) {
      clearTimeout(timerRef.current[threadId]);
      delete timerRef.current[threadId];
    }
    esRef.current[threadId]?.close();
    delete esRef.current[threadId];
    delete runIdRef.current[threadId];
    setRuns((prev) => {
      const next = { ...prev };
      const cur = next[threadId];
      if (cur) {
        next[threadId] = { ...cur, runId: null, isRunning: false, isCancelling: false };
      }
      return next;
    });
  }, []);

  // Refresh the sliding timeout on every event and fail after five quiet minutes.
  const armTimeout = React.useCallback((threadId, onError) => {
    if (timerRef.current[threadId]) {
      clearTimeout(timerRef.current[threadId]);
    }
    timerRef.current[threadId] = setTimeout(() => {
      if (esRef.current[threadId]) {
        esRef.current[threadId].close();
        delete esRef.current[threadId];
        delete timerRef.current[threadId];
        delete runIdRef.current[threadId];
        setRuns((prev) => {
          const next = { ...prev };
          const cur = next[threadId];
          if (cur) {
            next[threadId] = { ...cur, runId: null, isRunning: false, isCancelling: false };
          }
          return next;
        });
        onError?.('The task made no progress for five minutes, so waiting was stopped.');
      }
    }, 5 * 60 * 1000);
  }, []);

  const start = React.useCallback((threadId, {
    video_id,
    user_input,
    pinned_joints = {},
    selected_option_id = null,
    effect_mentions = [],
    editor_revision = null,
    editor_selection = null,
    onStage,
    onTerminal,
    onError,
  }) => {
    setRuns((prev) => ({
      ...prev,
      [threadId]: { ...IDLE_RUN, isRunning: true },
    }));

    (async () => {
      try {
        const { run_id, thread_id: tid } = await createRun({
          video_id,
          user_input,
          thread_id: threadId,
          pinned_joints,
          selected_option_id,
          effect_mentions,
          editor_revision,
          editor_selection,
        });
        runIdRef.current[threadId] = run_id;
        setRuns((prev) => ({ ...prev, [threadId]: { ...prev[threadId], runId: run_id } }));
        onStage?.({ content: 'Task submitted.', thread_id: tid });

        const es = subscribeRun(run_id, {
          onEvent: (ev) => {
            armTimeout(threadId, onError);
            setRuns((prev) => {
              const cur = prev[threadId] || IDLE_RUN;
              return { ...prev, [threadId]: { ...cur, events: [...cur.events, ev] } };
            });
            if (ev.type === 'stage') {
              onStage?.({ stage: ev.stage, content: ev.content });
            }
            if (ev.type === 'terminal') {
              clearRun(threadId);
              onTerminal?.(ev);
            }
          },
          onError: (msg) => {
            clearRun(threadId);
            onError?.(msg);
          },
        });
        esRef.current[threadId] = es;
        armTimeout(threadId, onError);
      } catch (err) {
        clearRun(threadId);
        if (err instanceof ApiError && err.status === 409) {
          setRuns((prev) => ({
            ...prev,
            [threadId]: { ...(prev[threadId] || IDLE_RUN), busy: true },
          }));
        }
        onError?.(err.message || 'Failed to submit the task.');
      }
    })();
  }, [armTimeout, clearRun]);

  const cancel = React.useCallback((threadId) => {
    const runId = runIdRef.current[threadId];
    if (!runId) return;
    setRuns((prev) => ({
      ...prev,
      [threadId]: { ...(prev[threadId] || IDLE_RUN), isCancelling: true },
    }));
    cancelRun(runId).catch(() => {
      setRuns((prev) => ({
        ...prev,
        [threadId]: { ...(prev[threadId] || IDLE_RUN), isCancelling: false },
      }));
    });
  }, []);

  const reset = React.useCallback((threadId) => {
    clearRun(threadId);
    setRuns((prev) => ({ ...prev, [threadId]: { ...IDLE_RUN } }));
  }, [clearRun]);

  const resetAll = React.useCallback(() => {
    Object.keys(esRef.current).forEach((tid) => esRef.current[tid]?.close());
    Object.keys(timerRef.current).forEach((tid) => clearTimeout(timerRef.current[tid]));
    esRef.current = {};
    timerRef.current = {};
    runIdRef.current = {};
    setRuns({});
  }, []);

  return { start, cancel, reset, resetAll, runs };
}
