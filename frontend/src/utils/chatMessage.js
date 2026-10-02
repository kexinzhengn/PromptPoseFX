/**
 * Convert a chat API result into the assistant message used by the UI.
 * Add clarification fields only when options are present.
 */
export function createAssistantMessage(result) {
  const message = {
    role: 'assistant',
    content: result?.response ?? '',
  };

  if (!Array.isArray(result?.options) || result.options.length === 0) {
    return message;
  }

  return {
    ...message,
    optionsHeader: result.options_header ?? '',
    options: result.options,
  };
}

/** Collapse legacy Effect-ready replies without rewriting conversation storage. */
export function formatAssistantContent(content = '') {
  const legacyMarker = ' is ready. Adjust its controls in the Parameters panel.\n\nParameters:';
  const markerIndex = content.indexOf(legacyMarker);
  if (markerIndex < 0) return content;

  const effectName = content.slice(0, markerIndex).trim();
  const parameterLines = content
    .slice(markerIndex + legacyMarker.length)
    .split('\n')
    .filter((line) => line.trim().includes(' — '));
  const controlCount = parameterLines.length;
  const controlLabel = controlCount === 1 ? 'control' : 'controls';

  return `${effectName} is ready.\n${controlCount} ${controlLabel} available in Parameters.`;
}

/** Add a unique ID that distinguishes local/server copies from repeated messages. */
export function withMessageId(message) {
  const id = (typeof crypto !== 'undefined' && crypto.randomUUID)
    ? crypto.randomUUID()
    : `msg-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return { ...message, id };
}

function messageKey(message) {
  return `${message.role}\u0000${message.content}`;
}

/**
 * Merge local messages with history loaded from the server.
 *
 * Local messages remain first because they are newest. Skip a server message only when
 * it duplicates a local message sent during history loading. Append all other history
 * in server order and preserve repeated local messages.
 */
export function mergeConversation(local = [], remote = [], pendingLocalKeys = new Set()) {
  const result = [...local];
  const stamp = Date.now();
  remote.forEach((msg, index) => {
    const withId = { ...msg, id: `hist-${index}-${stamp}` };
    if (pendingLocalKeys.has(messageKey(withId))) return;
    result.push(withId);
  });
  return result;
}

/**
 * Filter persisted conversation history for display.
 *
 * conversation.json may include tool messages containing full code and empty assistant
 * placeholders for tool calls. Keep only visible user and assistant text.
 */
export function filterConversationForDisplay(conversation = []) {
  return conversation.filter(
    (msg) => msg.role === 'user' || (msg.role === 'assistant' && msg.content),
  );
}

/**
 * Remove <options> markup from assistant messages and keep the question text.
 *
 * The selected value appears as the next user message, so history does not need to list
 * every option again.
 */
export function stripOptionsMarkup(content = '') {
  return content
    .replace(/<options>[\s\S]*?<\/options>/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/**
 * Remove the context prefix stored at the start of user messages in legacy archives.
 * New archives store clean text; this remains a compatibility fallback.
 */
export function stripContextPrefix(content = '') {
  return content.replace(/^(?:\[[^\]]*\]\n)+\n?/, '');
}
