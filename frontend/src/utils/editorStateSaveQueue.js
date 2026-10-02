export function createEditorStateSaveQueue({
  save,
  onSaved = () => {},
  onError = () => {},
}) {
  const entries = new Map();

  function resolveIdleWaiters(entry) {
    if (entry.inFlight || entry.pending || entry.blocked) return;
    const waiters = entry.waiters.splice(0);
    for (const waiter of waiters) waiter.resolve(entry.serverRevision);
  }

  function rejectWaiters(entry, error) {
    const waiters = entry.waiters.splice(0);
    for (const waiter of waiters) waiter.reject(error);
  }

  function pump(effectId, entry) {
    if (entry.inFlight || entry.blocked || !entry.pending) return;
    const task = entry.pending;
    entry.pending = null;
    entry.inFlight = true;

    Promise.resolve(save(effectId, entry.serverRevision, task.editorState))
      .then((result) => {
        if (entry.cancelled) return;
        entry.serverRevision = result.editor_revision;
        entry.inFlight = false;
        if (entry.localVersion === task.localVersion) {
          onSaved(result);
        }
        pump(effectId, entry);
        resolveIdleWaiters(entry);
      })
      .catch((error) => {
        if (entry.cancelled) return;
        entry.inFlight = false;
        entry.blocked = true;
        entry.lastError = error;
        if (!entry.pending) entry.pending = task;
        rejectWaiters(entry, error);
        onError(error, effectId);
      });
  }

  function enqueue(effectId, expectedRevision, editorState) {
    const entry = entries.get(effectId) || {
      serverRevision: expectedRevision,
      localVersion: 0,
      pending: null,
      inFlight: false,
      blocked: false,
      cancelled: false,
      lastError: null,
      waiters: [],
    };
    entry.localVersion += 1;
    entry.pending = {
      localVersion: entry.localVersion,
      editorState,
    };
    entries.set(effectId, entry);
    pump(effectId, entry);
  }

  function retry(effectId, serverRevision) {
    const entry = entries.get(effectId);
    if (!entry) return;
    if (Number.isInteger(serverRevision)) entry.serverRevision = serverRevision;
    entry.blocked = false;
    entry.lastError = null;
    pump(effectId, entry);
  }

  function waitForIdle(effectId) {
    const entry = entries.get(effectId);
    if (!entry) return Promise.resolve(null);
    if (entry.blocked) return Promise.reject(entry.lastError || new Error('Editor state save failed'));
    if (!entry.inFlight && !entry.pending) return Promise.resolve(entry.serverRevision);
    return new Promise((resolve, reject) => {
      entry.waiters.push({ resolve, reject });
    });
  }

  function cancelAll() {
    for (const entry of entries.values()) {
      entry.cancelled = true;
      rejectWaiters(entry, new Error('Editor state save was cancelled'));
    }
    entries.clear();
  }

  function cancel(effectId) {
    const entry = entries.get(effectId);
    if (!entry) return;
    entry.cancelled = true;
    rejectWaiters(entry, new Error('Editor state save was cancelled'));
    entries.delete(effectId);
  }

  return { enqueue, retry, waitForIdle, cancel, cancelAll };
}
