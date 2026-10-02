import React from 'react';

import Header from './components/Header.jsx';
import Toolbar from './components/Toolbar.jsx';
import VideoPreview from './components/VideoPreview.jsx';
import RightPanel from './components/RightPanel.jsx';
import ChatInput from './components/ChatInput.jsx';
import Timeline from './components/Timeline.jsx';
import { formatSelectedOptionMessage } from './utils/chatOptionSelection.js';
import useEffectRegistry from './hooks/useEffectRegistry.js';
import useChatRun from './hooks/useChatRun.js';
import usePlayback from './hooks/usePlayback.js';
import { createAssistantMessage, filterConversationForDisplay, stripOptionsMarkup, stripContextPrefix, withMessageId, mergeConversation } from './utils/chatMessage.js';
import { createEffectPatchScheduler } from './utils/effectPatchScheduler.js';
import { createEditorStateSaveQueue } from './utils/editorStateSaveQueue.js';
import { prepareEditorChatContext } from './utils/editorChatContext.js';
import { selectPointReference, selectPathReference } from './utils/referenceSelection.js';
import { createWorkspaceId, resolveWorkspaceId } from './utils/workspaceIdentity.js';
import { addJointPoint, getPointDeletionError, movePointToPosition, removePoint } from './utils/editorPointOperations.js';
import { addDrawnPath, getPathDeletionError, removePath, replacePathPoints } from './utils/editorPathOperations.js';
import { addTimeMarker, getTimeMarkerDeletionError, moveTimeMarker, removeTimeMarker, trimEffectClip } from './utils/editorTimeOperations.js';
import { deleteAfterWorkspaceCreation, planEffectRemoval } from './utils/effectDeletion.js';

import {
  checkHealth,
  createEffectWorkspace, fetchEffects, fetchEffectDetail, fetchThreadConversation,
  patchEffect, replaceEditorState, deleteEffect,
  uploadVideo, getProcessStatus,
} from './api/api.js';

