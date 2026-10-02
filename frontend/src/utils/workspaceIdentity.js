export function createWorkspaceId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `workspace-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function resolveWorkspaceId(threadId, selectedEffectId, createId = createWorkspaceId) {
  return threadId || selectedEffectId || createId();
}
