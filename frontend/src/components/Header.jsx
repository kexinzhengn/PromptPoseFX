import React from 'react';
import { fetchVideoList } from '../api/api.js';

function ChevronIcon() {
  return (
    <svg width="10" height="6" viewBox="0 0 10 6" fill="none" aria-hidden="true">
      <path d="M1 1L5 5L9 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Header({ onImport, onSelectVideo, currentVideoId }) {
  const fileInputRef = React.useRef(null);
  const menuRef = React.useRef(null);
  const [videos, setVideos] = React.useState([]);
  const [open, setOpen] = React.useState(false);

  const refreshList = React.useCallback(() => {
    fetchVideoList()
      .then((list) => {
        setVideos(list);
        if (list.length > 0 && !currentVideoId) {
          onSelectVideo(list.find((video) => video.status === 'complete') || list[0]);
        }
      })
      .catch(() => {});
  }, [currentVideoId, onSelectVideo]);

  React.useEffect(() => {
    refreshList();
  }, [refreshList]);

  React.useEffect(() => {
    if (!open) return;
    const handleOutsideClick = (event) => {
      if (!menuRef.current?.contains(event.target)) setOpen(false);
    };
    const handleEscape = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', handleOutsideClick);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('pointerdown', handleOutsideClick);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  const selectedVideo = videos.find((video) => video.id === currentVideoId);

  return (
    <header className="editor-header">
      <div data-name="header" className="editor-header-inner">
        <div data-name="header-logo" className="editor-wordmark">
          PromptPose<span className="editor-wordmark-fx">FX</span>
        </div>

        <div className="editor-video-picker" ref={menuRef}>
          <div className="editor-video-select-wrap">
            <button
              data-name="header-video-select"
              type="button"
              className="editor-video-select"
              aria-label="Select video"
              aria-expanded={open}
              aria-haspopup="menu"
              onClick={() => {
                if (!open) refreshList();
                setOpen((value) => !value);
              }}
            >
              <span className="editor-video-name">{selectedVideo?.name || currentVideoId || 'Select video'}</span>
              <ChevronIcon />
            </button>

            {open && (
              <div className="editor-video-menu" role="menu" aria-label="Videos">
                {videos.length === 0 ? (
                  <div className="editor-video-empty">No videos yet</div>
                ) : videos.map((video) => (
                  <button
                    key={video.id}
                    type="button"
                    role="menuitem"
                    data-name="video-option"
                    className="editor-video-option"
                    aria-current={video.id === currentVideoId ? 'true' : undefined}
                    onClick={() => {
                      setOpen(false);
                      onSelectVideo(video);
                    }}
                  >
                    <span className="editor-video-option-name">{video.name || video.id}</span>
                    <span className="editor-video-option-status">
                      {video.status === 'complete' ? 'Ready' : video.status === 'error' ? 'Failed' : 'Processing'}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            data-name="header-import-btn"
            type="button"
            className="editor-import-button"
            onClick={() => fileInputRef.current?.click()}
          >
            Import
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="video/*"
            hidden
            onChange={(event) => {
              if (event.target.files?.[0]) onImport(event.target.files[0]);
              event.target.value = '';
            }}
          />
        </div>
      </div>
    </header>
  );
}
