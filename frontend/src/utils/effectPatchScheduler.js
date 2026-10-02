function mergePatch(current, next) {
  const merged = { ...current, ...next };
  const parameterUpdates = {
    ...(current.parameter_updates || {}),
    ...(next.parameter_updates || {}),
  };
  if (Object.keys(parameterUpdates).length > 0) {
    merged.parameter_updates = parameterUpdates;
  } else {
    delete merged.parameter_updates;
  }
  const parameterRangeUpdates = {
    ...(current.parameter_range_updates || {}),
    ...(next.parameter_range_updates || {}),
  };
  if (Object.keys(parameterRangeUpdates).length > 0) {
    merged.parameter_range_updates = parameterRangeUpdates;
  } else {
    delete merged.parameter_range_updates;
  }
  return merged;
}

export function createEffectPatchScheduler({
  save,
  onSaved = () => {},
  onError = () => {},
  delay = 300,
  setTimer = setTimeout,
  clearTimer = clearTimeout,
}) {
  const entries = new Map();

  function schedule(effectId, patch, { immediate = false } = {}) {
    const entry = entries.get(effectId) || {
      revision: 0,
      pending: {},
      localPatch: {},
      timer: null,
      cancelled: false,
    };
    entry.cancelled = false;
    entry.revision += 1;
    entry.localPatch = mergePatch(entry.localPatch, patch);
    entry.pending = mergePatch(entry.pending, entry.localPatch);
    if (entry.timer !== null) clearTimer(entry.timer);

    const scheduledRevision = entry.revision;
    const persist = async () => {
      entry.timer = null;
      const payload = entry.pending;
      entry.pending = {};
      try {
        const result = await save(effectId, payload);
        if (!entry.cancelled && entry.revision === scheduledRevision) {
          entry.localPatch = {};
          onSaved(result);
        }
      } catch (error) {
        if (!entry.cancelled && entry.revision === scheduledRevision) {
          onError(error, effectId);
        }
      }
    };
    entry.timer = immediate ? null : setTimer(persist, delay);
    entries.set(effectId, entry);
    return immediate ? persist() : undefined;
  }

  function cancelAll() {
    for (const entry of entries.values()) {
      if (entry.timer !== null) clearTimer(entry.timer);
      entry.cancelled = true;
    }
    entries.clear();
  }

  function getLocalPatch(effectId) {
    const patch = entries.get(effectId)?.localPatch || {};
    return mergePatch({}, patch);
  }

  return { schedule, cancelAll, getLocalPatch };
}
