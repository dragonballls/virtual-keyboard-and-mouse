# Blox Fruits Mastery Assistant — review-only prototype

This subproject is a lightweight Windows desktop assistant for reviewing user-provided game demonstrations and videos. It is separate from the original hand-gesture project in the repository.

## What it does

- Previews a local review plan and flags a mismatch between the selected category and the user's prompt.
- Supports on-demand text/image analysis through Gemini, OpenAI, Anthropic, or OpenRouter.
- Stores API keys through the operating-system credential store; keys are never written into project files.
- Optionally records an allowlisted set of keyboard/mouse events and small screenshots while the Roblox window is foregrounded.
- Samples at most six frames from a selected video or recording and sends them to only the selected provider.
- Keeps model output pending until the user reviews and explicitly saves it as local reference knowledge.
- Saves recordings and approved reference notes under %LOCALAPPDATA%\\BloxFruitsMasteryAssistant (or ~/.local/share/BloxFruitsMasteryAssistant as fallback).

**This branch is intentionally review-only. It does not send or replay gameplay inputs, automate movement, reset the character, or perform combat.** Model output is untrusted until reviewed. No local language model is run.

## Run from source

Python 3.11+ is recommended. Open PowerShell in mastery_assistant:

    py -m venv .venv
    .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt
    .\\.venv\\Scripts\\python.exe app.py

The Tkinter UI is included with standard Windows Python. Focus detection requires pywin32.

## API keys

Choose a provider, enter its key, and select **Test connection** to make one small real request to that provider. Then select **Save key securely** to store the key through keyring and the OS credential backend when available. The key field is masked. Do not put keys into prompts, recordings, screenshots, or Git. Test and analysis requests may incur provider charges. API calls occur only when you explicitly request them, with one selected provider and bounded input. Provider model availability and quotas can change; model names are editable.

## Recording and privacy

Arm recording in the app, focus Roblox, and press F6 to start or stop without changing game focus. Only a narrow allowlist of game-control keys and mouse clicks is captured; arbitrary typed text is ignored. A small screenshot is captured about every three seconds only while the Roblox window remains in the foreground. Recordings may still contain account names or other visible information, so review them before uploading anything to a cloud provider.

The app can also analyze an existing local video. It samples at most six resized frames. Recording analysis sends at most 48 allowlisted events and six small JPEG frames. Oversized/corrupt files are rejected or skipped. If the game loses focus, the recorder does not save additional input events.

Approved knowledge is stored in %LOCALAPPDATA%\\BloxFruitsMasteryAssistant\\knowledge\\references.json; only notes that the user explicitly saves are reused in future review prompts. This local data is excluded from Git.

## Windows executable

The Mastery Assistant CI workflow runs syntax checks and the tests. After they pass, it builds a portable one-folder Windows executable and runs its --self-test mode to verify imports and core review-only invariants without using the network or sending gameplay inputs.

Download the workflow artifact named BloxFruitsMasteryAssistant-Windows-x64. Keep the entire extracted folder together (including _internal) and run BloxFruitsMasteryAssistant.exe. The executable still requires your own API key for cloud analysis.

## Development and tests

From this folder:

    .\\.venv\\Scripts\\python.exe -m compileall -q .
    .\\.venv\\Scripts\\python.exe -m pytest -q

The tests cover target validation, movement policy, manual reset reporting, bounded video/recording inputs, provider request shapes, credential-safe error handling, and packaged-build startup checks.

## Current limitations

- Video analysis describes observations only; it cannot infer precise keypresses from frames alone.
- Focus detection and the packaged executable target Windows.
- The recorder is a demonstration recorder, not a playback engine.
- The app does not inspect game memory, inject into the game process, manipulate remote events, or bypass anti-cheat systems.
