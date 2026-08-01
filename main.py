from __future__ import annotations

"""
Virtual Mouse and Keyboard — main application entry point.

Captures webcam input and routes gestures to virtual mouse or keyboard modules.
Press M for Mouse Mode, K for Keyboard Mode, A for AI analysis, Q to quit.
"""

import sys

import cv2

from hand_tracker import HandTracker

try:
    from groq_analyzer import GroqGestureAnalyzer
except ImportError:
    GroqGestureAnalyzer = None  # type: ignore[misc, assignment]
from ui_overlay import ACCENT_GESTURE, draw_ai_insight, draw_notice, draw_status_hud
from utils import (
    build_landmark_map,
    configure_pyautogui,
    get_fingertips,
    get_index_track_point,
    has_complete_landmarks,
    open_webcam,
    pinch_distance,
    read_frame,
    release_camera,
    MAX_FRAME_FAILURES,
)
from virtual_keyboard import VirtualKeyboard
from virtual_mouse import VirtualMouse


def run_mouse_mode(frame, tracker, mouse, landmarks):
    """Handle virtual mouse gestures for the current frame."""
    frame = mouse.draw_active_area(frame)

    if not has_complete_landmarks(landmarks):
        mouse.reset_scroll_tracking()
        mouse.reset_smoothing()
        mouse.update_gesture(False, None, None, None, None)
        return frame

    lm_map = build_landmark_map(landmarks)
    index_tip, thumb_tip, middle_tip = get_fingertips(lm_map)
    track_point = get_index_track_point(lm_map) or index_tip
    fingers = tracker.fingersUp()
    mouse.update_gesture(True, fingers, track_point, thumb_tip, middle_tip)

    # Peace sign (index + middle up, ring + pinky down) → scroll
    if fingers and VirtualMouse.is_scrolling_mode(fingers) and track_point and middle_tip:
        mouse.handle_scroll((track_point[1] + middle_tip[1]) // 2)
        return mouse.draw_scrolling_feedback(frame, track_point, middle_tip)

    if track_point and thumb_tip and fingers:
        mouse.reset_scroll_tracking()
        mouse.sync_finger(*track_point)
        mouse.handle_pinch_click(thumb_tip, track_point)
        frame = mouse.draw_pinch_feedback(frame, thumb_tip, track_point)
        mouse.draw_finger_cursor(frame, track_point)

        # Index finger up (not peace-sign) inside purple zone → move cursor
        if (
            not mouse.is_pinching
            and VirtualMouse.is_cursor_gesture(fingers)
            and mouse.is_inside_active_area(*track_point)
        ):
            mouse.move_cursor(*track_point)
        return frame

    mouse.reset_scroll_tracking()
    return frame


def run_keyboard_mode(frame, keyboard, landmarks):
    """Handle virtual keyboard hover and pinch-to-type for the current frame."""
    if not has_complete_landmarks(landmarks):
        keyboard.update_hover(-1, -1)
        keyboard.update_gesture(None)
        return keyboard.draw(frame, finger_pos=None)

    index_tip, thumb_tip, _ = get_fingertips(build_landmark_map(landmarks))

    if index_tip:
        keyboard.update_hover(index_tip[0], index_tip[1])
    else:
        keyboard.update_hover(-1, -1)

    if index_tip and thumb_tip:
        keyboard.handle_pinch_type(thumb_tip, index_tip)
        frame = keyboard.draw_pinch_feedback(frame, thumb_tip, index_tip)

    keyboard.update_gesture(index_tip)
    return keyboard.draw(frame, finger_pos=index_tip)


def _parse_camera_index() -> int:
    """Parse optional camera index from command line (defaults to 0)."""
    if len(sys.argv) < 2:
        return 0
    try:
        return int(sys.argv[1])
    except ValueError:
        print(f"Warning: Invalid camera index '{sys.argv[1]}', using camera 0.")
        return 0


def _build_gesture_snapshot(analyzer, mode, tracker, keyboard, landmarks, rule_gesture):
    """Build a compact snapshot for Groq AI analysis."""
    fingers = tracker.fingersUp() if has_complete_landmarks(landmarks) else None
    lm_map = build_landmark_map(landmarks) if landmarks else {}
    index_tip, thumb_tip, _ = get_fingertips(lm_map)

    pinch_dist = None
    if index_tip and thumb_tip:
        pinch_dist = pinch_distance(thumb_tip, index_tip)

    hovered_key = keyboard.hovered_key.label if keyboard.hovered_key else None

    return analyzer.build_snapshot(
        mode=mode,
        landmarks=landmarks,
        fingers=fingers,
        pinch_distance=pinch_dist,
        index_tip=index_tip,
        rule_gesture=rule_gesture,
        hovered_key=hovered_key,
    )


def main() -> None:
    camera_index = _parse_camera_index()
    configure_pyautogui()

    cap = open_webcam(camera_index)
    if cap is None:
        sys.exit(1)

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if frame_width <= 0 or frame_height <= 0:
        print("Error: Webcam returned invalid frame dimensions.")
        release_camera(cap)
        sys.exit(1)

    tracker = HandTracker()
    mouse = VirtualMouse(frame_width, frame_height)
    keyboard = VirtualKeyboard(frame_width, frame_height)
    ai_analyzer = GroqGestureAnalyzer(min_interval=4.0) if GroqGestureAnalyzer else None
    mode = "mouse"
    frame_failures = 0
    ai_auto_analyze = True

    print("Virtual Mouse & Keyboard started.")
    print("  M = Mouse Mode   K = Keyboard Mode   A = AI Analyze   Q = Quit")

    if ai_analyzer and ai_analyzer.is_enabled:
        print("  Groq AI gesture analysis: ENABLED")
    elif ai_analyzer:
        print(f"  Groq AI: disabled — {ai_analyzer.error_message}")
    else:
        print("  Groq AI: disabled — pip install groq python-dotenv")

    try:
        while True:
            frame = read_frame(cap)
            if frame is None:
                frame_failures += 1
                if frame_failures >= MAX_FRAME_FAILURES:
                    print(
                        f"Error: Lost webcam connection after {MAX_FRAME_FAILURES} "
                        "consecutive read failures."
                    )
                    break
                continue
            frame_failures = 0

            frame = cv2.flip(frame, 1)
            frame, landmarks = tracker.findHands(frame, draw=True)

            if mode == "mouse":
                frame = run_mouse_mode(frame, tracker, mouse, landmarks)
                gesture = mouse.active_gesture
            else:
                frame = run_keyboard_mode(frame, keyboard, landmarks)
                gesture = keyboard.active_gesture

            draw_status_hud(frame, mode, gesture)

            if not landmarks:
                draw_notice(frame, "Show your hand to the camera to begin controlling.", ACCENT_GESTURE)
            elif not has_complete_landmarks(landmarks):
                draw_notice(frame, "Partial hand detected — hold your hand fully in view.", (100, 180, 255))

            # Groq AI: auto-analyze every few seconds
            if ai_analyzer and ai_analyzer.is_enabled and ai_auto_analyze:
                snapshot = _build_gesture_snapshot(ai_analyzer, mode, tracker, keyboard, landmarks, gesture)
                ai_analyzer.request_analysis(snapshot)

            if ai_analyzer:
                draw_ai_insight(
                    frame,
                    ai_analyzer.get_insight(),
                    enabled=ai_analyzer.is_enabled,
                    error=ai_analyzer.error_message,
                )

            cv2.imshow("Virtual Mouse & Keyboard", frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q")):
                break
            if key in (ord("m"), ord("M")):
                mode = "mouse"
                keyboard.is_pinching = False
                mouse.reset_smoothing()
            elif key in (ord("k"), ord("K")):
                mode = "keyboard"
                mouse.reset_scroll_tracking()
            elif key in (ord("a"), ord("A")):
                if ai_analyzer and ai_analyzer.is_enabled:
                    snapshot = _build_gesture_snapshot(ai_analyzer, mode, tracker, keyboard, landmarks, gesture)
                    if ai_analyzer.request_analysis(snapshot, force=True):
                        print("AI analysis requested...")
                elif ai_analyzer:
                    print(f"AI unavailable: {ai_analyzer.error_message}")
                else:
                    print("AI unavailable: pip install groq python-dotenv")

    except KeyboardInterrupt:
        print("\nInterrupted — shutting down.")
    finally:
        tracker.release()
        release_camera(cap)
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
