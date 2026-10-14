"""Bounded video and recording analysis; all results remain human-reviewed notes."""
from __future__ import annotations

import base64
import json
import math
from pathlib import Path

from providers import ask_provider

MAX_VIDEO_FRAMES = 6
MAX_RECORDING_EVENTS = 48
MAX_RECORDING_FILE_BYTES = 12 * 1024 * 1024
MAX_FRAME_FILE_BYTES = 512 * 1024

_ALLOWED_KEYS = frozenset({
    "w", "a", "s", "d", "q", "e", "z", "x", "c", "v", "f", "r",
    "1", "2", "3", "4", "5", "space", "shift", "esc", "tab",
})
_ALLOWED_BUTTONS = frozenset({"left", "right", "middle"})

VIDEO_SYSTEM = (
    "Analyze a user-supplied gameplay video to produce neutral, human-reviewed observations. Describe only "
    "visible events, UI indicators, state changes, and uncertainty. Do not invent keypresses or hidden state. "
    "Do not provide weapon-use, attack, or combat tactics; do not return code, executable automation instructions, "
    "or actions to perform. All findings are advisory notes that the user must review."
)


def _bounded_frame_count(value: object, default: int = MAX_VIDEO_FRAMES) -> int:
    """Keep internal callers from raising the six-frame privacy/payload ceiling."""
    try:
        count = int(value)
    except (TypeError, ValueError, OverflowError):
        count = default
    return max(1, min(MAX_VIDEO_FRAMES, count))


def _is_finite_nonnegative_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value)) and value >= 0
    except (ValueError, TypeError, OverflowError):
        return False


def sample_video_frames(path: str, max_frames: int = MAX_VIDEO_FRAMES) -> list[str]:
    """Sample at most six small JPEG frames without local model inference."""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("Video sampling requires opencv-python-headless. " + str(exc)) from exc

    video_path = Path(path)
    if not video_path.is_file():
        raise RuntimeError("Select an existing video file.")
    try:
        cap = cv2.VideoCapture(str(video_path))
    except Exception:
        raise RuntimeError("The video could not be opened.") from None
    if not cap.isOpened():
        cap.release()
        raise RuntimeError("The video could not be opened.")

    images: list[str] = []
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if (
            not math.isfinite(fps) or not math.isfinite(frame_count)
            or fps <= 0 or frame_count <= 0
        ):
            raise RuntimeError("The video duration could not be determined.")
        duration = frame_count / fps
        if not math.isfinite(duration) or duration <= 0:
            raise RuntimeError("The video duration could not be determined.")
        limit = _bounded_frame_count(max_frames)
        sample_count = min(limit, max(1, int(duration / 2) + 1))
        last_time = max(0.0, duration - (1.0 / fps))
        positions = [0.0] if sample_count == 1 else [
            last_time * idx / (sample_count - 1) for idx in range(sample_count)
        ]
        for seconds in positions:
            cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            height, width = frame.shape[:2]
            scale = min(1.0, 640.0 / max(width, 1), 360.0 / max(height, 1))
            if scale < 1.0:
                frame = cv2.resize(
                    frame, (max(1, int(width * scale)), max(1, int(height * scale)))
                )
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            if ok:
                images.append(base64.b64encode(encoded.tobytes()).decode("ascii"))
            if len(images) >= MAX_VIDEO_FRAMES:
                break
    finally:
        cap.release()

    if not images:
        raise RuntimeError("No readable frames were extracted.")
    return images[:MAX_VIDEO_FRAMES]


def analyze_video(path: str, provider: str, api_key: str, model: str) -> str:
    frames = sample_video_frames(path, max_frames=MAX_VIDEO_FRAMES)
    prompt = (
        "Review these sparsely sampled frames from a gameplay video. Summarize visible events, "
        "recognizable UI indicators, visible game-state changes, and details that remain uncertain. "
        "Do not infer exact key presses or unseen mechanics from frames alone. "
        f"Frames sampled: {len(frames)}."
    )
    return ask_provider(provider, api_key, model, VIDEO_SYSTEM, prompt, images_b64=frames)


