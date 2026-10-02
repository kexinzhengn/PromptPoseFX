import json
import os
import threading
from typing import Dict

import cv2
import mediapipe as mp
import numpy as np

from .smooth import OneEuroFilter

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")

# In-memory progress tracking
processing_status: Dict[str, dict] = {}
_lock = threading.Lock()


def _update_progress(video_id: str, **kwargs):
    with _lock:
        if video_id in processing_status:
            processing_status[video_id].update(kwargs)


def _get_progress(video_id: str) -> dict:
    with _lock:
        return processing_status.get(video_id, {}).copy()


def run_pipeline(video_id: str):
    """Run the full pose-tracking pipeline in a background thread.

    Stages (stored in ``processing_status[video_id]``):
        * ``stage`` — human-readable stage name (e.g. ``"Running pose
          tracking…"``)
        * ``current`` — frames / items completed in this stage
        * ``total`` — total items for this stage
        * ``percent`` — overall progress ``[0, 100]``
        * ``status`` — ``"processing"`` or ``"complete"``
    """
    try:
        processing_status[video_id] = {
            "stage": "Preparing…",
            "current": 0,
            "total": 100,
            "percent": 0,
            "status": "processing",
        }

        vid_dir = os.path.join(DATA_DIR, video_id)
        img_dir = os.path.join(vid_dir, "img")

        # ---- Stage 1: load image paths ----
        img_names = sorted(
            f for f in os.listdir(img_dir)
            if f.endswith(".jpg") or f.endswith(".png")
        )
        total_frames = len(img_names)
        if total_frames == 0:
            raise RuntimeError(f"No images found in {img_dir}")

        _update_progress(
            video_id,
            stage="Running pose tracking…",
            current=0,
            total=total_frames,
            percent=5,
        )

        # ---- Stage 2: MediaPipe pose tracking ----
        mp_pose = mp.solutions.pose
        normalized_landmarks = []
        world_landmarks = []

        with mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        ) as pose:
            for i, fname in enumerate(img_names):
                img_path = os.path.join(img_dir, fname)
                img = cv2.imread(img_path)
                if img is None:
                    continue
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                results = pose.process(img_rgb)

                if results.pose_landmarks:
                    frame_lm = []
                    frame_world = []
                    for lm in results.pose_landmarks.landmark:
                        frame_lm.append([lm.x, lm.y, lm.z])
                    for wl in results.pose_world_landmarks.landmark:
                        frame_world.append([wl.x, wl.y, wl.z])
                    normalized_landmarks.append(frame_lm)
                    world_landmarks.append(frame_world)
                else:
                    # no pose detected — insert zeros to keep frame alignment
                    normalized_landmarks.append(
                        [[0.0, 0.0, 0.0]] * 33
                    )
                    world_landmarks.append([[0.0, 0.0, 0.0]] * 33)

                # report progress every 10 frames
                if i % 10 == 0 or i == total_frames - 1:
                    pct = 5 + int((i + 1) / total_frames * 75)
                    _update_progress(
                        video_id,
                        current=i + 1,
                        percent=min(pct, 80),
                    )

        lm_array = np.array(normalized_landmarks)  # (T, 33, 3)

        # ---- Stage 3: Smooth landmarks ----
        _update_progress(
            video_id, stage="Smoothing landmarks…", percent=82,
        )
        smoother = OneEuroFilter(min_cutoff=0.2, beta=0.005)
        smoothed, _ = smoother(lm_array)

        # ---- Stage 4: Save .npy files ----
        _update_progress(
            video_id, stage="Saving data…", percent=88,
        )
        np.save(os.path.join(vid_dir, "original_landmark.npy"), lm_array)
        np.save(os.path.join(vid_dir, "smoothed_landmark.npy"), smoothed)
        np.save(
            os.path.join(vid_dir, "world_landmark.npy"),
            np.array(world_landmarks),
        )

        # ---- Stage 5: Convert to JSON ----
        _update_progress(
            video_id, stage="Building JSON…", percent=93,
        )
        data_json = {}
        for frame_idx in range(smoothed.shape[0]):
            frame_jpos = []
            for jidx in range(smoothed.shape[1]):
                x_px = float(smoothed[frame_idx, jidx, 0]) * 640
                y_px = float(smoothed[frame_idx, jidx, 1]) * 360
                frame_jpos.append([x_px, y_px])
            data_json[str(frame_idx)] = frame_jpos

        data_json["frame_number"] = smoothed.shape[0]

        with open(
            os.path.join(vid_dir, "smoothed_landmark.json"), "w"
        ) as f:
            json.dump(data_json, f)

        # Update metadata.json status
        meta_path = os.path.join(vid_dir, "metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            meta["status"] = "complete"
            with open(meta_path, "w") as f:
                json.dump(meta, f)

        _update_progress(
            video_id,
            stage="Complete",
            current=total_frames,
            total=total_frames,
            percent=100,
            status="complete",
        )
    except Exception as exc:
        _update_progress(
            video_id,
            stage=f"Error: {exc}",
            status="error",
        )
        raise


def start_processing(video_id: str) -> dict:
    """Launch the pipeline in a daemon thread and return initial status."""
    status = {"stage": "Queued…", "current": 0, "total": 100, "percent": 0, "status": "processing"}
    processing_status[video_id] = status
    t = threading.Thread(target=run_pipeline, args=(video_id,), daemon=True)
    t.start()
    return status


def get_status(video_id: str) -> dict:
    return _get_progress(video_id)
