import os
import cv2


def video_to_frames(video_path: str, output_dir: str, fps: int = 30, speed: float = 1.0) -> int:
    """Extract frames from video at the given fps, resize to 640x360, save as JPG.

    Reads every frame sequentially (avoids unreliable seeking), saves every Nth
    frame based on the source fps / target fps ratio, and returns the actual
    number of frames saved.
    """
    os.makedirs(output_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if src_fps <= 0:
        src_fps = 30  # fallback for unreliable metadata

    # How many source frames between each saved frame
    step = max(1, round(src_fps * speed / fps))

    saved = 0
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % step == 0:
            if frame.shape[1] != 640 or frame.shape[0] != 360:
                frame = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
            cv2.imwrite(os.path.join(output_dir, f"{saved:04d}.jpg"), frame)
            saved += 1
        idx += 1

    cap.release()
    return saved
