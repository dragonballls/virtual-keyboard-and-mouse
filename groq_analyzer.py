"""
AI gesture analysis using the Groq API.

Sends compact hand-gesture snapshots to an LLM for interpretation.
Runs in a background thread so the webcam loop stays responsive.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Supported gesture labels the model should return
VALID_GESTURES = {
    "move_cursor",
    "pinch_click",
    "scroll_up",
    "scroll_down",
    "hover_key",
    "pinch_type",
    "idle",
    "no_hand",
    "uncertain",
}

SYSTEM_PROMPT = """You are a real-time hand-gesture analyst for a virtual mouse and keyboard app.

Given JSON snapshot data (finger states, pinch distance, mode, rule-based guess), respond with ONLY valid JSON:
{
  "gesture": "<one of: move_cursor, pinch_click, scroll_up, scroll_down, hover_key, pinch_type, idle, no_hand, uncertain>",
  "confidence": <0.0 to 1.0>,
  "action": "<short recommended action>",
  "explanation": "<one concise sentence>"
}

Rules:
- pinch_distance_px < 40 with thumb+index close → likely pinch_click or pinch_type (depends on mode)
- index+middle up in mouse mode → scroll_up or scroll_down based on hand movement hint
- index up alone in mouse mode inside active area → move_cursor
- index over key in keyboard mode → hover_key
- no landmarks → no_hand
- Be brief. JSON only, no markdown."""


class GroqGestureAnalyzer:
    """Analyzes hand gesture snapshots via Groq in a background thread."""

    def __init__(self, model: str = "llama-3.3-70b-versatile", min_interval: float = 4.0):
        self.model = model
        self.min_interval = min_interval
        self._client = None
        self._enabled = False
        self._last_request_time = 0.0
        self._lock = threading.Lock()
        self._pending = False
        self._latest_insight: dict[str, Any] = {
            "gesture": "idle",
            "confidence": 0.0,
            "action": "Waiting for analysis",
            "explanation": "Press A to analyze gesture with AI",
        }
        self._error: str | None = None
        self._init_client()

    def _init_client(self) -> None:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key or api_key == "your_groq_api_key_here":
            self._error = "GROQ_API_KEY not set. Copy .env.example to .env and add your key."
            return

        try:
            from groq import Groq

            self._client = Groq(api_key=api_key)
            self._enabled = True
        except ImportError:
            self._error = "groq package not installed. Run: pip install groq python-dotenv"
        except Exception as exc:
            self._error = f"Groq init failed: {exc}"

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def error_message(self) -> str | None:
        return self._error

    def get_insight(self) -> dict[str, Any]:
        """Return the most recent AI analysis result."""
        with self._lock:
            return dict(self._latest_insight)

    def build_snapshot(
        self,
        mode: str,
        landmarks: list | None,
        fingers: list[bool] | None,
        pinch_distance: float | None,
        index_tip: tuple[int, int] | None,
        rule_gesture: str,
        hovered_key: str | None = None,
    ) -> dict[str, Any]:
        """Build a compact gesture snapshot for the LLM."""
        return {
            "mode": mode,
            "landmark_count": len(landmarks) if landmarks else 0,
            "fingers_up": {
                "thumb": fingers[0] if fingers and len(fingers) > 0 else False,
                "index": fingers[1] if fingers and len(fingers) > 1 else False,
                "middle": fingers[2] if fingers and len(fingers) > 2 else False,
                "ring": fingers[3] if fingers and len(fingers) > 3 else False,
                "pinky": fingers[4] if fingers and len(fingers) > 4 else False,
            },
            "pinch_distance_px": round(pinch_distance, 1) if pinch_distance is not None else None,
            "index_tip": list(index_tip) if index_tip else None,
            "hovered_key": hovered_key,
            "rule_based_gesture": rule_gesture,
        }

    def request_analysis(self, snapshot: dict[str, Any], force: bool = False) -> bool:
        """
        Queue an AI analysis request (non-blocking).

        Returns True if a new request was queued, False if rate-limited or disabled.
        """
        if not self._enabled or self._client is None:
            return False

        now = time.time()
        if not force and (now - self._last_request_time) < self.min_interval:
            return False

        with self._lock:
            if self._pending:
                return False
            self._pending = True
            self._last_request_time = now

        thread = threading.Thread(target=self._run_analysis, args=(snapshot,), daemon=True)
        thread.start()
        return True

    def _run_analysis(self, snapshot: dict[str, Any]) -> None:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Analyze this hand gesture snapshot:\n{json.dumps(snapshot)}",
                    },
                ],
                temperature=0.1,
                max_tokens=200,
            )
            raw = response.choices[0].message.content or ""
            parsed = self._parse_response(raw)
            with self._lock:
                self._latest_insight = parsed
                self._error = None
        except Exception as exc:
            with self._lock:
                self._error = f"Groq API error: {exc}"
        finally:
            with self._lock:
                self._pending = False

    def _parse_response(self, raw: str) -> dict[str, Any]:
        """Extract JSON from the model response."""
        raw = raw.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
            if not match:
                return {
                    "gesture": "uncertain",
                    "confidence": 0.0,
                    "action": "Parse error",
                    "explanation": raw[:120] or "Empty AI response",
                }
            data = json.loads(match.group())

        gesture = str(data.get("gesture", "uncertain")).lower()
        if gesture not in VALID_GESTURES:
            gesture = "uncertain"

        return {
            "gesture": gesture,
            "confidence": float(data.get("confidence", 0.5)),
            "action": str(data.get("action", "No action"))[:60],
            "explanation": str(data.get("explanation", ""))[:120],
        }
