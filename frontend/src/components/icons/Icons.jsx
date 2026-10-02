export const PlayIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
);
export const SendIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 2L11 13" /><path d="M22 2L15 22L11 13L2 9L22 2Z" />
  </svg>
);
export const PenIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
  </svg>
);
export const PathIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 17c4-9 7 4 11-5s5-2 7 1" />
    <circle cx="3" cy="17" r="1.5" />
    <circle cx="21" cy="13" r="1.5" />
  </svg>
);
export const BonesIcon = ({ active }) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={active ? '#8ea3be' : '#9a9a9a'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="17" cy="4" r="2.5" />
    <circle cx="7" cy="20" r="2.5" />
    <path d="M15 5.5L9 18.5" />
    <circle cx="12" cy="8" r="1.5" />
    <circle cx="10" cy="14" r="1.5" />
  </svg>
);