export default function App() {
  // --- Video ---
  const [videoInfo, setVideoInfo] = React.useState(null);
  const [isVideoLoading, setIsVideoLoading] = React.useState(false);
  const [videoError, setVideoError] = React.useState(null);

  // --- Processing ---
  const [isProcessing, setIsProcessing] = React.useState(false);
  const [processingStatus, setProcessingStatus] = React.useState(null);

  // --- Effects ---
  const [effects, setEffects] = React.useState([]);
  const [effectVisibility, setEffectVisibility] = React.useState({});
  const effectVisibilityRef = React.useRef({});
  const [selectedEffectId, setSelectedEffectId] = React.useState(null);
  const [, setIsEffectsLoading] = React.useState(false);
  const [, setEffectsError] = React.useState(null);

  // Effect code storage (for p5 runtime rendering)
  const [effectCodes, setEffectCodes] = React.useState({});
  const [effectParams, setEffectParams] = React.useState({});
  const [parameterRanges, setParameterRanges] = React.useState({});
  const [editorWorkspaces, setEditorWorkspaces] = React.useState({});
  const editorWorkspacesRef = React.useRef({});
  const [pointToolActive, setPointToolActive] = React.useState(false);
  const [pathToolActive, setPathToolActive] = React.useState(false);
  const [selectedPathId, setSelectedPathId] = React.useState(null);
  const [redrawPathId, setRedrawPathId] = React.useState(null);
  const [selectedPointId, setSelectedPointId] = React.useState(null);
  const [editorError, setEditorError] = React.useState('');

  const handleSelectPoint = React.useCallback((pointId) => {
    const selection = selectPointReference(pointId);
    setSelectedPointId(selection.selectedPointId);
    if (selection.selectedPathId !== undefined) setSelectedPathId(selection.selectedPathId);
  }, []);

  const handleSelectPath = React.useCallback((pathId) => {
    const selection = selectPathReference(pathId);
    setSelectedPathId(selection.selectedPathId);
    if (selection.selectedPointId !== undefined) setSelectedPointId(selection.selectedPointId);
  }, []);

  const updateEditorWorkspaces = React.useCallback((updater) => {
    const next = updater(editorWorkspacesRef.current);
    editorWorkspacesRef.current = next;
    setEditorWorkspaces(next);
  }, []);

  const editorStateSaveQueue = React.useMemo(() => createEditorStateSaveQueue({
    save: replaceEditorState,
    onSaved: (result) => {
      updateEditorWorkspaces((current) => ({
        ...current,
        [result.effect_id]: {
          ...current[result.effect_id],
          editorRevision: result.editor_revision,
        },
      }));
      setEditorError('');
    },
    onError: (error) => {
      setEditorError(
        error?.status === 409
          ? 'This editor change could not be saved because the Effect changed elsewhere. Reload before retrying.'
          : 'This editor change could not be saved. Your latest change remains in the editor.',
      );
    },
  }), [updateEditorWorkspaces]);

  React.useEffect(() => (
    () => editorStateSaveQueue.cancelAll()
  ), [editorStateSaveQueue]);

  // Effect registry — manages instances and params via Ref + State dual-write
  const {
    effectsRef,
    paramsMapRef,
    paramsState,
    visualVersion,
    updateParam,
    replaceParams,
  } = useEffectRegistry(effectCodes, effectParams);

  // --- Chat ---
  const [messages, setMessages] = React.useState([]);
  const [, setChatError] = React.useState(null);
  const { start: startChatRun, cancel: cancelChatRun, reset: resetChatRun, resetAll: resetAllRuns, runs } = useChatRun();

  // Conversation thread stored by the backend; it matches the effect ID.
  const [threadId, setThreadId] = React.useState('');
  // Per-thread cache preserves in-progress and failed conversations across selection changes.
  const messagesCacheRef = React.useRef({});
  // Tracks which threads are loading history so locally sent messages can be marked.
  const historyLoadingRef = React.useRef({});
  // Stores role-and-content keys created during history loading for merge deduplication.
  const pendingDuringLoadRef = React.useRef({});
  // Holds the first user message until the backend assigns a thread ID.
  const pendingUserMsgRef = React.useRef(null);
  // Refs let async callbacks check whether a result belongs to the visible conversation.
  const threadIdRef = React.useRef('');
  const selectedEffectIdRef = React.useRef(null);

  React.useEffect(() => {
    threadIdRef.current = threadId;
  }, [threadId]);

  React.useEffect(() => {
    selectedEffectIdRef.current = selectedEffectId;
  }, [selectedEffectId]);

  React.useEffect(() => {
    effectVisibilityRef.current = effectVisibility;
  }, [effectVisibility]);

  const applyEffectUpdate = React.useCallback((update, localPatch = {}) => {
    if (!update?.effect_id) return;
    const localParams = localPatch.parameter_updates || {};
    const params = update.params
      ? {
          ...update.params,
          ...Object.fromEntries(
            Object.entries(localParams).filter(([key]) => key in update.params)
          ),
        }
      : null;
    const name = localPatch.name ?? update.name;
    const localRanges = localPatch.parameter_range_updates || {};
    const parameterRangesUpdate = update.parameter_ranges
      ? {
          ...update.parameter_ranges,
          ...Object.fromEntries(
            Object.entries(localRanges).filter(([key]) => key in (update.params || {}))
          ),
        }
      : null;

    if (name !== undefined) {
      setEffects((items) => items.map((effect) => (
        effect.id === update.effect_id ? { ...effect, name } : effect
      )));
    }
    if (params) {
      setEffectParams((current) => ({ ...current, [update.effect_id]: params }));
      replaceParams(update.effect_id, params);
    }
    if (parameterRangesUpdate) {
      setParameterRanges((current) => ({
        ...current,
        [update.effect_id]: parameterRangesUpdate,
      }));
    }
  }, [replaceParams]);

  const effectPatchScheduler = React.useMemo(() => createEffectPatchScheduler({
    save: patchEffect,
    onSaved: (result) => applyEffectUpdate(result.effect_update),
    onError: (error) => setChatError(error?.message || 'Could not save Effect changes.'),
  }), [applyEffectUpdate]);

  React.useEffect(() => (
    () => effectPatchScheduler.cancelAll()
  ), [effectPatchScheduler]);

  // --- Timeline ---
  const timelineTotal = videoInfo?.totalFrames ?? 230;
  const {
    currentFrame,
    frameEvent,
    isPlaying,
    pause: pausePlayback,
    toggle: togglePlayback,
    seek: seekFrame,
  } = usePlayback({
    totalFrames: timelineTotal,
    fps: 30,
    resetKey: videoInfo?.id ?? '',
    disabled: !videoInfo || isProcessing,
  });
  const [inputFocusKey, setInputFocusKey] = React.useState(0);
  // Pending layers appear immediately and use independent IDs for parallel generation.
  const [pendingEffects, setPendingEffects] = React.useState([]);
  const workspaceCreationPromisesRef = React.useRef({});

  // --- Skeleton visibility ---
  const [skeletonVisible, setSkeletonVisible] = React.useState(true);

  // --- Pinned joints ---
  const [pinnedJoints, setPinnedJoints] = React.useState({});

  // Keep the selected effect and conversation thread in sync before sending messages.
  const handleSelectEffect = React.useCallback((effectId) => {
    setSelectedEffectId(effectId);
    setThreadId(effectId);
    setPointToolActive(false);
    setPathToolActive(false);
    setRedrawPathId(null);
    setSelectedPointId(null);
    setSelectedPathId(null);
  }, []);

  const processingRef = React.useRef(null);

  // Load effects list + all details in parallel
  const loadEffectsAndDetails = React.useCallback(async () => {
    const list = await fetchEffects();
    const savedEffects = list.filter((effect) => effect.status !== 'pending');
    const savedWorkspaces = list.filter((effect) => effect.status === 'pending');
    setEffects(savedEffects);
    setPendingEffects(savedWorkspaces.map((effect) => ({
      id: effect.id,
      name: effect.name || 'Pending',
    })));
    setEffectVisibility((prev) => Object.fromEntries(
      list.map((effect) => [effect.id, prev[effect.id] !== false])
    ));
    const details = await Promise.all(
      list.map((e) => fetchEffectDetail(e.id).catch(() => null))
    );
    const codes = {};
    const params = {};
    const ranges = {};
    const workspaces = {};
    for (const d of details) {
      if (d) {
        if (d.code) codes[d.effect_id] = d.code;
        params[d.effect_id] = d.params;
        ranges[d.effect_id] = d.parameter_ranges || {};
        if (d.editor_state) {
          workspaces[d.effect_id] = {
            editorRevision: d.editor_revision,
            editorState: d.editor_state,
            boundControlIds: d.bound_control_ids || [],
          };
        }
      }
    }
    setEffectCodes((prev) => ({ ...prev, ...codes }));
    setEffectParams((prev) => ({ ...prev, ...params }));
    setParameterRanges((prev) => ({ ...prev, ...ranges }));
    updateEditorWorkspaces(() => workspaces);
    return list;
  }, [updateEditorWorkspaces]);

  // Health check on mount
  React.useEffect(() => {
    checkHealth().catch(() => {
      console.warn('Backend not available — API calls will fail');
    });
  }, []);

  // Poll processing status
  const pollProcessing = React.useCallback(async (videoId) => {
    const poll = async () => {
      try {
        const status = await getProcessStatus(videoId);
        setProcessingStatus(status);
        if (status.status === 'complete') {
          setIsProcessing(false);
          const list = await loadEffectsAndDetails();
          if (list.length > 0) {
            handleSelectEffect(list[0].id);
          }
          return;
        }
        if (status.status === 'error') {
          setIsProcessing(false);
          setVideoError(status.stage || 'Processing failed');
          return;
        }
        // Still processing — poll again
        processingRef.current = setTimeout(poll, 1500);
      } catch {
        setIsProcessing(false);
      }
    };
    poll();
  }, [loadEffectsAndDetails, handleSelectEffect]);

  // Cleanup polling on unmount
  React.useEffect(() => {
    return () => { if (processingRef.current) clearTimeout(processingRef.current); };
  }, []);

  // Load effects when video is ready (not processing)
  React.useEffect(() => {
    if (!videoInfo || isProcessing) return;
    setIsEffectsLoading(true);
    setEffectsError(null);
    loadEffectsAndDetails()
      .then((list) => {
        if (list.length > 0 && !selectedEffectId) {
          handleSelectEffect(list[0].id);
        }
      })
      .catch((err) => setEffectsError(err.message))
      .finally(() => setIsEffectsLoading(false));
  }, [videoInfo, isProcessing, selectedEffectId, loadEffectsAndDetails, handleSelectEffect]);

  // ---- Handlers ----

  const conversationLoadedRef = React.useRef(null); // track which effect's conversation is displayed

  // Load conversation when effect is selected
  React.useEffect(() => {
    if (!selectedEffectId) {
      setMessages([]);
      return;
    }

    // Already showing this effect's conversation
    if (conversationLoadedRef.current === selectedEffectId) return;

    // Prefer cached messages so switching effects does not erase active or failed runs.
    const cached = messagesCacheRef.current[selectedEffectId];
    if (cached) {
      setMessages(cached);
      setThreadId(selectedEffectId);
      conversationLoadedRef.current = selectedEffectId;
      return;
    }

    // Mark local messages sent during async history loading for merge deduplication.
    historyLoadingRef.current[selectedEffectId] = true;
    if (!pendingDuringLoadRef.current[selectedEffectId]) {
      pendingDuringLoadRef.current[selectedEffectId] = new Set();
    }

    const applyConversation = (conv) => {
      historyLoadingRef.current[selectedEffectId] = false;
      const remote = filterConversationForDisplay(conv).map((msg) => ({
        role: msg.role,
        content: stripOptionsMarkup(stripContextPrefix(msg.content)),
        ...(msg.isError ? { isError: true } : {}),
      }));
      // Preserve local messages first and append only missing history entries.
      const local = messagesCacheRef.current[selectedEffectId] || [];
      const pendingKeys = pendingDuringLoadRef.current[selectedEffectId] || new Set();
      const merged = mergeConversation(local, remote, pendingKeys);
      messagesCacheRef.current[selectedEffectId] = merged;
      setMessages(merged);
      setThreadId(selectedEffectId);
      conversationLoadedRef.current = selectedEffectId;
    };

    fetchEffectDetail(selectedEffectId)
      .then((detail) => {
        if (detail) {
          applyConversation(detail.conversation || []);
          return;
        }
        // Fall back to thread history when an effect file does not exist yet.
        return fetchThreadConversation(selectedEffectId)
          .then((data) => applyConversation(data.conversation || []))
          .catch(() => {});
      })
      .catch(() => (
        // Show an empty conversation while a new pending thread is not yet persisted.
        fetchThreadConversation(selectedEffectId)
          .then((data) => applyConversation(data.conversation || []))
          .catch(() => applyConversation([]))
      ));
  }, [selectedEffectId]);

  const handleImport = React.useCallback(async (file) => {
    setIsVideoLoading(true);
    setVideoError(null);
    try {
      const data = await uploadVideo(file);
      setVideoInfo(data);
      if (data.status === 'processing') {
        setIsProcessing(true);
        setProcessingStatus({ stage: 'Starting…', percent: 0, status: 'processing' });
        pollProcessing(data.id);
      }
    } catch {
      // Fallback: local blob preview
      const url = URL.createObjectURL(file);
      setVideoInfo({ id: 'local', totalFrames: 230, fps: 30, width: 640, height: 360, url });
    } finally {
      setIsVideoLoading(false);
    }
  }, [pollProcessing]);

  const handleSendMessage = React.useCallback(async (
    text,
    selectedOptionId = null,
    effectMentions = [],
  ) => {
    if (!videoInfo) return false;
    const hadWorkspace = Boolean(threadId || selectedEffectIdRef.current);
    const tid = resolveWorkspaceId(threadId, selectedEffectIdRef.current);
    let editorContext;
    try {
      editorContext = await prepareEditorChatContext({
        effectId: tid,
        videoId: videoInfo.id,
        currentFrame,
        selectedPointId,
        selectedPathId,
        getWorkspace: () => editorWorkspacesRef.current[tid],
        saveQueue: editorStateSaveQueue,
      });
    } catch (error) {
      const message = error?.message || 'Editor controls could not be saved before sending.';
      setChatError(message);
      setEditorError(message);
      return false;
    }
    if (!hadWorkspace) {
      const pending = { id: tid, name: 'Pending' };
      setPendingEffects((prev) => [...prev, pending]);
      setSelectedEffectId(tid);
      selectedEffectIdRef.current = tid;
      setThreadId(tid);
      threadIdRef.current = tid;
      conversationLoadedRef.current = tid;
    } else if (tid !== threadId) {
      setThreadId(tid);
      threadIdRef.current = tid;
    }
    // Reset a stale running state before starting another request in the same thread.
    if (runs[tid]?.isRunning) resetChatRun(tid);
    setChatError(null);

    const userMsg = withMessageId({
      role: 'user',
      content: text,
      selectedOptionId,
    });
    // Mark messages sent during history loading so their server copies can be skipped.
    if (historyLoadingRef.current[tid]) {
      const set = pendingDuringLoadRef.current[tid] || (pendingDuringLoadRef.current[tid] = new Set());
      set.add(`${userMsg.role}\u0000${userMsg.content}`);
    }
    setMessages((prev) => [...prev, userMsg]);
    if (tid) {
      messagesCacheRef.current[tid] = [...(messagesCacheRef.current[tid] || []), userMsg];
    } else {
      pendingUserMsgRef.current = userMsg;
    }

    const applyResult = (result) => {
      const rid = result.thread_id || tid;
      const assistantMsg = withMessageId(createAssistantMessage(result));
      const viewingThisThread = selectedEffectIdRef.current === tid || selectedEffectIdRef.current === rid;
      // Update visible messages only when the user is viewing this thread.
      if (viewingThisThread) {
        setMessages((prev) => [...prev, assistantMsg]);
      }
      messagesCacheRef.current[rid] = [...(messagesCacheRef.current[rid] || []), assistantMsg];
      // Move the local cache when the backend returns a different persisted thread ID.
      if (rid !== tid && messagesCacheRef.current[tid]?.length) {
        messagesCacheRef.current[rid] = [...(messagesCacheRef.current[tid] || []), ...(messagesCacheRef.current[rid] || [])];
        delete messagesCacheRef.current[tid];
      }
      if (result.new_effect) {
        const ne = result.new_effect;
        const localPatch = effectPatchScheduler.getLocalPatch(ne.effect_id);
        const mergedParams = {
          ...ne.params,
          ...Object.fromEntries(
            Object.entries(localPatch.parameter_updates || {}).filter(([key]) => key in ne.params)
          ),
        };
        const mergedName = localPatch.name ?? ne.effect_name;
        const mergedRanges = {
          ...(ne.parameter_ranges || {}),
          ...Object.fromEntries(
            Object.entries(localPatch.parameter_range_updates || {}).filter(
              ([key]) => key in mergedParams
            )
          ),
        };
        // Promote the matching pending layer to a persisted effect after success.
        setPendingEffects((prev) => prev.filter((p) => p.id !== ne.effect_id));
        const entry = { id: ne.effect_id, name: mergedName, visible: true, status: ne.status };
        setEffectVisibility((prev) => ({ ...prev, [ne.effect_id]: true }));
        setEffects((prev) => (
          prev.some((e) => e.id === ne.effect_id)
            ? prev.map((e) => (e.id === ne.effect_id ? { ...e, name: mergedName, status: ne.status } : e))
            : [...prev, entry]
        ));
        // Move the message cache under the effect ID when it differs from the thread ID.
        if (rid !== ne.effect_id && messagesCacheRef.current[rid]) {
          messagesCacheRef.current[ne.effect_id] = [...(messagesCacheRef.current[ne.effect_id] || []), ...messagesCacheRef.current[rid]];
          delete messagesCacheRef.current[rid];
        }
        setEffectCodes((prev) => ({ ...prev, [ne.effect_id]: ne.code }));
        setEffectParams((prev) => ({ ...prev, [ne.effect_id]: mergedParams }));
        setParameterRanges((prev) => ({ ...prev, [ne.effect_id]: mergedRanges }));
        replaceParams(ne.effect_id, mergedParams);
        updateEditorWorkspaces((current) => {
          const workspace = current[ne.effect_id];
          if (!workspace) return current;
          return {
            ...current,
            [ne.effect_id]: {
              ...workspace,
              boundControlIds: ne.bound_control_ids || [],
            },
          };
        });
        // Auto-select the result only while the user is still viewing its creation flow.
        if (selectedEffectIdRef.current === null || selectedEffectIdRef.current === tid || selectedEffectIdRef.current === rid || selectedEffectIdRef.current === ne.effect_id) {
          setSelectedEffectId(ne.effect_id);
          setThreadId(ne.effect_id);
          conversationLoadedRef.current = ne.effect_id;
        }
      }
      if (result.effect_update) {
        const localPatch = effectPatchScheduler.getLocalPatch(result.effect_update.effect_id);
        applyEffectUpdate(result.effect_update, localPatch);
      }
    };

    startChatRun(tid, {
      video_id: videoInfo.id,
      user_input: text,
      pinned_joints: pinnedJoints,
      selected_option_id: selectedOptionId,
      effect_mentions: effectMentions,
      editor_revision: editorContext.editor_revision,
      editor_selection: editorContext.editor_selection,
      onStage: ({ thread_id: newTid }) => {
        if (newTid && newTid !== tid) {
          // Attach cached first-turn messages after the backend creates the thread.
          const cached = messagesCacheRef.current[tid];
          if (cached && cached.length) {
            messagesCacheRef.current[newTid] = [...(messagesCacheRef.current[newTid] || []), ...cached];
            delete messagesCacheRef.current[tid];
          } else if (pendingUserMsgRef.current) {
            messagesCacheRef.current[newTid] = [pendingUserMsgRef.current];
            pendingUserMsgRef.current = null;
          }
          if (pendingDuringLoadRef.current[tid]) {
            pendingDuringLoadRef.current[newTid] = pendingDuringLoadRef.current[tid];
            delete pendingDuringLoadRef.current[tid];
          }
          if (selectedEffectIdRef.current === tid) setThreadId(newTid);
        }
      },
      onTerminal: (ev) => {
        // Always write terminal results to the originating thread.
        const rid = tid;
        if (ev.status === 'cancelled') {
          const m = withMessageId({ role: 'assistant', content: 'Task cancelled.' });
          if (selectedEffectIdRef.current === rid) setMessages((prev) => [...prev, m]);
          messagesCacheRef.current[rid] = [...(messagesCacheRef.current[rid] || []), m];
          return;
        }
        if (ev.status === 'failed' && ev.error) {
          setChatError(ev.error);
          const m = withMessageId({ role: 'assistant', content: ev.error || 'Task failed.', isError: true });
          if (selectedEffectIdRef.current === rid) setMessages((prev) => [...prev, m]);
          messagesCacheRef.current[rid] = [...(messagesCacheRef.current[rid] || []), m];
          return;
        }
        if (ev.result) applyResult(ev.result);
      },
      onError: (msg) => {
        setChatError(msg);
        const rid = tid;
        const m = withMessageId({ role: 'assistant', content: msg || 'Request failed.', isError: true });
        if (selectedEffectIdRef.current === rid) setMessages((prev) => [...prev, m]);
        messagesCacheRef.current[rid] = [...(messagesCacheRef.current[rid] || []), m];
      },
    });
    return true;
  }, [videoInfo, threadId, currentFrame, selectedPointId, selectedPathId, editorStateSaveQueue, runs, pinnedJoints, startChatRun, resetChatRun, effectPatchScheduler, applyEffectUpdate, replaceParams, updateEditorWorkspaces]);

  const handleRenameEffect = React.useCallback((effectId, newName) => {
    setEffects((prev) => prev.map((e) => e.id === effectId ? { ...e, name: newName } : e));
    effectPatchScheduler.schedule(effectId, { name: newName });
  }, [effectPatchScheduler]);

  const handleUpdateParam = React.useCallback((effectId, key, value) => {
    updateParam(effectId, key, value);
    setEffectParams((current) => ({
      ...current,
      [effectId]: { ...current[effectId], [key]: value },
    }));
    effectPatchScheduler.schedule(effectId, {
      parameter_updates: { [key]: value },
    });
  }, [effectPatchScheduler, updateParam]);

  const handleUpdateRange = React.useCallback((effectId, key, range) => {
    setParameterRanges((current) => ({
      ...current,
      [effectId]: {
        ...(current[effectId] || {}),
        [key]: { min: range.min, max: range.max },
      },
    }));
    const valueChanged = !Object.is(paramsMapRef.current[effectId]?.[key], range.value);
    if (valueChanged) {
      updateParam(effectId, key, range.value);
      setEffectParams((current) => ({
        ...current,
        [effectId]: { ...current[effectId], [key]: range.value },
      }));
    }
    effectPatchScheduler.schedule(effectId, {
      ...(valueChanged ? { parameter_updates: { [key]: range.value } } : {}),
      parameter_range_updates: {
        [key]: { min: range.min, max: range.max },
      },
    }, { immediate: true });
  }, [effectPatchScheduler, paramsMapRef, updateParam]);

  const handleDeleteEffect = React.useCallback((effectId) => {
    // Prevent deletion while generation could write the effect back to disk.
    if (runs[effectId]?.isRunning) return;

    const removal = planEffectRemoval({
      effectId,
      effects,
      pendingEffects,
      selectedEffectId,
    });
    if (!removal.removedEffect && !removal.removedPendingEffect) return;

    const removedCode = effectCodes[effectId];
    const removedParams = effectParams[effectId];
    const removedRanges = parameterRanges[effectId];
    const removedWorkspace = editorWorkspacesRef.current[effectId];
    setEffects(removal.effects);
    setPendingEffects(removal.pendingEffects);
    setEffectCodes((prev) => {
      const next = { ...prev };
      delete next[effectId];
      return next;
    });
    setEffectParams((prev) => {
      const next = { ...prev };
      delete next[effectId];
      return next;
    });
    setParameterRanges((prev) => {
      const next = { ...prev };
      delete next[effectId];
      return next;
    });
    delete messagesCacheRef.current[effectId];
    delete historyLoadingRef.current[effectId];
    delete pendingDuringLoadRef.current[effectId];
    setEffectVisibility((prev) => {
      const next = { ...prev };
      delete next[effectId];
      return next;
    });
    updateEditorWorkspaces((current) => {
      const next = { ...current };
      delete next[effectId];
      return next;
    });
    editorStateSaveQueue.cancel(effectId);
    if (selectedEffectId === effectId) {
      setMessages([]);
      conversationLoadedRef.current = null;
      if (removal.nextSelectedEffectId) {
        handleSelectEffect(removal.nextSelectedEffectId);
      } else {
        setSelectedEffectId(null);
        setThreadId('');
      }
    }
    const creation = workspaceCreationPromisesRef.current[effectId];
    deleteAfterWorkspaceCreation({
      creation,
      remove: () => deleteEffect(effectId),
    }).catch(() => {
      // Restore local state when deletion fails.
      if (removal.removedEffect) {
        setEffects((prev) => (
          prev.some((effect) => effect.id === effectId)
            ? prev
            : [removal.removedEffect, ...prev]
        ));
      }
      if (removal.removedPendingEffect) {
        setPendingEffects((prev) => (
          prev.some((effect) => effect.id === effectId)
            ? prev
            : [...prev, removal.removedPendingEffect]
        ));
      }
      if (removedCode) {
        setEffectCodes((prev) => ({ ...prev, [effectId]: removedCode }));
      }
      if (removedParams) {
        setEffectParams((prev) => ({ ...prev, [effectId]: removedParams }));
      }
      if (removedRanges) {
        setParameterRanges((prev) => ({ ...prev, [effectId]: removedRanges }));
      }
      if (removedWorkspace) {
        updateEditorWorkspaces((current) => ({
          ...current,
          [effectId]: removedWorkspace,
        }));
      }
      setEditorError('Could not delete the Effect Workspace.');
    });
  }, [effects, pendingEffects, runs, selectedEffectId, effectCodes, effectParams, parameterRanges, handleSelectEffect, updateEditorWorkspaces, editorStateSaveQueue]);

  const handleToggleSkeleton = React.useCallback(() => {
    setSkeletonVisible((prev) => !prev);
  }, []);

  const handleToggleEffect = React.useCallback((effectId) => {
    const visible = effectVisibilityRef.current[effectId] !== false;
    const nextVisible = !visible;
    effectVisibilityRef.current = { ...effectVisibilityRef.current, [effectId]: nextVisible };
    setEffectVisibility(effectVisibilityRef.current);
    setEffects((items) => items.map((effect) => (
      effect.id === effectId ? { ...effect, visible: nextVisible } : effect
    )));
  }, []);

  const ensureEditorWorkspace = React.useCallback(async (effectId) => {
    const existing = editorWorkspacesRef.current[effectId];
    if (existing) return existing;
    if (!videoInfo || videoInfo.id === 'local') {
      throw new Error('A processed video is required before adding editor controls.');
    }
    const detail = await createEffectWorkspace(effectId, videoInfo.id);
    const workspace = {
      editorRevision: detail.editor_revision,
      editorState: detail.editor_state,
      boundControlIds: detail.bound_control_ids || [],
    };
    updateEditorWorkspaces((current) => ({ ...current, [effectId]: workspace }));
    return workspace;
  }, [videoInfo, updateEditorWorkspaces]);

  const handleAddEffect = React.useCallback(async () => {
    // Create and select a pending layer immediately so the user can start describing it.
    const id = createWorkspaceId();
    setPendingEffects((prev) => [...prev, { id, name: 'Pending' }]);
    setSelectedEffectId(id);
    selectedEffectIdRef.current = id;
    setThreadId(id);
    threadIdRef.current = id;
    setMessages([]);
    conversationLoadedRef.current = null;
    setInputFocusKey((k) => k + 1);
    const creation = ensureEditorWorkspace(id);
    workspaceCreationPromisesRef.current[id] = creation;
    try {
      await creation;
      setEditorError('');
      return id;
    } catch (error) {
      setEditorError(error?.message || 'Could not create an Effect Workspace.');
      return null;
    } finally {
      if (workspaceCreationPromisesRef.current[id] === creation) {
        delete workspaceCreationPromisesRef.current[id];
      }
    }
  }, [ensureEditorWorkspace]);

  const handleTogglePointTool = React.useCallback(async () => {
    if (!videoInfo || isProcessing) return;
    if (pointToolActive) {
      setPointToolActive(false);
      return;
    }
    let effectId = selectedEffectIdRef.current;
    if (!effectId) effectId = await handleAddEffect();
    if (!effectId) return;
    try {
      await ensureEditorWorkspace(effectId);
      setPathToolActive(false);
      setRedrawPathId(null);
      setPointToolActive(true);
      setEditorError('');
    } catch (error) {
      setEditorError(error?.message || 'Could not enable Point controls.');
    }
  }, [videoInfo, isProcessing, pointToolActive, handleAddEffect, ensureEditorWorkspace]);

  const handleTogglePathTool = React.useCallback(async () => {
    if (!videoInfo || isProcessing) return;
    if (pathToolActive || redrawPathId) {
      setPathToolActive(false);
      setRedrawPathId(null);
      return;
    }
    let effectId = selectedEffectIdRef.current;
    if (!effectId) effectId = await handleAddEffect();
    if (!effectId) return;
    try {
      await ensureEditorWorkspace(effectId);
      setPointToolActive(false);
      setSelectedPointId(null);
      setSelectedPathId(null);
      setPathToolActive(true);
      setEditorError('');
    } catch (error) {
      setEditorError(error?.message || 'Could not enable Path controls.');
    }
  }, [videoInfo, isProcessing, pathToolActive, redrawPathId, handleAddEffect, ensureEditorWorkspace]);

  const handleAddFixedPoint = React.useCallback(({ x, y }) => {
    const effectId = selectedEffectIdRef.current;
    const workspace = editorWorkspacesRef.current[effectId];
    if (!effectId || !workspace) return;
    const pointNumber = workspace.editorState.next_alias.point;
    const pointId = `point-${createWorkspaceId()}`;
    const nextState = {
      ...workspace.editorState,
      points: [
        ...workspace.editorState.points,
        {
          id: pointId,
          alias: `p${pointNumber}`,
          source: { type: 'fixed', x, y },
        },
      ],
      next_alias: {
        ...workspace.editorState.next_alias,
        point: pointNumber + 1,
      },
    };
    const nextWorkspace = { ...workspace, editorState: nextState };
    updateEditorWorkspaces((current) => ({
      ...current,
      [effectId]: nextWorkspace,
    }));
    editorStateSaveQueue.enqueue(
      effectId,
      workspace.editorRevision,
      nextState,
    );
    handleSelectPoint(pointId);
    setPointToolActive(false);
  }, [editorStateSaveQueue, updateEditorWorkspaces, handleSelectPoint]);

  const handleAddPath = React.useCallback((points) => {
    const effectId = selectedEffectIdRef.current;
    const workspace = editorWorkspacesRef.current[effectId];
    if (!effectId || !workspace) return;
    try {
      const pathId = `path-${createWorkspaceId()}`;
      const nextState = addDrawnPath(workspace.editorState, {
        id: pathId,
        points,
      });
      updateEditorWorkspaces((current) => ({
        ...current,
        [effectId]: { ...workspace, editorState: nextState },
      }));
      editorStateSaveQueue.enqueue(effectId, workspace.editorRevision, nextState);
      handleSelectPath(pathId);
      setEditorError('');
    } catch (error) {
      setEditorError(error?.message || 'Could not add the Path.');
    }
  }, [editorStateSaveQueue, updateEditorWorkspaces, handleSelectPath]);

  const handleDeletePath = React.useCallback((pathId) => {
    const effectId = selectedEffectIdRef.current;
    const workspace = editorWorkspacesRef.current[effectId];
    if (!effectId || !workspace) return;
    const deletionError = getPathDeletionError(pathId, workspace.boundControlIds);
    if (deletionError) {
      setEditorError(deletionError);
      return;
    }
    const nextState = removePath(workspace.editorState, pathId);
    updateEditorWorkspaces((current) => ({
      ...current,
      [effectId]: { ...workspace, editorState: nextState },
    }));
    editorStateSaveQueue.enqueue(effectId, workspace.editorRevision, nextState);
    setSelectedPathId(null);
    setEditorError('');
  }, [editorStateSaveQueue, updateEditorWorkspaces]);

  const handleStartRedrawPath = React.useCallback((pathId) => {
    setSelectedPathId(pathId);
    setSelectedPointId(null);
    setPointToolActive(false);
    setPathToolActive(false);
    setRedrawPathId(pathId);
  }, []);

  const handleRedrawPath = React.useCallback((pathId, points) => {
    const effectId = selectedEffectIdRef.current;
    const workspace = editorWorkspacesRef.current[effectId];
    if (!effectId || !workspace) return;
    try {
      const nextState = replacePathPoints(workspace.editorState, pathId, points);
      updateEditorWorkspaces((current) => ({
        ...current,
        [effectId]: { ...workspace, editorState: nextState },
      }));
      editorStateSaveQueue.enqueue(effectId, workspace.editorRevision, nextState);
      setEditorError('');
    } catch (error) {
      setEditorError(error?.message || 'Could not redraw the Path.');
    } finally {
      setRedrawPathId(null);
    }
  }, [editorStateSaveQueue, updateEditorWorkspaces]);

  const handleMovePoint = React.useCallback((pointId, position, jointPosition) => {
    const effectId = selectedEffectIdRef.current;
    const workspace = editorWorkspacesRef.current[effectId];
    if (!effectId || !workspace) return;
    const nextState = movePointToPosition(workspace.editorState, {
      pointId,
      position,
      jointPosition,
    });
    updateEditorWorkspaces((current) => ({
      ...current,
      [effectId]: { ...workspace, editorState: nextState },
    }));
    handleSelectPoint(pointId);
  }, [updateEditorWorkspaces, handleSelectPoint]);

  const handleAddJointPoint = React.useCallback(async (jointName) => {
    if (!videoInfo || isProcessing || !skeletonVisible) return;
    let effectId = selectedEffectIdRef.current;
    if (!effectId) effectId = await handleAddEffect();
    if (!effectId) return;
    try {
      const workspace = await ensureEditorWorkspace(effectId);
      const pointId = `point-${createWorkspaceId()}`;
      const nextState = addJointPoint(workspace.editorState, {
        id: pointId,
        joint: jointName,
      });
      updateEditorWorkspaces((current) => ({
        ...current,
        [effectId]: { ...workspace, editorState: nextState },
      }));
      editorStateSaveQueue.enqueue(
        effectId,
        workspace.editorRevision,
        nextState,
      );
      handleSelectPoint(pointId);
      setEditorError('');
    } catch (error) {
      setEditorError(error?.message || 'Could not add a Joint Point.');
    }
  }, [videoInfo, isProcessing, skeletonVisible, handleAddEffect, ensureEditorWorkspace, updateEditorWorkspaces, editorStateSaveQueue, handleSelectPoint]);

  const handleCommitFixedPoint = React.useCallback(() => {
    const effectId = selectedEffectIdRef.current;
    const workspace = editorWorkspacesRef.current[effectId];
    if (!effectId || !workspace) return;
    editorStateSaveQueue.enqueue(
      effectId,
      workspace.editorRevision,
      workspace.editorState,
    );
  }, [editorStateSaveQueue]);

  const handleDeletePoint = React.useCallback((pointId) => {
    const effectId = selectedEffectIdRef.current;
    const workspace = editorWorkspacesRef.current[effectId];
    if (!effectId || !workspace) return;
    const deletionError = getPointDeletionError(pointId, workspace.boundControlIds);
    if (deletionError) {
      setEditorError(deletionError);
      return;
    }
    const nextState = removePoint(workspace.editorState, pointId);
    updateEditorWorkspaces((current) => ({
      ...current,
      [effectId]: { ...workspace, editorState: nextState },
    }));
    editorStateSaveQueue.enqueue(
      effectId,
      workspace.editorRevision,
      nextState,
    );
    setSelectedPointId(null);
  }, [editorStateSaveQueue, updateEditorWorkspaces]);

  const handleAddTimeMarker = React.useCallback(async (effectId, frame) => {
    try {
      const workspace = await ensureEditorWorkspace(effectId);
      const nextState = addTimeMarker(workspace.editorState, {
        id: `marker-${createWorkspaceId()}`,
        frame,
      });
      updateEditorWorkspaces((current) => ({
        ...current,
        [effectId]: { ...workspace, editorState: nextState },
      }));
      editorStateSaveQueue.enqueue(effectId, workspace.editorRevision, nextState);
      setEditorError('');
    } catch (error) {
      setEditorError(error?.message || 'Could not add the Time Marker.');
    }
  }, [editorStateSaveQueue, ensureEditorWorkspace, updateEditorWorkspaces]);

  const handleMoveTimeMarker = React.useCallback((effectId, markerId, frame) => {
    const workspace = editorWorkspacesRef.current[effectId];
    if (!workspace) return;
    const nextState = moveTimeMarker(workspace.editorState, markerId, frame);
    if (nextState === workspace.editorState) return;
    updateEditorWorkspaces((current) => ({
      ...current,
      [effectId]: { ...workspace, editorState: nextState },
    }));
  }, [updateEditorWorkspaces]);

  const handleCommitTimeMarker = React.useCallback((effectId) => {
    const workspace = editorWorkspacesRef.current[effectId];
    if (!workspace) return;
    editorStateSaveQueue.enqueue(
      effectId,
      workspace.editorRevision,
      workspace.editorState,
    );
  }, [editorStateSaveQueue]);

  const handleDeleteTimeMarker = React.useCallback((effectId, markerId) => {
    const workspace = editorWorkspacesRef.current[effectId];
    if (!workspace) return;
    const deletionError = getTimeMarkerDeletionError(
      workspace.editorState,
      markerId,
      workspace.boundControlIds,
    );
    if (deletionError) {
      setEditorError(deletionError);
      return;
    }
    const nextState = removeTimeMarker(workspace.editorState, markerId);
    updateEditorWorkspaces((current) => ({
      ...current,
      [effectId]: { ...workspace, editorState: nextState },
    }));
    editorStateSaveQueue.enqueue(effectId, workspace.editorRevision, nextState);
    setEditorError('');
  }, [editorStateSaveQueue, updateEditorWorkspaces]);

  const handleTrimEffectClip = React.useCallback((effectId, edge, frame) => {
    const workspace = editorWorkspacesRef.current[effectId];
    if (!workspace) return;
    const nextState = trimEffectClip(workspace.editorState, edge, frame);
    updateEditorWorkspaces((current) => ({
      ...current,
      [effectId]: { ...workspace, editorState: nextState },
    }));
  }, [updateEditorWorkspaces]);

  const handleCommitEffectClip = React.useCallback((effectId) => {
    const workspace = editorWorkspacesRef.current[effectId];
    if (!workspace) return;
    editorStateSaveQueue.enqueue(
      effectId,
      workspace.editorRevision,
      workspace.editorState,
    );
  }, [editorStateSaveQueue]);

  const handleSelectVideo = React.useCallback((videoMeta) => {
    // Reset all state for the newly selected video
    setVideoInfo(videoMeta);
    setProcessingStatus(null);
    setIsProcessing(false);
    setPendingEffects([]);
    resetAllRuns();
    messagesCacheRef.current = {};
    historyLoadingRef.current = {};
    pendingDuringLoadRef.current = {};
    pendingUserMsgRef.current = null;
    setMessages([]);
    setThreadId('');
    setEffects([]);
    setEffectCodes({});
    setEffectParams({});
    setParameterRanges({});
    updateEditorWorkspaces(() => ({}));
    editorStateSaveQueue.cancelAll();
    setPointToolActive(false);
    setPathToolActive(false);
    setRedrawPathId(null);
    setEditorError('');
    setSelectedEffectId(null);
    setSelectedPointId(null);
    setSelectedPathId(null);
    setPinnedJoints({});
    conversationLoadedRef.current = null;

    if (videoMeta.status === 'complete') {
      loadEffectsAndDetails().then((list) => {
        if (list.length > 0 && !selectedEffectId) {
          handleSelectEffect(list[0].id);
        }
      }).catch(() => {});
    }
  }, [loadEffectsAndDetails, resetAllRuns, selectedEffectId, handleSelectEffect, updateEditorWorkspaces, editorStateSaveQueue]);

  const handleRetry = React.useCallback((msgIndex) => {
    const userMsg = messages.slice(0, msgIndex).reverse().find((m) => m.role === 'user');
    if (userMsg) handleSendMessage(userMsg.content, userMsg.selectedOptionId || null);
  }, [messages, handleSendMessage]);

  const handleOptionSelect = React.useCallback((option) => {
    handleSendMessage(formatSelectedOptionMessage(option), option.id);
  }, [handleSendMessage]);

  // ---- Derived values ----
  const hasVideo = !!videoInfo;
  const currentRun = runs[threadId] || { events: [], isRunning: false, isCancelling: false, busy: false };
  const runningEffectIds = Object.keys(runs).filter((tid) => runs[tid]?.isRunning);
  // Disable input only without a video or while pose processing is active.
  // Request serialization remains in the send path to avoid stale UI locks.
  const chatDisabled = !hasVideo || isProcessing;
  const chatDisabledHint = !hasVideo
    ? 'Import a video first.'
    : (isProcessing ? 'Video processing is in progress. Input is temporarily disabled.' : '');
  const processingPct = processingStatus?.percent ?? 0;
  const processingStage = processingStatus?.stage ?? '';
  const selectedWorkspace = selectedEffectId
    ? editorWorkspaces[selectedEffectId]
    : null;

  return (
    <div className="min-h-screen" style={{ backgroundColor: 'var(--editor-bg)' }}>
      <Header onImport={handleImport} onSelectVideo={handleSelectVideo} currentVideoId={videoInfo?.id || ''} />

      <div className="editor-main">
        {/* Top row */}
        <div className="editor-workspace">
          <div className="editor-stage">
          <Toolbar
            skeletonVisible={skeletonVisible}
            onToggleSkeleton={handleToggleSkeleton}
            pointToolActive={pointToolActive}
            onTogglePointTool={handleTogglePointTool}
            pointToolDisabled={!videoInfo || videoInfo.id === 'local' || isProcessing}
            pathToolActive={pathToolActive || !!redrawPathId}
            onTogglePathTool={handleTogglePathTool}
          />
          <div className="editor-preview-area">
            <VideoPreview
              videoInfo={videoInfo}
              effects={effects}
              currentFrame={currentFrame}
              frameEvent={frameEvent}
              isVideoLoading={isVideoLoading}
              videoError={videoError}
              effectsRef={effectsRef}
              paramsMapRef={paramsMapRef}
              effectVisibilityRef={effectVisibilityRef}
              effectVisibility={effectVisibility}
              visualVersion={visualVersion}
              isProcessing={isProcessing}
              pinnedJoints={pinnedJoints}
              onJointClick={handleAddJointPoint}
              skeletonVisible={skeletonVisible}
              editorWorkspaces={editorWorkspaces}
              selectedEditorState={selectedWorkspace?.editorState}
              pointToolActive={pointToolActive}
              pathToolActive={pathToolActive}
              redrawPathId={redrawPathId}
              onAddFixedPoint={handleAddFixedPoint}
              onAddPath={handleAddPath}
              onRedrawPath={handleRedrawPath}
              onCancelRedraw={() => setRedrawPathId(null)}
              onMovePoint={handleMovePoint}
              onCommitPoint={handleCommitFixedPoint}
              selectedPointId={selectedPointId}
              onSelectPoint={handleSelectPoint}
              onDeletePoint={handleDeletePoint}
              selectedPathId={selectedPathId}
              onSelectPath={handleSelectPath}
              onDeletePath={handleDeletePath}
              onStartRedraw={handleStartRedrawPath}
            />
            {editorError ? (
              <div
                data-name="editor-control-error"
                className="absolute left-3 right-3 top-3 rounded-lg px-3 py-2 text-xs"
                style={{
                  zIndex: 40,
                  color: '#FCA5A5',
                  backgroundColor: 'rgba(30,8,12,0.9)',
                  border: '1px solid rgba(248,113,113,0.35)',
                  pointerEvents: 'none',
                }}
              >
                {editorError}
              </div>
            ) : null}
            {/* Processing progress overlay */}
            {isProcessing && (
              <div data-name="processing-overlay"
                className="absolute inset-0 flex flex-col items-center justify-center gap-3"
                style={{
                  borderRadius: 16,
                  backgroundColor: 'rgba(0,0,0,0.65)',
                  backdropFilter: 'blur(4px)',
                  WebkitBackdropFilter: 'blur(4px)',
                }}
              >
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" className="animate-spin">
                  <circle cx="12" cy="12" r="10" stroke="var(--editor-selection)" strokeWidth="2" opacity="0.2" />
                  <path d="M12 2a10 10 0 0 1 10 10" stroke="var(--editor-selection)" strokeWidth="2" strokeLinecap="round" />
                </svg>
                <div className="text-center">
                  <div className="text-sm font-medium text-white">{processingStage}</div>
                  <div className="text-xs font-mono mt-1" style={{ color: '#9CA3AF' }}>{processingPct}%</div>
                </div>
                <div className="w-48 h-1 rounded-full overflow-hidden" style={{ backgroundColor: 'rgba(255,255,255,0.1)' }}>
                  <div className="h-full rounded-full transition-all duration-300" style={{
                    width: `${processingPct}%`,
                    background: 'var(--editor-selection)',
                  }} />
                </div>
              </div>
            )}
          </div>
          <ChatInput
            onSend={(text, mentions) => handleSendMessage(text, null, mentions)}
            isLoading={chatDisabled}
            hasVideo={hasVideo}
            disabledHint={chatDisabledHint}
            focusKey={inputFocusKey}
            effects={effects}
            currentEffectId={selectedEffectId || ''}
            points={selectedWorkspace?.editorState.points || []}
            paths={selectedWorkspace?.editorState.paths || []}
            selectedPointId={selectedPointId}
            selectedPathId={selectedPathId}
            onSelectPoint={handleSelectPoint}
            onSelectPath={handleSelectPath}
          />
          </div>
          <RightPanel
            messages={messages}
            isLoading={currentRun.isRunning}
            onRetry={handleRetry}
            onOptionSelect={handleOptionSelect}
            selectedEffectId={selectedEffectId}
            runEvents={currentRun.events}
            onCancel={() => cancelChatRun(threadId)}
            cancelling={currentRun.isCancelling}
            effectCodes={effectCodes}
            paramsState={paramsState}
            parameterRanges={parameterRanges}
            onUpdateParam={handleUpdateParam}
            onUpdateRange={handleUpdateRange}
            effects={effects}
            onRenameEffect={handleRenameEffect}
          />
        </div>

        {/* Timeline (always visible) */}
        <div className="editor-timeline-wrap">
          <Timeline
            effects={effects}
            selectedEffectId={selectedEffectId}
            onSelectEffect={handleSelectEffect}
            onAddEffect={handleAddEffect}
            onDeleteEffect={handleDeleteEffect}
            onToggleEffect={handleToggleEffect}
            onAddTimeMarker={handleAddTimeMarker}
            onMoveTimeMarker={handleMoveTimeMarker}
            onCommitTimeMarker={handleCommitTimeMarker}
            onDeleteTimeMarker={handleDeleteTimeMarker}
            onTrimEffectClip={handleTrimEffectClip}
            onCommitEffectClip={handleCommitEffectClip}
            runningEffectIds={runningEffectIds}
            pendingEffects={pendingEffects}
            editorWorkspaces={editorWorkspaces}
            totalFrames={timelineTotal}
            currentFrame={currentFrame}
            onFrameChange={seekFrame}
            isPlaying={isPlaying}
            onTogglePlayback={togglePlayback}
            onPausePlayback={pausePlayback}
          />
        </div>
      </div>
    </div>
  );
}
