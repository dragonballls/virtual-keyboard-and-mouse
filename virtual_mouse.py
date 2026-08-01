from __future__ import annotations

"""
Virtual mouse controller using hand tracking.

Maps the index fingertip position inside a defined active area
to system cursor movement with smoothing. Pinch gesture triggers clicks.
"""

import time
from collections import deque

import cv2
import numpy as np
import pyautogui

from ui_overlay import draw_click_ripple
from utils import pinch_distance


class VirtualMouse:
    """Maps index-finger position within an active area to smooth screen cursor movement."""

    def __init__(
        self,
        frame_width: int,
        frame_height: int,
        cursor_ema_alpha: float = 0.72,
        movement_threshold: float = 45.0,
        pinch_on_threshold: float = 38.0,
        pinch_off_threshold: float = 52.0,
        click_cooldown: float = 0.5,
        snap_threshold: float = 90.0,
    ):
        self.screen_width, self.screen_height = pyautogui.size()
        self.cursor_ema_alpha = cursor_ema_alpha
        self.movement_threshold = movement_threshold
        self.pinch_on_threshold = pinch_on_threshold
        self.pinch_off_threshold = pinch_off_threshold
        self.click_cooldown = click_cooldown
        self.snap_threshold = snap_threshold

        # Raw finger position — used for on-screen marker (no lag)
        self.tracking_point: tuple[int, int] | None = None

        # Light smoothing for cursor mapping only (not for display)
        self._map_x: float | None = None
        self._map_y: float | None = None

        self._cursor_x = self.screen_width / 2
        self._cursor_y = self.screen_height / 2

        self._pinch_dist_buffer: deque[float] = deque(maxlen=5)

        self.last_click_time = 0.0
        self.is_pinching = False
        self.click_anim_start = 0.0
        self.click_anim_pos: tuple[int, int] | None = None
        self.active_gesture = "No Hand Detected"

        self.prev_scroll_y: int | None = None
        self.scroll_threshold = 4
        self.scroll_speed = 3
        self.last_scroll_direction = 0

        margin_x = int(frame_width * 0.10)
        margin_y = int(frame_height * 0.10)
        self.active_area = (
            margin_x,
            margin_y,
            frame_width - margin_x,
            frame_height - margin_y,
        )

    def draw_active_area(self, frame) -> np.ndarray:
        """Draw a rectangle marking the cursor control zone."""
        x1, y1, x2, y2 = self.active_area
        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 0, 255), 2)
        cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
        cv2.putText(
            frame,
            "Cursor Zone",
            (x1 + 8, y1 + 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 0, 255),
            2,
        )
        return frame

    def sync_finger(self, finger_x: int, finger_y: int) -> tuple[int, int]:
        """
        Update tracking every frame so the on-screen marker follows the finger.

        Returns the raw tracking point used for drawing.
        """
        self.tracking_point = (finger_x, finger_y)

        if self._map_x is None or self._map_y is None:
            self._map_x = float(finger_x)
            self._map_y = float(finger_y)
        else:
            jump = float(np.hypot(finger_x - self._map_x, finger_y - self._map_y))
            if jump > self.snap_threshold:
                # Hand re-entered frame — snap instead of drifting
                self._map_x = float(finger_x)
                self._map_y = float(finger_y)
            else:
                a = self.cursor_ema_alpha
                self._map_x = a * finger_x + (1.0 - a) * self._map_x
                self._map_y = a * finger_y + (1.0 - a) * self._map_y

        return self.tracking_point

    def _map_to_screen(self, x: float, y: float) -> tuple[int, int]:
        """Map webcam coordinates inside the active area to screen coordinates."""
        x1, y1, x2, y2 = self.active_area
        clamped_x = float(np.clip(x, x1, x2))
        clamped_y = float(np.clip(y, y1, y2))
        screen_x = int(np.interp(clamped_x, [x1, x2], [0, self.screen_width]))
        screen_y = int(np.interp(clamped_y, [y1, y2], [0, self.screen_height]))
        return screen_x, screen_y

    def _adaptive_cursor_ema(self, screen_x: int, screen_y: int) -> tuple[int, int]:
        """Final cursor smoothing — fast when moving, steady when still."""
        distance = float(np.hypot(screen_x - self._cursor_x, screen_y - self._cursor_y))
        blend = np.clip(distance / self.movement_threshold, 0.0, 1.0)
        alpha = 0.55 + blend * 0.40  # 0.55 still → 0.95 fast

        self._cursor_x = alpha * screen_x + (1.0 - alpha) * self._cursor_x
        self._cursor_y = alpha * screen_y + (1.0 - alpha) * self._cursor_y
        return int(self._cursor_x), int(self._cursor_y)

    def move_cursor(self, finger_x: int, finger_y: int) -> None:
        """Move the system cursor. Display uses raw finger; cursor uses light smoothing."""
        self.sync_finger(finger_x, finger_y)
        if self._map_x is None or self._map_y is None:
            return

        screen_x, screen_y = self._map_to_screen(self._map_x, self._map_y)
        smooth_x, smooth_y = self._adaptive_cursor_ema(screen_x, screen_y)
        pyautogui.moveTo(smooth_x, smooth_y, _pause=False)

    def reset_smoothing(self) -> None:
        """Reset smoothing state when hand leaves frame or mode changes."""
        self.tracking_point = None
        self._map_x = None
        self._map_y = None
        self._pinch_dist_buffer.clear()
        self._cursor_x = self.screen_width / 2
        self._cursor_y = self.screen_height / 2

    def is_inside_active_area(self, x: int, y: int) -> bool:
        x1, y1, x2, y2 = self.active_area
        return x1 <= x <= x2 and y1 <= y <= y2

    @staticmethod
    def is_cursor_gesture(fingers: list[bool]) -> bool:
        if len(fingers) < 3:
            return False
        return fingers[1] and not VirtualMouse.is_scrolling_mode(fingers)

    @staticmethod
    def is_scrolling_mode(fingers: list[bool]) -> bool:
        if len(fingers) < 5:
            return False
        return fingers[1] and fingers[2] and not fingers[3] and not fingers[4]

    def _smooth_pinch_distance(self, thumb_tip: tuple[int, int], index_tip: tuple[int, int]) -> float:
        raw = pinch_distance(thumb_tip, index_tip)
        self._pinch_dist_buffer.append(raw)
        return float(np.mean(self._pinch_dist_buffer))

    def _is_pinching_now(self, distance: float) -> bool:
        if self.is_pinching:
            return distance < self.pinch_off_threshold
        return distance < self.pinch_on_threshold

    def handle_pinch_click(
        self,
        thumb_tip: tuple[int, int],
        index_tip: tuple[int, int],
    ) -> bool:
        distance = self._smooth_pinch_distance(thumb_tip, index_tip)
        pinching = self._is_pinching_now(distance)
        clicked = False
        current_time = time.time()

        if pinching and not self.is_pinching:
            if current_time - self.last_click_time >= self.click_cooldown:
                pyautogui.click()
                self.last_click_time = current_time
                self.click_anim_start = current_time
                self.click_anim_pos = index_tip
                clicked = True

        self.is_pinching = pinching
        return clicked

    def draw_pinch_feedback(self, frame, thumb_tip: tuple[int, int], index_tip: tuple[int, int]):
        distance = int(self._smooth_pinch_distance(thumb_tip, index_tip))
        pinching = self.is_pinching

        thumb_color = (0, 0, 255) if pinching else (255, 0, 0)
        index_color = (0, 0, 255) if pinching else (0, 255, 0)

        cv2.circle(frame, thumb_tip, 10, thumb_color, cv2.FILLED)
        cv2.circle(frame, index_tip, 10, index_color, cv2.FILLED)
        cv2.line(frame, thumb_tip, index_tip, (0, 0, 255) if pinching else (180, 180, 180), 2)

        mid_x = (thumb_tip[0] + index_tip[0]) // 2
        mid_y = (thumb_tip[1] + index_tip[1]) // 2
        cv2.putText(
            frame, f"{distance}px", (mid_x - 20, mid_y - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1,
        )

        if self.click_anim_pos:
            draw_click_ripple(frame, self.click_anim_pos, self.click_anim_start)
        return frame

    def draw_finger_cursor(self, frame, index_tip: tuple[int, int]) -> None:
        """Draw marker locked to the raw index finger position."""
        tip = self.tracking_point if self.tracking_point else index_tip
        in_zone = self.is_inside_active_area(*tip)
        color = (0, 255, 255) if in_zone else (0, 140, 255)

        # Crosshair on exact fingertip
        cv2.drawMarker(frame, tip, color, cv2.MARKER_CROSS, 18, 2)
        cv2.circle(frame, tip, 6, color, cv2.FILLED)
        cv2.circle(frame, tip, 14, color, 1)

    def update_gesture(
        self,
        has_hand: bool,
        fingers: list[bool] | None,
        index_tip: tuple[int, int] | None,
        thumb_tip: tuple[int, int] | None,
        middle_tip: tuple[int, int] | None,
    ) -> None:
        tip = self.tracking_point or index_tip
        if not has_hand or not tip:
            self.active_gesture = "No Hand Detected"
        elif fingers and self.is_scrolling_mode(fingers):
            direction = {1: "↑", -1: "↓"}.get(self.last_scroll_direction, "")
            self.active_gesture = f"Scrolling {direction}".strip() or "Scrolling"
        elif self.is_pinching:
            self.active_gesture = "Pinch to Click"
        elif fingers and self.is_cursor_gesture(fingers):
            if self.is_inside_active_area(*tip):
                self.active_gesture = "Moving Cursor"
            else:
                self.active_gesture = "Move finger into Cursor Zone"
        else:
            self.active_gesture = "Raise index finger to move"

    def reset_scroll_tracking(self) -> None:
        self.prev_scroll_y = None
        self.last_scroll_direction = 0

    def handle_scroll(self, hand_y: int) -> None:
        if self.prev_scroll_y is None:
            self.prev_scroll_y = hand_y
            return

        delta_y = hand_y - self.prev_scroll_y
        self.prev_scroll_y = hand_y

        if delta_y < -self.scroll_threshold:
            pyautogui.scroll(self.scroll_speed)
            self.last_scroll_direction = 1
        elif delta_y > self.scroll_threshold:
            pyautogui.scroll(-self.scroll_speed)
            self.last_scroll_direction = -1

    def draw_scrolling_feedback(self, frame, index_tip: tuple[int, int], middle_tip: tuple[int, int]):
        cv2.circle(frame, index_tip, 10, (80, 180, 255), cv2.FILLED)
        cv2.circle(frame, middle_tip, 10, (80, 180, 255), cv2.FILLED)
        cv2.putText(
            frame, "Scroll: move hand up/down", (10, 175),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 180, 255), 1,
        )

        cx = frame.shape[1] // 2
        if self.last_scroll_direction == 1:
            cv2.arrowedLine(frame, (cx, 130), (cx, 90), (90, 210, 90), 3, tipLength=0.35)
        elif self.last_scroll_direction == -1:
            cv2.arrowedLine(frame, (cx, 90), (cx, 130), (80, 80, 220), 3, tipLength=0.35)
        return frame


