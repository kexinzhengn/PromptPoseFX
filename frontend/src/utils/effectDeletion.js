export function planEffectRemoval({
  effectId,
  effects,
  pendingEffects,
  selectedEffectId,
}) {
  const removedEffect = effects.find((effect) => effect.id === effectId) || null;
  const removedPendingEffect = pendingEffects.find((effect) => effect.id === effectId) || null;
  const remainingEffects = effects.filter((effect) => effect.id !== effectId);
  const remainingPendingEffects = pendingEffects.filter((effect) => effect.id !== effectId);
  const nextWorkspace = selectedEffectId === effectId
    ? [...remainingEffects, ...remainingPendingEffects][0] || null
    : null;

  return {
    effects: remainingEffects,
    pendingEffects: remainingPendingEffects,
    removedEffect,
    removedPendingEffect,
    nextSelectedEffectId: nextWorkspace?.id || null,
  };
}

export async function deleteAfterWorkspaceCreation({ creation, remove }) {
  if (creation) {
    try {
      await creation;
    } catch {
      return 'not-created';
    }
  }
  await remove();
  return 'deleted';
}
