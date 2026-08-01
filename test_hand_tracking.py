from __future__ import annotations

"""
Test script for real-time hand tracking using HandTracker.

Opens the webcam, detects hand landmarks, displays FPS, and exits on Q.
"""

import time

import cv2

from hand_tracker import HandTracker
from utils import has_complete_landmarks, open_webcam, read_frame, release_camera, MAX_FRAME_FAILURES


def main():
    cap = open_webcam(0)
    if cap is None:
        return

    tracker = HandTracker()
    prev_time = 0
    frame_failures = 0

    print("Hand tracking test started. Press Q to quit.")

    try:
        while True:
            frame = read_frame(cap)
            if frame is None:
                frame_failures += 1
                if frame_failures >= MAX_FRAME_FAILURES:
                    print("Error: Lost connection to webcam after repeated read failures.")
                    break
                continue
            frame_failures = 0

            frame = cv2.flip(frame, 1)
            frame, landmarks = tracker.findHands(frame, draw=True)

            current_time = time.time()
            if prev_time > 0:
                fps = 1 / (current_time - prev_time)
                cv2.putText(
                    frame,
                    f"FPS: {int(fps)}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2,
                )
            prev_time = current_time

            if has_complete_landmarks(landmarks):
                cv2.putText(
                    frame,
                    f"Landmarks: {len(landmarks)}",
                    (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
                    2,
                )
            else:
                cv2.putText(
                    frame,
                    "No hand detected — show your hand to the camera",
                    (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (120, 120, 255),
                    2,
                )

            cv2.imshow("Hand Tracking Test", frame)

            if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q")):
                break
    finally:
        tracker.release()
        release_camera(cap)
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
