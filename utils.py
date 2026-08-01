"""
Shared utilities for safe webcam access and landmark handling.
"""

from __future__ import annotations

import cv2
import numpy as np
import pyautogui

# Number of landmarks MediaPipe provides per hand
HAND_LANDMARK_COUNT = 21

# Consecutive failed frame reads before treating the webcam as disconnected
MAX_FRAME_FAILURES = 30

# MediaPipe landmark IDs for fingertips and index joint
INDEX_TIP_ID = 8
INDEX_PIP_ID = 6
THUMB_TIP_ID = 4
MIDDLE_TIP_ID = 12

_pyautogui_configured = False


def configure_pyautogui() -> None:
    """Apply global pyautogui settings once for responsive input."""
    global _pyautogui_configured
    if not _pyautogui_configured:
        pyautogui.PAUSE = 0
        _pyautogui_configured = True


def open_webcam(camera_index: int = 0) -> cv2.VideoCapture | None:
    """
    Open the webcam and verify it can capture frames.

    Returns a VideoCapture object on success, or None with an error message.
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"Error: Cannot open webcam at index {camera_index}.")
        print("  • Ensure a camera is connected and not in use by another app.")
        print("  • Grant camera permission to your terminal or Python interpreter.")
        print("  • On macOS: System Settings → Privacy & Security → Camera.")
        return None

    success, test_frame = cap.read()
    if not success or test_frame is None or test_frame.size == 0:
        cap.release()
        print(f"Error: Webcam {camera_index} opened but failed to capture a test frame.")
        print("  • The camera may be disconnected or still initializing.")
        print("  • Try unplugging and reconnecting the camera.")
        return None

    return cap


def read_frame(cap: cv2.VideoCapture) -> np.ndarray | None:
    """
    Safely read a single frame from the webcam.

    Returns the frame array, or None if the read failed or the frame is empty.
    """
    success, frame = cap.read()
    if not success or frame is None or frame.size == 0:
        return None
    return frame


def release_camera(cap: cv2.VideoCapture | None) -> None:
    """Safely release a VideoCapture resource."""
    if cap is not None and cap.isOpened():
        cap.release()


def has_complete_landmarks(landmarks: list | None, required: int = HAND_LANDMARK_COUNT) -> bool:
    """Return True if landmarks contains the expected number of points."""
    return landmarks is not None and len(landmarks) >= required


def build_landmark_map(landmarks: list | None) -> dict[int, tuple[int, int]]:
    """
    Convert a landmark list into a dict for O(1) coordinate lookups.

    Call once per frame and reuse the map for all fingertip queries.
    """
    if not landmarks:
        return {}
    return {landmark_id: (int(x), int(y)) for landmark_id, x, y in landmarks}


def get_landmark(
    landmarks: list | None,
    landmark_id: int,
    landmark_map: dict[int, tuple[int, int]] | None = None,
) -> tuple[int, int] | None:
    """
    Safely return pixel coordinates for a MediaPipe landmark ID.

    Pass landmark_map when available to avoid rebuilding the dict each call.
    """
    if landmark_map is not None:
        return landmark_map.get(landmark_id)

    if not landmarks:
        return None

    for lid, x, y in landmarks:
        if lid == landmark_id:
            return int(x), int(y)

    return None


def get_fingertips(
    landmark_map: dict[int, tuple[int, int]],
) -> tuple[
    tuple[int, int] | None,
    tuple[int, int] | None,
    tuple[int, int] | None,
]:
    """Return (index_tip, thumb_tip, middle_tip) from a pre-built landmark map."""
    return (
        landmark_map.get(INDEX_TIP_ID),
        landmark_map.get(THUMB_TIP_ID),
        landmark_map.get(MIDDLE_TIP_ID),
    )


def get_index_track_point(
    landmark_map: dict[int, tuple[int, int]],
) -> tuple[int, int] | None:
    """
    Return a stable index-finger tracking point in pixel coordinates.

    Blends the fingertip (8) with the index PIP (6) so the marker stays
    glued to the visible finger while reducing MediaPipe tip jitter.
    """
    tip = landmark_map.get(INDEX_TIP_ID)
    pip = landmark_map.get(INDEX_PIP_ID)
    if tip is None:
        return None
    if pip is None:
        return tip
    return (
        int(tip[0] * 0.92 + pip[0] * 0.08),
        int(tip[1] * 0.92 + pip[1] * 0.08),
    )


def pinch_distance(
    thumb_tip: tuple[int, int],
    index_tip: tuple[int, int],
) -> float:
    """Return Euclidean distance in pixels between thumb and index fingertips."""
    return float(np.hypot(thumb_tip[0] - index_tip[0], thumb_tip[1] - index_tip[1]))
