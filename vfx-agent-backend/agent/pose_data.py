import json
import os
from typing import Optional


# MediaPipe Pose landmark index to joint name.
JOINT_NAMES = {
    0: 'nose',
    11: 'left_shoulder', 12: 'right_shoulder',
    13: 'left_elbow', 14: 'right_elbow',
    15: 'left_wrist', 16: 'right_wrist',
    23: 'left_hip', 24: 'right_hip',
    25: 'left_knee', 26: 'right_knee',
    27: 'left_ankle', 28: 'right_ankle',
}


from config import POSE_DATA_DIR


class PoseDataReader:
    """Read and summarize stored pose data."""

    def __init__(self, video_id: str, data_dir: str = ""):
        self.video_id = video_id
        data_dir = data_dir or POSE_DATA_DIR
        file_path = os.path.join(data_dir, video_id, "smoothed_landmark.json")
        with open(file_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)

    def get_stats(self) -> dict:
        """
        Calculate pose-data statistics.

        Returns:
            {
                "total_frames": 231,
                "fps": 30,
                "duration_seconds": 7.7,
                "joints": ["left_wrist", ...],
                "motion_range": {
                    "left_wrist": {"min_x": 50, "max_x": 500, "min_y": 30, "max_y": 400,
                                   "range_x": 450, "range_y": 370, "max_disp": 480},
                    ...
                }
            }
        """
        frames = sorted([k for k in self.data.keys() if k.isdigit()], key=int)
        total_frames = len(frames)

        # Collect each joint's coordinates across all frames.
        motion = {name: {"xs": [], "ys": []} for name in JOINT_NAMES.values()}
        present_joints = set()

        for frame_key in frames:
            landmarks = self.data[frame_key]
            for idx, name in JOINT_NAMES.items():
                if idx < len(landmarks):
                    pt = landmarks[idx]
                    if pt[0] >= 0 and pt[1] >= 0:
                        motion[name]["xs"].append(pt[0])
                        motion[name]["ys"].append(pt[1])
                        present_joints.add(name)

        # Calculate per-joint motion ranges.
        motion_range = {}
        for name in sorted(present_joints):
            xs = motion[name]["xs"]
            ys = motion[name]["ys"]
            if not xs:
                continue
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            range_x = max_x - min_x
            range_y = max_y - min_y
            max_disp = max(range_x, range_y)
            motion_range[name] = {
                "min_x": min_x, "max_x": max_x,
                "min_y": min_y, "max_y": max_y,
                "range_x": range_x, "range_y": range_y,
                "max_disp": max_disp,
            }

        avg_fps = 30  # Pose data does not include FPS, so assume 30.

        return {
            "total_frames": total_frames,
            "fps": avg_fps,
            "duration_seconds": total_frames / avg_fps,
            "joints": sorted(present_joints),
            "motion_range": motion_range,
        }

    def get_joint_position(self, joint_name: str, frame: int) -> Optional[dict]:
        """
        Return a joint position for a specific frame.

        Args:
            joint_name: Joint name such as "left_wrist".
            frame: Zero-based video frame number.

        Returns:
            Coordinates, or None when the joint is unavailable.
        """
        frame_key = str(frame)
        if frame_key not in self.data:
            return None

        # Resolve the landmark index for the joint name.
        idx = None
        for i, name in JOINT_NAMES.items():
            if name == joint_name:
                idx = i
                break
        if idx is None:
            return None

        landmarks = self.data[frame_key]
        if idx >= len(landmarks):
            return None

        pt = landmarks[idx]
        if pt[0] < 0 or pt[1] < 0:
            return None

        return {"x": pt[0], "y": pt[1]}
