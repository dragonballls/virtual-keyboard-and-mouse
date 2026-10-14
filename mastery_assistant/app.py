"""Tkinter UI for the first Blox Fruits Mastery Assistant milestone."""
from __future__ import annotations

import json
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

import keyring

from providers import PROVIDERS, DEFAULT_MODELS, SERVICE_NAMES, ask_provider
from recorder import ActionRecorder, app_data_dir, roblox_is_foreground
from knowledge_store import list_references, load_reference_context, save_reference
from routine import TARGETS, build_review, compose_ai_request
from video_learning import analyze_video, analyze_recording

APP_TITLE = "Blox Fruits Mastery Assistant"
SYSTEM_PROMPT = (
    "You help users review a proposed routine for an ordinary keyboard/mouse game macro. "
    "Give a concise plan and uncertainty notes only. Never output code, shell commands, or executable tool calls. "
    "Do not authorize movement, choose a conflicting mastery target, or claim that a routine is ready. "
    "Do not override emergency-stop, focus checks, user permissions, or the local plan's explicit restrictions. "
    "Your response is advisory; the local app remains authoritative."
)


class MasteryApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE + " — Prototype")
        self.root.geometry("990x820")
        self.root.minsize(820, 650)
        self.recorder = ActionRecorder()
        self.recording_armed = False
        self._last_hotkey_at = 0.0
        self._hotkey_listener = None
        self.recording_summary = ""
        self.recording_path: str | None = None
        self.pending_knowledge_notes = ""
        self.pending_knowledge_source = ""
        self.knowledge_context = ""
        self.video_notes = ""
        self.video_path = tk.StringVar()
        self.provider = tk.StringVar(value="Gemini")
        self.model = tk.StringVar(value=DEFAULT_MODELS["Gemini"])
        self.mastery_target = tk.StringVar(value="Fruit")
        self.allow_movement = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready. Live gameplay input playback is not implemented.")
        self._build_ui()
        self._load_key_for_provider()
        self._load_saved_knowledge()
        self._start_hotkey_listener()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_recording_status()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Blox Fruits Mastery Assistant", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Prompts + your demonstrations + cloud analysis. This prototype previews plans and records examples; it does not replay game inputs.",
            wraplength=920,
        ).pack(anchor="w", pady=(3, 10))

        provider_box = ttk.LabelFrame(outer, text="Cloud AI (only called when you ask)", padding=8)
        provider_box.pack(fill="x", pady=(0, 8))
        row = ttk.Frame(provider_box)
        row.pack(fill="x")
        ttk.Label(row, text="Provider").pack(side="left")
        provider_menu = ttk.Combobox(row, textvariable=self.provider, values=PROVIDERS, state="readonly", width=13)
        provider_menu.pack(side="left", padx=(6, 14))
        provider_menu.bind("<<ComboboxSelected>>", self._provider_changed)
        ttk.Label(row, text="Model").pack(side="left")
        ttk.Entry(row, textvariable=self.model, width=31).pack(side="left", padx=6)
        ttk.Label(row, text="API key").pack(side="left", padx=(8, 4))
        self.key_entry = ttk.Entry(row, show="•", width=25)
        self.key_entry.pack(side="left", padx=(0, 6))
        ttk.Button(row, text="Save key securely", command=self._save_key).pack(side="left")
        ttk.Label(
            provider_box,
            text="Keys use the OS credential store. Do not put API keys in prompts, recordings, or Git.",
            foreground="#666",
        ).pack(anchor="w", pady=(5, 0))

        settings = ttk.LabelFrame(outer, text="Routine settings", padding=8)
        settings.pack(fill="x", pady=(0, 8))
        row = ttk.Frame(settings)
        row.pack(fill="x")
        ttk.Label(row, text="Mastery target").pack(side="left")
        target_menu = ttk.Combobox(row, textvariable=self.mastery_target, values=TARGETS, state="readonly", width=18)
        target_menu.pack(side="left", padx=6)
        ttk.Checkbutton(
            row,
            text="Allow movement even if the prompt does not mention it",
            variable=self.allow_movement,
        ).pack(side="left", padx=12)
        ttk.Label(settings, text="Movement is off by default. Explicit movement in your prompt can authorize it for that plan.").pack(anchor="w", pady=(5, 0))

        prompt_box = ttk.LabelFrame(outer, text="Describe the routine", padding=8)
        prompt_box.pack(fill="x", pady=(0, 8))
        self.prompt_text = tk.Text(prompt_box, height=4, wrap="word", undo=True)
        self.prompt_text.pack(fill="x")
        self.prompt_text.insert(
            "1.0",
            "Farm nearby NPCs for sword mastery. Use my configured sword moves, keep attacking while enemies are nearby, and stop if the character gets stuck or the game loses focus.",
        )
        row = ttk.Frame(prompt_box)
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="Generate review plan", command=self._generate_plan).pack(side="left")
        ttk.Button(row, text="Clear prompt", command=lambda: self.prompt_text.delete("1.0", "end")).pack(side="left", padx=6)

        record_box = ttk.LabelFrame(outer, text="Record a demonstration (Windows; Roblox window must be focused)", padding=8)
        record_box.pack(fill="x", pady=(0, 8))
        row = ttk.Frame(record_box)
        row.pack(fill="x")
        self.start_button = ttk.Button(row, text="Arm F6 recording", command=self._toggle_recording_armed)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(row, text="Stop and save", command=self._stop_recording, state="disabled")
        self.stop_button.pack(side="left", padx=6)
        self.recording_status = ttk.Label(row, text="Not recording")
        self.recording_status.pack(side="left", padx=8)
        self.recording_analysis_button = ttk.Button(
            record_box, text="Analyze last recording + screenshots", command=self._analyze_recording, state="disabled"
        )
        self.recording_analysis_button.pack(anchor="w", pady=(6, 0))
        ttk.Button(
            record_box, text="Choose saved recording…", command=self._choose_saved_recording
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            record_box,
            text="Arm recording here, then focus Roblox and press F6 to start or stop while the game has focus. Only an allowlist of game controls and low-resolution screenshots are captured; arbitrary typed text is ignored.",
            wraplength=900,
        ).pack(anchor="w", pady=(5, 0))

        video_box = ttk.LabelFrame(outer, text="Learn from a video (on demand; sends sampled frames to selected provider)", padding=8)
        video_box.pack(fill="x", pady=(0, 8))
        row = ttk.Frame(video_box)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.video_path).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Choose video…", command=self._choose_video).pack(side="left", padx=6)
        self.video_button = ttk.Button(row, text="Analyze video", command=self._analyze_video)
        self.video_button.pack(side="left")
        ttk.Label(
            video_box,
            text="Only up to six resized frames are sent for analysis. Recorded demonstrations can align sampled input events with screenshots. Review AI findings before saving them as local knowledge.",
            wraplength=900,
        ).pack(anchor="w", pady=(5, 0))

        result_box = ttk.LabelFrame(outer, text="Review plan / AI observations", padding=8)
        result_box.pack(fill="both", expand=True)
        self.save_notes_button = ttk.Button(
            result_box, text="Save reviewed analysis as local knowledge", command=self._save_notes_as_knowledge, state="disabled"
        )
        self.save_notes_button.pack(anchor="w", pady=(0, 6))
        self.result_text = tk.Text(result_box, wrap="word", height=12)
        self.result_text.pack(fill="both", expand=True)
        self.result_text.insert(
            "1.0",
            "No plan generated yet. The example prompt requests sword mastery while the target selector is set to Fruit. The app should flag the mismatch instead of silently choosing.",
        )
        self.status_label = ttk.Label(outer, textvariable=self.status, wraplength=930)
        self.status_label.pack(fill="x", pady=(8, 0))

    def _load_saved_knowledge(self) -> None:
        # Only notes explicitly approved by the user are reused as reference knowledge.
        try:
            self.knowledge_context = load_reference_context()
            self.video_notes = self.knowledge_context
            if self.knowledge_context:
                self.status.set("Loaded user-approved local knowledge. Cloud requests remain on-demand.")
        except Exception:
            self.knowledge_context = ""
            self.video_notes = ""

    def _provider_changed(self, _event=None) -> None:
        name = self.provider.get()
        self.model.set(DEFAULT_MODELS.get(name, ""))
        self._load_key_for_provider()

    def _load_key_for_provider(self) -> None:
        try:
            key = keyring.get_password("BloxFruitsMasteryAssistant", SERVICE_NAMES[self.provider.get()])
        except Exception:
            key = None
        self.key_entry.delete(0, "end")
        if key:
            self.key_entry.insert(0, key)

    def _save_key(self) -> None:
        key = self.key_entry.get().strip()
        if not key:
            messagebox.showwarning("Missing API key", "Enter an API key first.")
            return
        try:
            keyring.set_password("BloxFruitsMasteryAssistant", SERVICE_NAMES[self.provider.get()], key)
            self.status.set(f"Saved {self.provider.get()} key in the system credential store.")
        except Exception as exc:
            messagebox.showerror(
                "Secure storage unavailable",
                f"The credential store could not save this key: {exc}\n\nNo key was written to a project file.",
            )

    def _get_key(self) -> str:
        # Prefer freshly entered text so a replacement key is testable before saving.
        entered = self.key_entry.get().strip()
        if entered:
            return entered
        try:
            return keyring.get_password("BloxFruitsMasteryAssistant", SERVICE_NAMES[self.provider.get()]) or ""
        except Exception:
            return ""

    def _render(self, text: str) -> None:
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)

    def _generate_plan(self) -> None:
        prompt = self.prompt_text.get("1.0", "end").strip()
        review = build_review(prompt, self.mastery_target.get(), self.allow_movement.get())
        self._render(review.format())
        if review.conflicts:
            self.status.set("Resolve the target/prompt conflict first. No API request or gameplay action was made.")
            return
        key = self._get_key()
        if not key:
            self.status.set("Review plan generated locally. Add an API key if you want cloud commentary.")
            return

        provider = self.provider.get()
        model = self.model.get()
        request_text = compose_ai_request(prompt, review, self.recording_summary, self.knowledge_context)
        self.status.set("Sending one review request to " + provider + "…")
        self._run_background(
            lambda: ask_provider(provider, key, model, SYSTEM_PROMPT, request_text),
            on_success=lambda answer: self._append_ai("AI commentary (advisory only):", answer),
            operation="Plan analysis",
        )

    def _append_ai(self, heading: str, answer: str) -> None:
        self.result_text.insert("end", "\n\n" + heading + "\n" + answer)
        self.status.set("Cloud analysis complete. The local movement/target restrictions remain authoritative.")

    def _start_hotkey_listener(self) -> None:
        try:
            from pynput import keyboard
            self._hotkey_listener = keyboard.Listener(on_press=self._on_global_key)
            self._hotkey_listener.start()
        except Exception as exc:
            self._hotkey_listener = None
            self.status.set(f"F6 recording hotkey unavailable: {exc}. Install requirements and restart.")

    def _on_global_key(self, key) -> None:
        if str(key) != "Key.f6":
            return
        now = time.monotonic()
        if now - self._last_hotkey_at < 0.9:
            return
        self._last_hotkey_at = now
        if not self.recording_armed or not roblox_is_foreground():
            return
        try:
            self.root.after(0, self._toggle_recording_from_game)
        except Exception:
            pass

    def _toggle_recording_from_game(self) -> None:
        if not self.recording_armed:
            return
        if self.recorder.active:
            self._stop_recording()
        else:
            self._start_recording()

    def _toggle_recording_armed(self) -> None:
        if self.recorder.active:
            self._stop_recording()
        self.recording_armed = not self.recording_armed
        self.start_button.configure(
            text="Disarm F6 recording" if self.recording_armed else "Arm F6 recording"
        )
        self.status.set(
            "Armed: focus Roblox and press F6 to start/stop recording."
            if self.recording_armed
            else "Recording hotkey disarmed."
        )

    def _start_recording(self) -> None:
        try:
            path = self.recorder.start()
            self.recording_summary = f"Recording started at local path {path}."
            self.stop_button.configure(state="normal")
            self.status.set("Recording. Press F6 in Roblox to stop, or use Stop and save.")
        except Exception as exc:
            messagebox.showerror("Cannot start recording", str(exc))
            self.status.set("Recording did not start.")

    def _stop_recording(self) -> None:
        try:
            info = self.recorder.stop()
            source_path = Path(info["directory"]) / "recording.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            actions = source.get("actions", [])
            # Preserve a spread of events across the demonstration without sending a huge prompt.
            sample_limit = 45
            if len(actions) <= sample_limit:
                sampled_actions = actions
            else:
                indexes = sorted({round(i * (len(actions) - 1) / (sample_limit - 1)) for i in range(sample_limit)})
                sampled_actions = [actions[i] for i in indexes]
            frames_dir = Path(info["directory"]) / "frames"
            frame_count = len(list(frames_dir.glob("*.jpg"))) if frames_dir.exists() else 0
            self.recording_path = str(Path(info["directory"]))
            self.recording_analysis_button.configure(state="normal")
            self.recording_summary = json.dumps({
                "duration_seconds": source.get("duration_seconds", info["duration_seconds"]),
                "action_count": len(actions),
                "sampled_action_count": len(sampled_actions),
                "sampled_actions_across_timeline": sampled_actions,
                "sampled_screenshot_count": frame_count,
                "recording_path": info["directory"],
                "note": "Sampled action events and screenshots are reference observations only; no playback is enabled."
            }, indent=2)[:4700]
            self.status.set(f"Recording saved. {info['action_count']} allowed input events and {frame_count} screenshots captured.")
        except Exception as exc:
            messagebox.showerror("Recording error", str(exc))
        finally:
            self.start_button.configure(
                state="normal",
                text="Disarm F6 recording" if self.recording_armed else "Arm F6 recording",
            )
            self.stop_button.configure(state="disabled")

    def _refresh_recording_status(self) -> None:
        if self.recorder.active:
            self.recording_status.configure(text=f"Recording · {self.recorder.action_count} events")
        else:
            self.recording_status.configure(text="Not recording")
        self.root.after(500, self._refresh_recording_status)

    def _choose_saved_recording(self) -> None:
        root_dir = app_data_dir() / "recordings"
        root_dir.mkdir(parents=True, exist_ok=True)
        chosen = filedialog.askdirectory(
            title="Choose a saved demonstration folder",
            initialdir=str(root_dir),
        )
        if not chosen:
            return
        if not (Path(chosen) / "recording.json").is_file():
            messagebox.showwarning("Not a recording", "Choose a folder containing recording.json.")
            return
        self.recording_path = chosen
        self.recording_analysis_button.configure(state="normal")
        self.status.set("Selected saved recording. Analyze it when ready.")

    def _analyze_recording(self) -> None:
        if not self.recording_path:
            messagebox.showwarning("No recording", "Record a demonstration or choose a saved recording folder first.")
            return
        key = self._get_key()
        if not key:
            messagebox.showwarning("API key required", "Save or enter an API key for the selected provider.")
            return
        provider, model, directory = self.provider.get(), self.model.get(), self.recording_path
        self.recording_analysis_button.configure(state="disabled")
        self.status.set("Analyzing a capped sample of input events and screenshots with " + provider + "…")
        self._run_background(
            lambda: analyze_recording(directory, provider, key, model),
            on_success=lambda notes: self._analysis_finished(notes, "recording"),
            operation="Recording analysis",
            on_finally=lambda: self.recording_analysis_button.configure(state="normal"),
        )

    def _choose_video(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose gameplay video",
            filetypes=[("Video files", "*.mp4 *.mov *.mkv *.avi *.webm"), ("All files", "*.*")],
        )
        if path:
            self.video_path.set(path)

    def _analyze_video(self) -> None:
        path = self.video_path.get().strip()
        if not path:
            messagebox.showwarning("Choose a video", "Choose a local gameplay video first.")
            return
        key = self._get_key()
        if not key:
            messagebox.showwarning("API key required", "Save or enter an API key for the selected provider.")
            return
        provider = self.provider.get()
        model = self.model.get()
        self.video_button.configure(state="disabled")
        self.status.set("Sampling a few small frames and sending them to " + provider + "…")
        self._run_background(
            lambda: analyze_video(path, provider, key, model),
            on_success=lambda notes: self._analysis_finished(notes, "video"),
            operation="Video analysis",
            on_finally=lambda: self.video_button.configure(state="normal"),
        )

    def _analysis_finished(self, notes: str, source: str) -> None:
        # Provider output is pending/untrusted; do not persist it before explicit approval.
        self.pending_knowledge_notes = notes
        self.pending_knowledge_source = source
        self.save_notes_button.configure(state="normal")
        label = "RECORDED INPUT + SCREENSHOT ANALYSIS" if source == "recording" else "VIDEO FRAME ANALYSIS"
        self._render(
            label + " (unapproved observations; review before saving)\n\n" + notes
            + "\n\nThese findings will not be added to future prompts until you click Save reviewed analysis as local knowledge."
        )
        self.status.set("Analysis complete. Review it before saving. No gameplay actions were executed.")

    def _save_notes_as_knowledge(self) -> None:
        notes = self.pending_knowledge_notes.strip()
        if not notes:
            messagebox.showwarning("No reviewed findings", "Analyze a video or recording first.")
            return
        source = "recording" if self.pending_knowledge_source == "recording" else "video"
        try:
            save_reference(
                title="Reviewed gameplay " + source + " notes",
                source=source,
                notes=notes,
            )
            self.knowledge_context = load_reference_context()
            self.video_notes = self.knowledge_context
            self.pending_knowledge_notes = ""
            self.save_notes_button.configure(state="disabled")
            self.status.set(f"Saved locally as approved knowledge. {len(list_references())} references stored on this PC.")
            self.result_text.insert("end", "\n\nSaved locally as user-approved knowledge.")
        except Exception as exc:
            messagebox.showerror("Could not save knowledge", str(exc))

    def _run_background(self, task, on_success, operation: str, on_finally=None) -> None:
        def worker() -> None:
            try:
                result = task()
                self.root.after(0, lambda: on_success(result))
            except Exception as exc:
                message = str(exc)
                self.root.after(0, lambda: self._show_error(operation, message))
            finally:
                if on_finally:
                    self.root.after(0, on_finally)
        threading.Thread(target=worker, name="mfa-cloud-request", daemon=True).start()

    def _show_error(self, operation: str, message: str) -> None:
        self.status.set(operation + " failed. No gameplay actions were taken.")
        messagebox.showerror(operation + " failed", message)

    def _on_close(self) -> None:
        if self.recorder.active:
            try:
                self.recorder.stop()
            except Exception:
                pass
        if self._hotkey_listener is not None:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    MasteryApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
