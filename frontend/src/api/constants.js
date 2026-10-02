export const API_BASE = import.meta.env?.VITE_API_BASE || '';

export const ENDPOINTS = {
  health:        () => `/api/health`,
  chat:          () => `/api/chat`,
  chatStream:    () => `/api/chat/stream`,
  chatRun:       () => `/api/chat/run`,
  runEvents: (id) => `/api/run/${id}/events`,
  runCancel: (id) => `/api/run/${id}/cancel`,
  effects:       () => `/api/effects`,
  effect:  (id) => `/api/effect/${id}`,
  editorState: (id) => `/api/effect/${id}/editor-state`,
  threadConversation: (id) => `/api/thread/${id}/conversation`,
  uploadVideo:   () => `/api/upload`,
  processStatus: (id) => `/api/process/${id}/status`,
  videos:          () => `/api/videos`,
};
