import { API_BASE, ENDPOINTS } from './constants.js';

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, body || response.statusText);
  }
  return response.json();
}

/** GET /api/health */
export async function checkHealth() {
  return request(`${API_BASE}${ENDPOINTS.health()}`);
}

/** POST /api/chat */
export async function sendChatMessage({
  video_id,
  user_input,
  thread_id = '',
  pinned_joints = {},
  effect_mentions = [],
  selected_option_id = null,
}) {
  return request(`${API_BASE}${ENDPOINTS.chat()}`, {
    method: 'POST',
    body: JSON.stringify({
      video_id,
      user_input,
      thread_id,
      pinned_joints,
      effect_mentions,
      selected_option_id,
    }),
  });
}

/** GET /api/effects */
export async function fetchEffects() {
  const data = await request(`${API_BASE}${ENDPOINTS.effects()}`);
  return data.effects;
}

/** POST /api/effects — create or recover a pending Effect Workspace. */
export async function createEffectWorkspace(effectId, videoId) {
  return request(`${API_BASE}${ENDPOINTS.effects()}`, {
    method: 'POST',
    body: JSON.stringify({ effect_id: effectId, video_id: videoId }),
  });
}

/** GET /api/effect/{effectId} */
export async function fetchEffectDetail(effectId) {
  return request(`${API_BASE}${ENDPOINTS.effect(effectId)}`);
}

/** PATCH /api/effect/{effectId} — update current name or parameter values. */
export async function patchEffect(effectId, patch) {
  return request(`${API_BASE}${ENDPOINTS.effect(effectId)}`, {
    method: 'PATCH',
    keepalive: true,
    body: JSON.stringify(patch),
  });
}

/** PUT /api/effect/{effectId}/editor-state — replace controls at one revision. */
export async function replaceEditorState(effectId, expectedRevision, editorState) {
  return request(`${API_BASE}${ENDPOINTS.editorState(effectId)}`, {
    method: 'PUT',
    body: JSON.stringify({
      expected_revision: expectedRevision,
      editor_state: editorState,
    }),
  });
}

/** DELETE /api/effect/{id} — delete an effect. */
export async function deleteEffect(effectId) {
  return request(`${API_BASE}${ENDPOINTS.effect(effectId)}`, {
    method: 'DELETE',
  });
}

/** GET /api/thread/{id}/conversation — read conversation-only thread data. */
export async function fetchThreadConversation(threadId) {
  return request(`${API_BASE}${ENDPOINTS.threadConversation(threadId)}`);
}

/** POST /api/upload (multipart) */
export async function uploadVideo(file) {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_BASE}${ENDPOINTS.uploadVideo()}`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, body || response.statusText);
  }
  return response.json();
}

/** GET /api/videos */
export async function fetchVideoList() {
  const data = await request(`${API_BASE}${ENDPOINTS.videos()}`);
  return data.videos;
}

/** GET /api/process/{videoId}/status */
export async function getProcessStatus(videoId) {
  return request(`${API_BASE}${ENDPOINTS.processStatus(videoId)}`);
}

/**
 * POST /api/chat/stream — stream a conversation over SSE.
 *
 * Sends the same request as sendChatMessage and receives progress through EventSource callbacks.
 * Adds an onEvent callback to the sendChatMessage parameters.
 *
 * @param {Object} params — the same parameters accepted by sendChatMessage
 * @param {Object} callbacks
 * @param {(stage: string, content: string) => void} callbacks.onStage — stage update callback
 * @param {(result: Object) => void} callbacks.onComplete — successful completion callback
 * @param {(error: string) => void} callbacks.onError — request failure callback
 */
export async function sendChatMessageStream(params, { onStage, onComplete, onError }) {
  const url = `${API_BASE}${ENDPOINTS.chatStream()}`;
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({
        video_id: params.video_id,
        user_input: params.user_input,
        thread_id: params.thread_id || '',
        pinned_joints: params.pinned_joints || {},
        effect_mentions: params.effect_mentions || [],
        selected_option_id: params.selected_option_id || null,
      }),
    });

    if (!response.ok) {
      const body = await response.text();
      throw new ApiError(response.status, body || response.statusText);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finished = false;

    function dispatchEvents(data) {
      if (data.type === 'stage' && onStage) {
        onStage(data.stage, data.content);
      } else if (data.type === 'complete' && onComplete) {
        finished = true;
        onComplete(data);
      } else if (data.type === 'error' && onError) {
        finished = true;
        onError(data.detail || 'Unknown error');
      }
    }

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Split on SSE event boundary (double newline)
      const parts = buffer.split('\n\n');
      for (let i = 0; i < parts.length - 1; i++) {
        const lines = parts[i].split('\n');
        let eventType = '';
        let dataStr = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            dataStr = line.slice(6).trim();
          }
        }
        if (eventType && dataStr) {
          try {
            dispatchEvents({ type: eventType, ...JSON.parse(dataStr) });
          } catch (e) {
            console.warn('SSE parse error:', e);
          }
        }
      }
      buffer = parts[parts.length - 1];
    }

    // Stream ended without complete/error event
    if (!finished) {
      onError?.('The connection closed unexpectedly.');
    }
  } catch (err) {
    if (!finished && onError) {
      onError(err instanceof ApiError ? err.message : (err.message || 'Network error'));
    }
  }
}

/** POST /api/chat/run — submit a chat run and return its run and thread IDs. */
export async function createRun({
  video_id,
  user_input,
  thread_id = '',
  pinned_joints = {},
  selected_option_id = null,
  effect_mentions = [],
  editor_revision = null,
  editor_selection = null,
}) {
  return request(`${API_BASE}${ENDPOINTS.chatRun()}`, {
    method: 'POST',
    body: JSON.stringify({
      video_id,
      user_input,
      thread_id,
      pinned_joints,
      selected_option_id,
      effect_mentions,
      editor_revision,
      editor_selection,
    }),
  });
}

/** GET /api/run/{runId}/events — subscribe to run events through EventSource. */
export function subscribeRun(runId, { onEvent, onError }) {
  const es = new EventSource(`${API_BASE}${ENDPOINTS.runEvents(runId)}`);
  es.addEventListener('message', (e) => {
    try {
      onEvent(JSON.parse(e.data));
    } catch {
      // Ignore malformed events.
    }
  });
  es.onerror = () => {
    onError?.('The event stream connection was interrupted.');
    es.close();
  };
  return es;
}

/** POST /api/run/{runId}/cancel — cancel an active run. */
export async function cancelRun(runId) {
  return request(`${API_BASE}${ENDPOINTS.runCancel(runId)}`, {
    method: 'POST',
  });
}
