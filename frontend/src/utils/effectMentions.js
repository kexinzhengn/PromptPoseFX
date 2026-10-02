/** Find the unfinished @mention at the end of the current input. */
export function findMentionQuery(text = '') {
  const start = text.lastIndexOf('@');
  if (start < 0) return null;
  return { start, query: text.slice(start + 1).trim().toLocaleLowerCase() };
}

/** Return searchable active Effects, excluding the current and already mentioned ones. */
export function getMentionCandidates(
  effects = [],
  currentEffectId = '',
  mentions = [],
  query = '',
) {
  const used = new Set(mentions.map((mention) => mention.effect_id));
  const normalizedQuery = query.trim().toLocaleLowerCase();
  return effects.filter((effect) => (
    effect.status === 'active'
    && effect.id !== currentEffectId
    && !used.has(effect.id)
    && effect.name.toLocaleLowerCase().includes(normalizedQuery)
  ));
}

/** Replace an unfinished mention with a visible name and return its stable payload. */
export function applyMentionSelection(text, start, effect) {
  return {
    text: `${text.slice(0, start)}@${effect.name} `,
    mention: { effect_id: effect.id, display_name: effect.name },
  };
}

/** Drop structured mentions whose visible tag was removed from the input. */
export function reconcileMentions(text, mentions = []) {
  return mentions.filter((mention) => text.includes(`@${mention.display_name}`));
}