def main():
    from hand_tracker import HandTracker
    from utils import (
        build_landmark_map,
        configure_pyautogui,
        get_fingertips,
        get_index_track_point,
        has_complete_landmarks,
        open_webcam,
        read_frame,
        release_camera,
        MAX_FRAME_FAILURES,
    )

    configure_pyautogui()
    cap = open_webcam(0)
    if cap is None:
        return

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    tracker = HandTracker()
    mouse = VirtualMouse(frame_width, int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    frame_failures = 0

    print("Virtual Mouse started. Press Q to quit.")

    try:
        while True:
            frame = read_frame(cap)
            if frame is None:
                frame_failures += 1
                if frame_failures >= MAX_FRAME_FAILURES:
                    break
                continue
            frame_failures = 0

            frame = cv2.flip(frame, 1)
            frame, landmarks = tracker.findHands(frame, draw=True)
            frame = mouse.draw_active_area(frame)

            if has_complete_landmarks(landmarks):
                lm_map = build_landmark_map(landmarks)
                index_tip, thumb_tip, middle_tip = get_fingertips(lm_map)
                track_point = get_index_track_point(lm_map) or index_tip
                fingers = tracker.fingersUp()
                mouse.update_gesture(True, fingers, track_point, thumb_tip, middle_tip)

                if fingers and VirtualMouse.is_scrolling_mode(fingers) and track_point and middle_tip:
                    mouse.handle_scroll((track_point[1] + middle_tip[1]) // 2)
                    frame = mouse.draw_scrolling_feedback(frame, track_point, middle_tip)
                elif track_point and thumb_tip and fingers:
                    mouse.reset_scroll_tracking()
                    mouse.sync_finger(*track_point)
                    mouse.handle_pinch_click(thumb_tip, track_point)
                    frame = mouse.draw_pinch_feedback(frame, thumb_tip, track_point)
                    mouse.draw_finger_cursor(frame, track_point)

                    if (
                        not mouse.is_pinching
                        and VirtualMouse.is_cursor_gesture(fingers)
                        and mouse.is_inside_active_area(*track_point)
                    ):
                        mouse.move_cursor(*track_point)
            else:
                mouse.reset_scroll_tracking()
                mouse.reset_smoothing()
                mouse.update_gesture(False, None, None, None, None)

            cv2.imshow("Virtual Mouse", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q")):
                break
    finally:
        tracker.release()
        release_camera(cap)
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
