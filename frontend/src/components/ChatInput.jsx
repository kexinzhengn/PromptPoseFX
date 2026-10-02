import React from 'react';
import { SendIcon } from './icons/Icons.jsx';
import EffectMentionOption from './EffectMentionOption.js';
import PointReferenceStrip from './PointReferenceStrip.js';
import {
  applyMentionSelection,
  findMentionQuery,
  getMentionCandidates,
  reconcileMentions,
} from '../utils/effectMentions.js';
import { shouldFocusInputFromRow } from '../utils/chatInputInteraction.js';
import { APP_LAYERS } from '../utils/layoutLayers.js';

export default function ChatInput({
  onSend,
  isLoading,
  hasVideo,
  disabledHint = '',
  focusKey = 0,
  effects = [],
  currentEffectId = '',
  points = [],
  paths = [],
  selectedPointId = null,
  selectedPathId = null,
  onSelectPoint,
  onSelectPath,
}) {
  const [text, setText] = React.useState('');
  const [mentions, setMentions] = React.useState([]);
  const [mentionQuery, setMentionQuery] = React.useState(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const inputRef = React.useRef(null);
  const submittingRef = React.useRef(false);
  const prevHasVideoRef = React.useRef(hasVideo);

  // Focus the input after a new effect layer is added.
  React.useEffect(() => {
    if (focusKey > 0) inputRef.current?.focus();
  }, [focusKey]);

  // Focus automatically when a video becomes available.
  React.useEffect(() => {
    const wasWithoutVideo = !prevHasVideoRef.current;
    prevHasVideoRef.current = hasVideo;
    if (hasVideo && wasWithoutVideo) inputRef.current?.focus();
  }, [hasVideo]);

  const handleSend = async () => {
    if (!text.trim() || isLoading || !hasVideo || submittingRef.current) return;
    submittingRef.current = true;
    setIsSubmitting(true);
    try {
      const sent = await onSend(text.trim(), mentions);
      if (sent !== false) {
        setText('');
        setMentions([]);
        setMentionQuery(null);
      }
    } finally {
      submittingRef.current = false;
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Escape' && mentionQuery) {
      setMentionQuery(null);
      return;
    }
    if (e.key === 'Enter' && mentionQuery && candidates.length > 0) {
      e.preventDefault();
      selectMention(candidates[0]);
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTextChange = (value) => {
    setText(value);
    const nextMentions = reconcileMentions(value, mentions);
    setMentions(nextMentions);
    const query = findMentionQuery(value);
    const pointsToExisting = query && nextMentions.some(
      (mention) => value.slice(query.start).startsWith(`@${mention.display_name}`),
    );
    setMentionQuery(pointsToExisting ? null : query);
  };

  const candidates = mentionQuery
    ? getMentionCandidates(
        effects,
        currentEffectId,
        mentions,
        mentionQuery.query,
      )
    : [];

  const selectMention = (effect) => {
    if (!mentionQuery) return;
    const selection = applyMentionSelection(text, mentionQuery.start, effect);
    setText(selection.text);
    setMentions((current) => [...current, selection.mention]);
    setMentionQuery(null);
    inputRef.current?.focus();
  };

  return (
    <div data-name="chat-input" className="editor-chat-input relative w-full" style={{
      opacity: hasVideo ? 1 : 0.5,
      zIndex: APP_LAYERS.chatInput,
      height: 96,
    }}>
      {mentionQuery && candidates.length > 0 ? (
        <div
          aria-label="Reference an Effect"
          data-name="effect-mention-menu"
          className="editor-mention-menu absolute bottom-full left-0 z-20 mb-2 w-full overflow-hidden"
        >
          <div className="px-3 py-2 text-xs" style={{ color: 'var(--editor-muted)' }}>
            Reference an Effect
          </div>
          {candidates.map((effect) => (
            <EffectMentionOption
              key={effect.id}
              effect={effect}
              onSelect={selectMention}
            />
          ))}
        </div>
      ) : null}
      <div
        className="flex items-center gap-3 px-5"
        style={{ height: 56 }}
        // Focus from any point in the input row to avoid browser pointer-focus issues.
        onMouseDown={(event) => {
          const shouldFocus = shouldFocusInputFromRow(event.target, event.currentTarget);
          if (shouldFocus) {
            inputRef.current?.focus();
          }
        }}
      >
        <input
          ref={inputRef}
          data-name="chat-input-field"
          type="text"
          value={text}
          onChange={(e) => handleTextChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={hasVideo ? "Describe the VFX you want..." : "Import a video first"}
          disabled={!hasVideo || isLoading || isSubmitting}
          className="flex-1 bg-transparent text-sm outline-none"
          style={{ color: 'var(--editor-text)' }}
        />
        <button
          data-name="chat-send-btn"
          onClick={handleSend}
          disabled={!text.trim() || isLoading || isSubmitting || !hasVideo}
          className="editor-chat-send flex-shrink-0"
          style={{ opacity: text.trim() && !isLoading && !isSubmitting && hasVideo ? 1 : 0.3, cursor: text.trim() && !isLoading && !isSubmitting && hasVideo ? 'pointer' : 'default' }}
        >
          <SendIcon />
        </button>
      </div>
      <div
        data-name="chat-input-context"
        className="flex items-center gap-3 px-5 overflow-hidden"
        style={{ height: 40 }}
      >
        <PointReferenceStrip
          points={points}
          paths={paths}
          selectedPointId={selectedPointId}
          selectedPathId={selectedPathId}
          onSelectPoint={onSelectPoint}
          onSelectPath={onSelectPath}
        />
        {disabledHint ? (
          <span data-name="chat-input-hint" className="flex-shrink-0 text-xs" style={{ color: 'var(--editor-muted)' }}>
            {disabledHint}
          </span>
        ) : null}
      </div>
    </div>
  );
}
