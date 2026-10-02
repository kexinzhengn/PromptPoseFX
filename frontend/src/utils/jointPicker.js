export const JOINT_HIT_RADIUS = 18;

export function formatJointName(name) {
  return name
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function findNearestJoint(joints, x, y, maxDistance = JOINT_HIT_RADIUS) {
  let nearest = null;
  let nearestDistance = maxDistance;

  for (const [name, position] of Object.entries(joints || {})) {
    if (!position || (position.x === 0 && position.y === 0)) continue;
    const distance = Math.hypot(position.x - x, position.y - y);
    if (distance > nearestDistance) continue;
    nearest = { name, x: position.x, y: position.y };
    nearestDistance = distance;
  }

  return nearest;
}

export function resolvePointCreation({ joints, x, y, addMode }) {
  const joint = findNearestJoint(joints, x, y);
  if (joint) return { type: 'joint', joint: joint.name };
  return addMode ? { type: 'fixed' } : null;
}
