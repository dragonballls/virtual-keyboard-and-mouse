# Blox Fruits Mastery Assistant (prototype)

A lightweight Windows prototype for prompt-driven, user-taught gameplay routines. This is a separate subproject under mastery_assistant/ and does not replace or modify the existing hand-gesture application.

## First milestone

- Prompt-to-plan preview with a locally enforced target-conflict check.
- Gemini, OpenAI, Anthropic, and OpenRouter text/image analysis through direct HTTPS requests.
- API keys stored through the operating-system credential store; keys are never written to project files.
- Opt-in recording of a limited set of keyboard/mouse actions only while the foreground window title contains Roblox.
- Periodic low-resolution screenshots of the focused Roblox window while recording.
- On-demand video analysis: sample up to six frames and send only those frames to the selected cloud provider.
- Saved video notes and recordings stay under the user's LocalAppData folder, not in Git.
- Movement disabled by default. An explicit movement instruction or the user setting is required.
- No game-input playback in this milestone. Plans and model output are advisory; they cannot execute actions.

## Windows setup

Python 3.11+ is recommended.

1. Open PowerShell in this folder.
2. Create a virtual environment and install the requirements:

   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe app.py

The app uses Tkinter included with standard Windows Python. The focused-window check requires pywin32.

## API keys

Choose a provider, enter its key, then select Save key securely. The app stores the key through keyring, using a system credential backend when available. The key field is masked. Never paste keys into prompts or commit them to Git.

Gemini is the suggested starter provider. The model name is editable because provider model availability and quotas can change. Other providers are optional. API calls occur only when you explicitly request plan or video analysis; there is no polling loop or automatic multi-provider fan-out.

## Recording safety

Click Arm F6 recording in the app, then focus Roblox and press F6 to start or stop recording without changing game focus. The recorder accepts a narrow allowlist of game-control keys and mouse clicks, and rechecks the foreground window before saving an event. It does not record arbitrary typed text. Screenshots are cropped to the Roblox window and downscaled before saving. You can also use Stop and save in the app as a fallback; that click will change focus, so use F6 for the cleanest recording.

Local recordings and video notes are stored under %LOCALAPPDATA%\BloxFruitsMasteryAssistant (or ~/.local/share/BloxFruitsMasteryAssistant as fallback). They are excluded from Git by this subproject's .gitignore.

## Current limitations

- Video analysis samples frames; it does not infer exact keyboard events from video alone. Pair video with an input recording for better teaching.
- Focus detection currently targets Windows and expects the foreground title to include Roblox.
- Stuck detection and Reset Character recovery are not wired into gameplay yet.
- No autonomous movement or live combat playback. Add those only after a separate safety-reviewed controller and test harness exist.
- Automation can conflict with game rules. Use only permitted, ordinary game-window interactions; no process injection, memory reading, or remote-event manipulation.

## Development

Run tests with: .venv\Scripts\python.exe -m pytest

Current test coverage focuses on target validation and movement authorization policy.


## Teaching-loop improvements

- Analyze a recorded demonstration by sending a bounded sample of normal input events and up to six recorded screenshots to one selected provider.
- Choose and analyze earlier recordings from the local recordings folder.
- AI analysis stays pending until reviewed and explicitly saved as local knowledge. Unreviewed model output is not reused in future prompts.
- Approved knowledge is stored under %LOCALAPPDATA%\BloxFruitsMasteryAssistant\knowledge\references.json and is never committed to Git.
- Movement authorization is conservative: “stop moving if stuck” is not permission; a positive instruction such as “move toward an NPC when out of range” is recognized.
- Live input playback remains outside this prototype; the app records, analyzes, and prepares reviewable plans.
