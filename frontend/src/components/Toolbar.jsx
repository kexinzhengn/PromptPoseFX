import { PenIcon, PathIcon, BonesIcon } from './icons/Icons.jsx';

export default function Toolbar({
  skeletonVisible,
  onToggleSkeleton,
  pointToolActive,
  onTogglePointTool,
  pointToolDisabled,
  pathToolActive,
  onTogglePathTool,
}) {
  return (
    <div data-name="toolbar" className="flex-shrink-0 flex flex-col items-center pt-3 gap-2" style={{
      width: 42,
    }}>
      {/* Skeleton toggle */}
      <button
        data-name="tool-btn-skeleton"
        type="button"
        aria-label={skeletonVisible ? 'Hide pose controls' : 'Show pose controls'}
        aria-pressed={skeletonVisible}
        data-tooltip="Show or hide pose guides"
        title={skeletonVisible ? 'Hide pose controls' : 'Show pose controls'}
        className="editor-tool-button flex items-center justify-center cursor-pointer"
        style={{
          width: 36, height: 36, borderRadius: 2,
          backgroundColor: skeletonVisible ? '#30343a' : 'transparent',
        }}
        onClick={onToggleSkeleton}
      >
        <BonesIcon active={skeletonVisible} />
      </button>

      <button
        data-name="tool-btn-add-point"
        type="button"
        aria-label={pointToolActive ? 'Exit point tool' : 'Add fixed point'}
        aria-pressed={pointToolActive}
        data-tooltip="Place a reference point"
        title={pointToolDisabled
          ? 'Select a processed video first'
          : (pointToolActive ? 'Exit point tool' : 'Add fixed point')}
        disabled={pointToolDisabled}
        className="editor-tool-button flex items-center justify-center"
        style={{
        width: 36, height: 36, borderRadius: 2,
        backgroundColor: pointToolActive ? '#30343a' : 'transparent',
        opacity: pointToolDisabled ? 0.35 : 1,
        cursor: pointToolDisabled ? 'default' : 'pointer',
      }}
        onClick={onTogglePointTool}
      >
        <PenIcon />
      </button>

      <button
        data-name="tool-btn-draw-path"
        type="button"
        aria-label={pathToolActive ? 'Exit Path tool' : 'Draw Path'}
        aria-pressed={pathToolActive}
        data-tooltip="Draw a reference path"
        title={pointToolDisabled
          ? 'Select a processed video first'
          : (pathToolActive ? 'Exit Path tool' : 'Draw Path')}
        disabled={pointToolDisabled}
        className="editor-tool-button flex items-center justify-center"
        style={{
          width: 36, height: 36, borderRadius: 2,
          backgroundColor: pathToolActive ? '#30343a' : 'transparent',
          opacity: pointToolDisabled ? 0.35 : 1,
          cursor: pointToolDisabled ? 'default' : 'pointer',
        }}
        onClick={onTogglePathTool}
      >
        <PathIcon />
      </button>
    </div>
  );
}
