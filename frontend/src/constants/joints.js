/**
 * MediaPipe Pose 33 landmark index → name mapping + skeleton connections.
 * See: https://developers.google.com/mediapipe/solutions/vision/pose_landmarker
 */

export const JOINT_NAMES = [
  'nose',               // 0
  'left_eye_inner',     // 1
  'left_eye',           // 2
  'left_eye_outer',     // 3
  'right_eye_inner',    // 4
  'right_eye',          // 5
  'right_eye_outer',    // 6
  'left_ear',           // 7
  'right_ear',          // 8
  'left_mouth',         // 9
  'right_mouth',        // 10
  'left_shoulder',      // 11
  'right_shoulder',     // 12
  'left_elbow',         // 13
  'right_elbow',        // 14
  'left_wrist',         // 15
  'right_wrist',        // 16
  'left_pinky',         // 17
  'right_pinky',        // 18
  'left_index',         // 19
  'right_index',        // 20
  'left_thumb',         // 21
  'right_thumb',        // 22
  'left_hip',           // 23
  'right_hip',          // 24
  'left_knee',          // 25
  'right_knee',         // 26
  'left_ankle',         // 27
  'right_ankle',        // 28
  'left_heel',          // 29
  'right_heel',         // 30
  'left_foot_index',    // 31
  'right_foot_index',   // 32
];

/** Torso + arm + leg connections (primary skeleton). Named pairs for lookup in frameData.joints. */
export const BODY_CONNECTIONS = [
  ['left_shoulder', 'right_shoulder'],
  ['left_shoulder', 'left_elbow'],     ['left_elbow', 'left_wrist'],
  ['right_shoulder', 'right_elbow'],   ['right_elbow', 'right_wrist'],
  ['left_shoulder', 'left_hip'],       ['right_shoulder', 'right_hip'],
  ['left_hip', 'right_hip'],
  ['left_hip', 'left_knee'],           ['left_knee', 'left_ankle'],
  ['right_hip', 'right_knee'],         ['right_knee', 'right_ankle'],
];

/** Face connections. */
export const FACE_CONNECTIONS = [
  ['nose', 'left_eye_inner'],           ['left_eye_inner', 'left_eye'],
  ['left_eye', 'left_eye_outer'],       ['left_eye_outer', 'left_ear'],
  ['nose', 'right_eye_inner'],          ['right_eye_inner', 'right_eye'],
  ['right_eye', 'right_eye_outer'],     ['right_eye_outer', 'right_ear'],
  ['nose', 'left_mouth'],               ['nose', 'right_mouth'],
  ['left_mouth', 'right_mouth'],
];

/** All connections combined. */
export const ALL_CONNECTIONS = [...BODY_CONNECTIONS, ...FACE_CONNECTIONS];
