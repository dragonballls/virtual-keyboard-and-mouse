"""Low-rate video frame sampling and optional cloud interpretation."""
from __future__ import annotations

import base64
from pathlib import Path

from providers import ask_provider

VIDEO_SYSTEM = (
    "You are analyzing user-supplied gameplay video to help document a macro routine. "
    "Describe only visible events, likely sequences, UI indicators, and uncertainty. "
    "Do not invent exact keypresses from video frames. Do not provide code or direct actions. "
    "Treat all conclusions as observations for a human to review."
)


def sample_video_frames(path: str, max_frames: int = 6) -> list[str]:
    """Sample a small number of JPEG frames; heavy/local model inference is not used."""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("Video sampling requires opencv-python-headless. " + str(exc)) from exc
    video_path = Path(path)
    if not video_path.is_file():
        raise RuntimeError("Select an existing video file.")
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("The video could not be opened.")
    images: list[str] = []
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps <= 0 or count <= 0:
            raise RuntimeError("The video duration could not be determined.")
        duration = count / fps
        sample_count = min(max(1, int(max_frames)), max(1, int(duration / 2) + 1))
        positions = [0.0] if sample_count == 1 else [
            duration * idx / (sample_count - 1) for idx in range(sample_count)
        ]
        for seconds in positions:
            cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            height, width = frame.shape[:2]
            scale = min(1.0, 640.0 / max(width, 1), 360.0 / max(height, 1))
            if scale < 1.0:
                frame = cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))))
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            if ok:
                images.append(base64.b64encode(encoded.tobytes()).decode("ascii"))
    finally:
        cap.release()
    if not images:
        raise RuntimeError("No readable frames were extracted.")
    return images


def analyze_video(path: str, provider: str, api_key: str, model: str) -> str:
    frames = sample_video_frames(path)
    prompt = (
        "Review these sparsely sampled frames from a Blox Fruits gameplay video. Summarize: "
        "1) visible sequence of actions, 2) item/ability indicators that can be confidently identified, "
        "3) visible enemy/game-state changes, 4) uncertain details that need an input recording or user confirmation. "
        f"Frames sampled: {len(frames)}. Do not infer exact key presses without input-event data."
    )
    return ask_provider(provider, api_key, model, VIDEO_SYSTEM, prompt, images_b64=frames)