def _sample_recording_frames(
    recording_dir: Path, max_frames: int = MAX_VIDEO_FRAMES
) -> tuple[list[str], list[int]]:
    """Read a bounded subset of small JPEG screenshots from a saved demonstration."""
    limit = _bounded_frame_count(max_frames)
    try:
        paths = sorted((recording_dir / "frames").glob("frame-*.jpg"))
    except OSError:
        return [], []
    if len(paths) > limit:
        if limit == 1:
            paths = paths[:1]
        else:
            indexes = sorted({
                round(i * (len(paths) - 1) / (limit - 1)) for i in range(limit)
            })
            paths = [paths[i] for i in indexes]

    images: list[str] = []
    offsets: list[int] = []
    for path in paths:
        try:
            if path.stat().st_size <= 0 or path.stat().st_size > MAX_FRAME_FILE_BYTES:
                continue
            data = path.read_bytes()
            if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
                continue
            images.append(base64.b64encode(data).decode("ascii"))
            try:
                offsets.append((int(path.stem.split("-")[-1]) + 1) * 3)
            except ValueError:
                offsets.append((len(offsets) + 1) * 3)
        except OSError:
            continue
    return images[:MAX_VIDEO_FRAMES], offsets[:MAX_VIDEO_FRAMES]


def _clean_event(event: object) -> dict | None:
    """Allowlist event fields and values before including them in a cloud request."""
    if not isinstance(event, dict):
        return None
    event_type = event.get("type")
    if event_type in ("key_down", "key_up"):
        key = event.get("key")
        if not isinstance(key, str) or key not in _ALLOWED_KEYS:
            return None
        clean = {"type": event_type, "key": key}
    elif event_type == "mouse_click":
        button = event.get("button")
        x, y = event.get("x"), event.get("y")
        if (
            not isinstance(button, str) or button not in _ALLOWED_BUTTONS
            or isinstance(x, bool) or isinstance(y, bool)
            or not isinstance(x, int) or not isinstance(y, int)
            or not (0 <= x <= 10000 and 0 <= y <= 10000)
        ):
            return None
        clean = {"type": event_type, "button": button, "x": x, "y": y}
    else:
        return None

    timestamp = event.get("t")
    if _is_finite_nonnegative_number(timestamp):
        clean["t"] = round(float(timestamp), 3)
    return clean


def analyze_recording(directory: str, provider: str, api_key: str, model: str) -> str:
    """Analyze at most 48 allowed input events and six small screenshots."""
    recording_dir = Path(directory)
    recording_file = recording_dir / "recording.json"
    if not recording_file.is_file():
        raise RuntimeError("The selected folder does not contain recording.json.")
    try:
        if recording_file.stat().st_size > MAX_RECORDING_FILE_BYTES:
            raise RuntimeError("This recording file is too large to analyze safely (12 MB limit).")
        payload = json.loads(recording_file.read_text(encoding="utf-8"))
    except RuntimeError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise RuntimeError("The recording file could not be read as valid UTF-8 JSON.") from None
    if not isinstance(payload, dict):
        raise RuntimeError("The recording file has an unsupported format.")

    all_events = payload.get("actions", [])
    if not isinstance(all_events, list):
        all_events = []
    if len(all_events) > MAX_RECORDING_EVENTS:
        indexes = sorted({
            round(i * (len(all_events) - 1) / (MAX_RECORDING_EVENTS - 1))
            for i in range(MAX_RECORDING_EVENTS)
        })
        events_to_review = [all_events[index] for index in indexes]
    else:
        events_to_review = all_events
    sampled = [clean for event in events_to_review if (clean := _clean_event(event)) is not None]

    images, frame_offsets = _sample_recording_frames(recording_dir)
    if not sampled and not images:
        raise RuntimeError("This recording contains no usable input events or screenshots.")

    duration = payload.get("duration_seconds", "unknown")
    if _is_finite_nonnegative_number(duration):
        duration_text = f"{float(duration):.2f}"
    else:
        duration_text = "unknown"
    action_count = payload.get("action_count", len(all_events))
    if isinstance(action_count, bool) or not isinstance(action_count, int) or action_count < 0:
        action_count = len(all_events)

    prompt = (
        "Review this user-provided gameplay demonstration. The JSON below contains a bounded sample of "
        "allowlisted keyboard/mouse events with timestamps in seconds. Screenshots are attached in chronological "
        f"order at approximate offsets (seconds): {json.dumps(frame_offsets)}.\n"
        "Describe only evidence-supported visible patterns, state changes, and uncertainties. A keypress or click "
        "does not prove the intended action succeeded. Do not invent unseen key presses, hidden mechanics, code, "
        "or executable automation instructions. Treat findings as observations for the user to review.\n\n"
        f"Duration: {duration_text} seconds. Total events: {action_count}.\n"
        f"Sampled events: {json.dumps(sampled, ensure_ascii=False)}\n"
        f"Attached screenshots: {len(images)}."
    )
    return ask_provider(provider, api_key, model, VIDEO_SYSTEM, prompt, images_b64=images)
