import React from 'react';
import ChatPanel from './ChatPanel.jsx';
import ParamsPanel from './ParamsPanel.jsx';

export default function RightPanel({ messages, isLoading, onRetry, onOptionSelect, selectedEffectId, runEvents, onCancel, cancelling, effectCodes, paramsState, parameterRanges, onUpdateParam, onUpdateRange, effects, onRenameEffect }) {
  const [activeTab, setActiveTab] = React.useState('chat');
  const [editingName, setEditingName] = React.useState(false);
  const [draftName, setDraftName] = React.useState('');
  const [renameEffectId, setRenameEffectId] = React.useState(null);
  const cancelRenameRef = React.useRef(false);
  const selectedEffect = effects?.find((effect) => effect.id === selectedEffectId);

  const finishRename = () => {
    if (!cancelRenameRef.current && editingName && draftName.trim() && renameEffectId === selectedEffectId) {
      onRenameEffect?.(renameEffectId, draftName.trim());
    }
    cancelRenameRef.current = false;
    setEditingName(false);
  };

  return (
    <div data-name="right-panel" className="editor-inspector">
      <div className="editor-inspector-heading">
        {selectedEffectId && editingName && renameEffectId === selectedEffectId ? (
          <input
            key={selectedEffectId}
            autoFocus
            aria-label="Rename effect"
            value={draftName}
            onChange={(event) => setDraftName(event.target.value)}
            onBlur={finishRename}
            onKeyDown={(event) => {
              if (event.key === 'Enter') event.currentTarget.blur();
              if (event.key === 'Escape') {
                cancelRenameRef.current = true;
                event.currentTarget.blur();
              }
            }}
          />
        ) : (
          <button
            type="button"
            data-name="params-effect-name"
            disabled={!selectedEffectId}
            title={selectedEffectId ? 'Click to rename' : undefined}
            onClick={() => {
              cancelRenameRef.current = false;
              setDraftName(selectedEffect?.name || '');
              setRenameEffectId(selectedEffectId);
              setEditingName(true);
            }}
          >
            {selectedEffect?.name || (selectedEffectId ? 'New Effect' : 'No effect selected')}
          </button>
        )}
      </div>
      <div data-name="panel-tabs" className="editor-inspector-tabs" role="tablist" aria-label="Inspector panels">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'chat'}
          className={activeTab === 'chat' ? 'active' : ''}
          onClick={() => setActiveTab('chat')}
        >
          Chat
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'params'}
          className={activeTab === 'params' ? 'active' : ''}
          onClick={() => setActiveTab('params')}
        >
          Parameters
        </button>
      </div>

      <div className="editor-inspector-content" style={{ display: activeTab === 'chat' ? 'block' : 'none' }}>
        <ChatPanel
          messages={messages}
          isLoading={isLoading}
          onRetry={onRetry}
          onOptionSelect={onOptionSelect}
          runEvents={runEvents}
          onCancel={onCancel}
          cancelling={cancelling}
        />
      </div>
      <div className="editor-inspector-content" style={{ display: activeTab === 'params' ? 'block' : 'none' }}>
        <ParamsPanel selectedEffectId={selectedEffectId} effectCodes={effectCodes} paramsState={paramsState} parameterRanges={parameterRanges} onUpdateParam={onUpdateParam} onUpdateRange={onUpdateRange} />
      </div>
    </div>
  );
}
