import { JOINT_NAMES } from '../constants/joints.js';

export const MAX_POSE_HISTORY_FRAMES = 120;

/**
 * Convert backend landmark JSON into joint data queryable by video frame.
 */
export class PoseTimeline {
  constructor(raw = {}) {
    const { frame_number: _frameNumber, ...frameEntries } = raw;
    this.frames = [];

    for (const [frameText, landmarks] of Object.entries(frameEntries)) {
      const frame = Number.parseInt(frameText, 10);
      if (!Number.isInteger(frame) || !Array.isArray(landmarks)) continue;

      const joints = {};
      for (let index = 0; index < landmarks.length && index < JOINT_NAMES.length; index += 1) {
        joints[JOINT_NAMES[index]] = {
          x: landmarks[index][0],
          y: landmarks[index][1],
        };
      }
      this.frames[frame] = joints;
    }
  }

  /** Return all joints for a video frame, or an empty object when unavailable. */
  getJointsAtFrame(frame) {
    return this.frames[frame] ?? {};
  }

  /** Return ascending joint motion history ending at the requested frame. */
  getJointHistory(jointName, currentFrame, lookbackFrames) {
    if (!JOINT_NAMES.includes(jointName)) return [];

    const count = Math.min(
      MAX_POSE_HISTORY_FRAMES,
      Math.max(1, Math.floor(lookbackFrames)),
    );
    const startFrame = Math.max(0, currentFrame - count + 1);
    const history = [];

    for (let frame = startFrame; frame <= currentFrame; frame += 1) {
      const position = this.frames[frame]?.[jointName];
      const previous = this.frames[frame - 1]?.[jointName];
      const valid = !!position && !(position.x === 0 && position.y === 0);
      const previousValid = !!previous && !(previous.x === 0 && previous.y === 0);
      const connected = valid && previousValid;
      const vx = connected ? position.x - previous.x : 0;
      const vy = connected ? position.y - previous.y : 0;

      history.push({
        frame,
        x: valid ? position.x : null,
        y: valid ? position.y : null,
        vx,
        vy,
        speed: Math.hypot(vx, vy),
        valid,
        connected,
      });
    }

    return history;
  }
}
