import assert from 'node:assert/strict';
import test from 'node:test';

import { prepareEditorChatContext } from './editorChatContext.js';


test('chat context waits for saved controls and reads the resulting revision', async () => {
  let releaseSave;
  const workspaces = {
    'workspace-1': {
      editorRevision: 0,
      editorState: {
        video_id: 'video-1',
        points: [{ id: 'point-1', alias: 'p1' }],
      },
    },
  };
  const saveQueue = {
    waitForIdle: () => new Promise((resolve) => {
      releaseSave = () => {
        workspaces['workspace-1'] = {
          ...workspaces['workspace-1'],
          editorRevision: 1,
        };
        resolve(1);
      };
    }),
  };

  const pendingContext = prepareEditorChatContext({
    effectId: 'workspace-1',
    videoId: 'video-1',
    currentFrame: 42,
    selectedPointId: 'point-1',
    selectedPathId: 'path-1',
    getWorkspace: () => workspaces['workspace-1'],
    saveQueue,
  });
  releaseSave();

  assert.deepEqual(await pendingContext, {
    editor_revision: 1,
    editor_selection: {
      current_frame: 42,
      selected_point_id: 'point-1',
      selected_path_id: 'path-1',
    },
  });
});
