"""Focus-gated input and screenshot demonstration recorder.

Only a narrow allowlist of game keys is captured; arbitrary typed text is ignored.
This module records demonstrations but deliberately does not replay them.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

_ALLOWED_CHARS = set("wasdqe zxcvfr12345")
_SPECIAL_KEYS = {
    "Key.space": "space",
    "Key.shift": "shift",
    "Key.shift_r": "shift",
    "Key.esc": "esc",
    "Key.tab": "tab",
}
MOUSE_BUTTONS = {"Button.left": "left", "Button.right": "right", "Button.middle": "middle"}


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        path = Path(base) / "BloxFruitsMasteryAssistant"
    else:
        path = Path.home() / ".local" / "share" / "BloxFruitsMasteryAssistant"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _foreground_window() -> tuple[str, tuple[int, int, int, int] | None]:
    if os.name != "nt":
        return "", None
    try:
        import win32gui  # type: ignore
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd) or ""
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        if right <= left or bottom <= top:
            return title, None
        return title, (left, top, right - left, bottom - top)
    except Exception:
        return "", None


def roblox_is_foreground() -> bool:
    title, _ = _foreground_window()
    return "roblox" in title.casefold()


def _key_name(key: Any) -> str | None:
    special = str(key)
    if special in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[special]
    char = getattr(key, "char", None)
    if isinstance(char, str) and len(char) == 1 and char.casefold() in _ALLOWED_CHARS:
        return char.casefold()
    return None


class ActionRecorder:
    def __init__(self) -> None:
        self._keyboard_listener = None
        self._mouse_listener = None
        self._stop_event = threading.Event()
        self._capture_thread: threading.Thread | None = None
        self._start_time = 0.0
        self._actions: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self.output_dir: Path | None = None
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def action_count(self) -> int:
        with self._lock:
            return len(self._actions)

    def start(self) -> Path:
        if self._active:
            raise RuntimeError("Recording is already active.")
        if os.name != "nt":
            raise RuntimeError("The focused-window recorder currently supports Windows only.")
        if not roblox_is_foreground():
            raise RuntimeError("Focus the Roblox game window before starting a recording.")
        try:
            from pynput import keyboard, mouse
        except ImportError as exc:
            raise RuntimeError("Install the requirements first: " + str(exc)) from exc

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.output_dir = app_data_dir() / "recordings" / f"demo-{stamp}"
        self.output_dir.mkdir(parents=True, exist_ok=False)
        self._actions = []
        self._start_time = time.monotonic()
        self._stop_event.clear()
        self._active = True

        self._keyboard_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        self._mouse_listener = mouse.Listener(on_click=self._on_mouse_click)
        self._keyboard_listener.start()
        self._mouse_listener.start()
        self._capture_thread = threading.Thread(target=self._capture_loop, name="mfa-screenshots", daemon=True)
        self._capture_thread.start()
        return self.output_dir

    def _record(self, event: dict[str, Any]) -> None:
        if not self._active or not roblox_is_foreground():
            return
        event["t"] = round(time.monotonic() - self._start_time, 3)
        with self._lock:
            self._actions.append(event)

    def _on_key_press(self, key: Any) -> None:
        name = _key_name(key)
        if name:
            self._record({"type": "key_down", "key": name})

    def _on_key_release(self, key: Any) -> None:
        name = _key_name(key)
        if name:
            self._record({"type": "key_up", "key": name})

    def _on_mouse_click(self, x: int, y: int, button: Any, pressed: bool) -> None:
        if not pressed or not roblox_is_foreground():
            return
        name = MOUSE_BUTTONS.get(str(button))
        if not name:
            return
        _, rect = _foreground_window()
        if rect is None:
            return
        left, top, width, height = rect
        rel_x, rel_y = int(x - left), int(y - top)
        if 0 <= rel_x < width and 0 <= rel_y < height:
            self._record({"type": "mouse_click", "button": name, "x": rel_x, "y": rel_y})

    def _capture_loop(self) -> None:
        try:
            import mss
            from PIL import Image
        except ImportError:
            return
        shot_dir = self.output_dir / "frames" if self.output_dir else None
        if shot_dir is None:
            return
        shot_dir.mkdir(parents=True, exist_ok=True)
        frame_number = 0
        with mss.mss() as capture:
            while not self._stop_event.wait(3.0):
                title, rect = _foreground_window()
                if "roblox" not in title.casefold() or rect is None:
                    continue
                left, top, width, height = rect
                try:
                    frame = capture.grab({"left": left, "top": top, "width": width, "height": height})
                    image = Image.frombytes("RGB", frame.size, frame.rgb)
                    image.thumbnail((640, 360))
                    image.save(shot_dir / f"frame-{frame_number:04d}.jpg", "JPEG", quality=62, optimize=True)
                    frame_number += 1
                except Exception:
                    continue

    def stop(self) -> dict[str, Any]:
        if not self._active:
            raise RuntimeError("No recording is active.")
        self._active = False
        self._stop_event.set()
        for listener in (self._keyboard_listener, self._mouse_listener):
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=4)
        with self._lock:
            actions = list(self._actions)
        elapsed = max(0.0, time.monotonic() - self._start_time)
        result = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "duration_seconds": round(elapsed, 2),
            "action_count": len(actions),
            "actions": actions,
            "notes": "Input actions and sampled screenshots are demonstrations only; this build does not replay inputs.",
        }
        if self.output_dir is None:
            raise RuntimeError("Recording directory was lost.")
        (self.output_dir / "recording.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return {"directory": str(self.output_dir), **{k: result[k] for k in ("duration_seconds", "action_count")}}
