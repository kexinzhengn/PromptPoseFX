import React from 'react';
import { formatJointName } from '../utils/jointPicker.js';

export default function JointHoverLabel({ joint, width, height }) {
  if (!joint || !width || !height) return null;
  const alignRight = joint.x > width * 0.72;
  const showBelow = joint.y < 38;

  return (
    <div
      className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2"
      style={{ left: `${(joint.x / width) * 100}%`, top: `${(joint.y / height) * 100}%` }}
    >
      <span
        className="block h-5 w-5 rounded-full border-2"
        style={{
          borderColor: '#FFFFFF',
          backgroundColor: 'rgba(45,212,191,0.3)',
          boxShadow: '0 0 0 4px rgba(45,212,191,0.14)',
        }}
      />
      <span
        role="tooltip"
        className="absolute whitespace-nowrap rounded-md border px-2 py-1 text-xs font-medium shadow-lg"
        style={{
          ...(alignRight ? { right: 16 } : { left: 16 }),
          ...(showBelow ? { top: 16 } : { bottom: 16 }),
          color: '#F4F4F5',
          backgroundColor: 'rgba(24,24,30,0.96)',
          borderColor: 'rgba(255,255,255,0.12)',
        }}
      >
        {formatJointName(joint.name)}
      </span>
    </div>
  );
}
