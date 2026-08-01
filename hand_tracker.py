from __future__ import annotations

"""
Hand tracking module using OpenCV and MediaPipe Hands.

Detects a single hand from webcam frames, draws landmarks,
and returns landmark positions as (id, x, y) tuples.
"""

import cv2
import mediapipe as mp

from utils import HAND_LANDMARK_COUNT

# Landmark IDs required for finger-state detection
_FINGER_LANDMARK_IDS = frozenset({3, 4, 6, 8, 10, 12, 14, 16, 18, 20})


class HandTracker:
    """Detects one hand per frame and exposes landmark drawing and position lookup."""

    def __init__(self, detection_confidence: float = 0.7, tracking_confidence: float = 0.7):
        self.mp_draw = mp.solutions.drawing_utils
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=detection_confidence,
            min_tracking_confidence=tracking_confidence,
        )

        self.landmark_list: list[tuple[int, int, int]] = []
        self.landmark_map: dict[int, tuple[int, int]] = {}
        self.hand_type: str | None = None

    def findHands(self, frame, draw: bool = True):
        """
        Detect a hand in the given BGR frame and optionally draw landmarks.

        Returns:
            The (possibly annotated) frame and a list of (id, x, y) tuples.
            Returns an empty list when no hand is found.
        """
        self.landmark_list = []
        self.landmark_map = {}
        self.hand_type = None

        if frame is None or frame.size == 0:
            return frame, []

        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb_frame)
        except Exception as exc:
            print(f"Warning: Hand detection failed this frame — {exc}")
            return frame, []

        if not results.multi_hand_landmarks:
            return frame, []

        hand_landmarks = results.multi_hand_landmarks[0]

        if results.multi_handedness:
            self.hand_type = results.multi_handedness[0].classification[0].label

        height, width, _ = frame.shape

        if draw:
            self.mp_draw.draw_landmarks(
                frame,
                hand_landmarks,
                self.mp_hands.HAND_CONNECTIONS,
            )

        for landmark_id, landmark in enumerate(hand_landmarks.landmark):
            x, y = int(landmark.x * width), int(landmark.y * height)
            self.landmark_list.append((landmark_id, x, y))
            self.landmark_map[landmark_id] = (x, y)

        return frame, self.landmark_list

    def findPosition(self, frame, hand_no: int = 0, draw: bool = True):
        """Return landmark positions, optionally drawing circles on each point."""
        if not self.landmark_list:
            return []

        if draw:
            for _, x, y in self.landmark_list:
                cv2.circle(frame, (x, y), 8, (0, 255, 0), cv2.FILLED)

        return self.landmark_list

    def fingersUp(self) -> list[bool]:
        """
        Determine which fingers are raised.

        Returns [Thumb, Index, Middle, Ring, Pinky] booleans.
        """
        if len(self.landmark_list) != HAND_LANDMARK_COUNT:
            return [False] * 5

        landmarks = self.landmark_map
        if not _FINGER_LANDMARK_IDS.issubset(landmarks.keys()):
            return [False] * 5

        fingers: list[bool] = []

        thumb_tip_x = landmarks[4][0]
        thumb_ip_x = landmarks[3][0]
        if self.hand_type == "Right":
            fingers.append(thumb_tip_x > thumb_ip_x)
        elif self.hand_type == "Left":
            fingers.append(thumb_tip_x < thumb_ip_x)
        else:
            fingers.append(thumb_tip_x > thumb_ip_x)

        for tip_id, pip_id in ((8, 6), (12, 10), (16, 14), (20, 18)):
            fingers.append(landmarks[tip_id][1] < landmarks[pip_id][1])

        return fingers

    def release(self) -> None:
        """Release MediaPipe resources."""
        self.hands.close()
