import React from 'react';
import ChatOptions from './ChatOptions.js';
import { formatAssistantContent } from '../utils/chatMessage.js';

function UserBubble({ content }) {
  return (
    <div key="user" data-name="msg-user" className="editor-message editor-message-user">
      <div className="text-sm leading-relaxed whitespace-pre-line">
        {content}
      </div>
    </div>
  );
}

function AssistantBubble({ content, isError, onRetry, optionsHeader, options, onOptionSelect, optionsDisabled }) {
  const displayContent = formatAssistantContent(content);
  const hasQuotedText = typeof displayContent === 'string' && displayContent.includes('"');

  return (
    <div data-name="msg-assistant" className={`editor-message ${isError ? 'editor-message-error' : ''}`}>
      <div className="text-sm leading-relaxed whitespace-pre-line">
        {hasQuotedText
          ? displayContent.split('"').map((part, j) =>
              j % 2 === 1
                ? <span key={j} className="font-medium" style={{ color: 'var(--editor-text)' }}>"{part}"</span>
                : <span key={j}>{part}</span>
            )
          : displayContent
        }
        {!isError && (
          <ChatOptions
            header={optionsHeader}
            options={options}
            onSelect={onOptionSelect}
            disabled={optionsDisabled}
          />
        )}
        {isError && onRetry && (
          <button type="button" onClick={onRetry} className="text-xs mt-2 font-medium block" style={{ color: '#c18d8d' }}>
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

function TypingIndicator({ stage }) {
  return (
    <div data-name="chat-typing" className="editor-message">
      <div className="flex items-center gap-2">
        {[0, 1, 2].map(i => (
          <span key={i} className="w-2 h-2 rounded-full animate-bounce" style={{
            backgroundColor: 'var(--editor-selection)',
            animationDelay: `${i * 0.15}s`,
          }} />
        ))}
        {stage && (
          <span className="text-xs ml-1" style={{ color: 'var(--editor-muted)' }}>{stage}</span>
        )}
      </div>
    </div>
  );
}

const TOOL_LABELS = {
  validate: 'Validate code',
  submit_code: 'Submit code',
  update_todo: 'Update plan',
  get_pose_stats: 'Read pose data',
};

function RunEventLog({ events }) {
  if (!events || events.length === 0) return null;
  const lines = events
    .map((ev, i) => {
      if (ev.type === 'tool') {
        const label = TOOL_LABELS[ev.tool] || ev.tool;
        const ok = ev.status === 'ok';
        return { key: i, text: `${label}: ${ok ? 'passed' : 'failed'}` };
      }
      if (ev.type === 'retry') {
        return { key: i, text: `Retry ${ev.attempt}` };
      }
      return null;
    })
    .filter(Boolean);
  if (lines.length === 0) return null;
  return (
    <div className="mt-2 space-y-1" style={{ color: 'var(--editor-quiet)', fontSize: 11 }}>
      {lines.map((l) => (
        <div key={l.key}>· {l.text}</div>
      ))}
    </div>
  );
}

export default function ChatPanel({ messages, isLoading, onRetry, onOptionSelect, runEvents, onCancel, cancelling }) {
  const bottomRef = React.useRef(null);

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const empty = (!messages || messages.length === 0) && !isLoading;
  const lastStage = [...(runEvents || [])].reverse().find((ev) => ev.type === 'stage');
  const stage = lastStage?.content;

  return (
    <div data-name="chat-messages" className="editor-chat-messages">
      <div className="editor-chat-scroll">
        {empty && (
          <div className="flex items-center justify-center h-full">
            <span className="text-sm" style={{ color: 'var(--editor-quiet)' }}>Describe the effect you want to create.</span>
          </div>
        )}
        {messages.map((msg, i) =>
          msg.role === 'user'
            ? <UserBubble key={i} content={msg.content} />
            : (
              <AssistantBubble
                key={i}
                content={msg.content}
                isError={msg.isError}
                optionsHeader={msg.optionsHeader}
                options={msg.options}
                onOptionSelect={i === messages.length - 1 ? onOptionSelect : undefined}
                optionsDisabled={isLoading || i !== messages.length - 1}
                onRetry={msg.isError && onRetry ? () => onRetry(i) : undefined}
              />
            )
        )}
        {isLoading && !empty && (
          <>
            <TypingIndicator stage={stage} />
            <RunEventLog events={runEvents} />
          </>
        )}
        <div ref={bottomRef} />
      </div>
      {isLoading && onCancel && (
        <div className="flex-shrink-0 px-5 py-2 border-t" style={{ borderColor: 'var(--editor-line)' }}>
          <button
            data-name="chat-cancel"
            type="button"
            onClick={onCancel}
            disabled={cancelling}
            className="text-xs font-medium"
            style={{ color: cancelling ? 'var(--editor-quiet)' : '#c18d8d', cursor: cancelling ? 'default' : 'pointer' }}
          >
            {cancelling ? 'Cancelling…' : 'Cancel task'}
          </button>
        </div>
      )}
    </div>
  );
}
