export async function prepareEditorChatContext({
  effectId,
  videoId,
  currentFrame,
  selectedPointId,
  selectedPathId,
  getWorkspace,
  saveQueue,
}) {
  if (!effectId || !getWorkspace()) {
    return { editor_revision: null, editor_selection: null };
  }

  await saveQueue.waitForIdle(effectId);
  const workspace = getWorkspace();
  if (!workspace) {
    throw new Error('The Effect Workspace is no longer available.');
  }
  if (workspace.editorState.video_id !== videoId) {
    throw new Error('The Effect Workspace belongs to another video.');
  }

  return {
    editor_revision: workspace.editorRevision,
    editor_selection: {
      current_frame: currentFrame,
      selected_point_id: selectedPointId,
      selected_path_id: selectedPathId,
    },
  };
}
