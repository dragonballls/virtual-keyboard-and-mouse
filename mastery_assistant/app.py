"""Tkinter UI for the first Blox Fruits Mastery Assistant milestone."""
from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import keyring

from providers import PROVIDERS, DEFAULT_MODELS, SERVICE_NAMES, ask_provider
from recorder import ActionRecorder, app_data_dir
from routine import TARGETS, build_review, compose_ai_request
from video_learning import analyze_video

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
        self.recording_summary = ""
        self.video_notes = ""
        self.video_path = tk.StringVar()
        self.provider = tk.StringVar(value="Gemini")
        self.model = tk.StringVar(value=DEFAULT_MODELS["Gemini"])
        self.mastery_target = tk.StringVar(value="Fruit")
        self.allow_movement = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready. Live gameplay input playback is not implemented.")
        self._build_ui()
        self._load_key_for_provider()
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
        self.start_button = ttk.Button(row, text="Start recording", command=self._start_recording)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(row, text="Stop and save", command=self._stop_recording, state="disabled")
        self.stop_button.pack(side="left", padx=6)
        self.recording_status = ttk.Label(row, text="Not recording")
        self.recording_status.pack(side="left", padx=8)
        ttk.Label(
            record_box,
            text="Records an allowlist of game controls and low-resolution screenshots only while the foreground window title contains Roblox. It does not record arbitrary typed text.",
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
            text="Only up to six resized frames are sent for analysis. Video-only analysis cannot determine the exact keys pressed; pair it with an input recording.",
            wraplength=900,
        ).pack(anchor="w", pady=(5, 0))

        result_box = ttk.LabelFrame(outer, text="Review plan / AI observations", padding=8)
        result_box.pack(fill="both", expand=True)
        self.result_text = tk.Text(result_box, wrap="word", height=12)
        self.result_text.pack(fill="both", expand=True)
        self.result_text.insert(
            "1.0",
            "No plan generated yet. The example prompt requests sword mastery while the target selector is set to Fruit. The app should flag the mismatch instead of silently choosing.",
        )
        self.status_label = ttk.Label(outer, textvariable=self.status, wraplength=930)
        self.status_label.pack(fill="x", pady=(8, 0))

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
        try:
            return keyring.get_password("BloxFruitsMasteryAssistant", SERVICE_NAMES[self.provider.get()]) or self.key_entry.get().strip()
        except Exception:
            return self.key_entry.get().strip()

    def _render(self, text: str) -> None:
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)

    def _generate_plan(self) -> None:
        prompt = self.prompt_text.get("1.0", "end").strip()
        review = build_review(prompt, self.mastery_target.get(), self.allow_movement.get())
        base = review.format()
        self._render(base)
        if review.conflicts:
            self.status.set("Resolve the target/prompt conflict before using this routine. No gameplay actions were taken.")
        else:
            self.status.set("Review plan generated locally. Live gameplay playback is disabled.")
        key = self._get_key()
        if not key:
            self.status.set(self.status.get() + " Add an API key to request optional cloud commentary.")
            return

        provider = self.provider.get()
        model = self.model.get()
        self.status.set("Sending one review request to " + provider + "…")
        request_text = compose_ai_request(prompt, review, self.recording_summary, self.video_notes)
        self._run_background(
            lambda: ask_provider(provider, key, model, SYSTEM_PROMPT, request_text),
            on_success=lambda answer: self._append_ai("AI commentary (advisory only):", answer),
            operation="Plan analysis",
        )

    def _append_ai(self, heading: str, answer: str) -> None:
        self.result_text.insert("end", "\n\n" + heading + "\n" + answer)
        self.status.set("Cloud analysis complete. The local movement/target restrictions remain authoritative.")

    def _start_recording(self) -> None:
        try:
            path = self.recorder.start()
            self.recording_summary = f"Recording started at local path {path}."
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            self.status.set("Recording. Keep the Roblox game focused; unrelated typed text is ignored.")
        except Exception as exc:
            messagebox.showerror("Cannot start recording", str(exc))
            self.status.set("Recording did not start.")

    def _stop_recording(self) -> None:
        try:
            info = self.recorder.stop()
            self.recording_summary = json.dumps(info, indent=2)
            self.recording_summary += "\nInput event data is available locally in recording.json."
            self.status.set(f"Recording saved. {info['action_count']} allowed input events captured.")
        except Exception as exc:
            messagebox.showerror("Recording error", str(exc))
        finally:
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")

    def _refresh_recording_status(self) -> None:
        if self.recorder.active:
            self.recording_status.configure(text=f"Recording · {self.recorder.action_count} events")
        else:
            self.recording_status.configure(text="Not recording")
        self.root.after(500, self._refresh_recording_status)

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
            on_success=self._video_analysis_finished,
            operation="Video analysis",
            on_finally=lambda: self.video_button.configure(state="normal"),
        )

    def _video_analysis_finished(self, notes: str) -> None:
        self.video_notes = notes
        knowledge_dir = app_data_dir() / "knowledge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        notes_path = knowledge_dir / "latest_video_notes.txt"
        notes_path.write_text(notes, encoding="utf-8")
        self._render(
            "VIDEO NOTES (observations; verify before reuse)\n\n" + notes
            + "\n\nThese notes will be included in the next plan request. No actions were executed."
        )
        self.status.set("Video analysis saved locally. No action sequence was inferred from frames alone.")

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
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    MasteryApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
