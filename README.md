# Virtual Mouse and Keyboard

Control your computer with hand gestures using a webcam. Built with **Python**, **OpenCV**, **MediaPipe**, and **PyAutoGUI** — move the cursor, click, scroll, and type on a virtual QWERTY keyboard without touching physical input devices.

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![OpenCV](https://img.shields.io/badge/opencv-4.8%2B-green)
![MediaPipe](https://img.shields.io/badge/mediapipe-0.10.21-orange)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Features

### Virtual Mouse
- **Cursor control** — raise your index finger inside the purple Cursor Zone
- **Pinch to click** — thumb + index pinch with hysteresis and cooldown
- **Scroll** — peace sign (index + middle up), move hand up/down
- **Responsive tracking** — fingertip crosshair follows your hand; cursor uses light smoothing
- **Visual feedback** — active area overlay, pinch distance, click ripples

### Virtual Keyboard
- **QWERTY overlay** — on-screen keyboard drawn with OpenCV
- **Glide typing** — pinch once and glide across keys without releasing
- **Hover highlight** — index finger highlights the key under the fingertip
- **Stable hit detection** — EMA smoothing and hover stability for accurate key selection

### Application
- **Dual mode** — switch between Mouse and Keyboard at runtime (`M` / `K`)
- **Live HUD** — mode, gesture label, and on-screen controls
- **Optional AI** — Groq-powered gesture analysis (press `A`)
- **Standalone demos** — run mouse, keyboard, or hand-tracking modules independently

---

## Demo

| Mode | Gestures |
|------|----------|
| **Mouse** | Index finger → move cursor · Pinch → click · Peace sign → scroll |
| **Keyboard** | Hover key → highlight · Pinch → type · Glide while pinching |

---

## Installation

### Prerequisites
- Python 3.9+
- Webcam
- macOS, Windows, or Linux

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/virtual-mouse-keyboard.git
cd virtual-mouse-keyboard
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install --upgrade pip
pip install --no-compile -r requirements.txt
```

> **Notes**
> - Use `--no-compile` if MediaPipe fails to install on macOS with Python 3.9.
> - MediaPipe is pinned to `0.10.21` because newer versions removed the `solutions` API this project uses.

### 4. (Optional) Enable Groq AI analysis

```bash
cp .env.example .env
# Edit .env and add your key from https://console.groq.com/keys
```

### 5. Grant permissions

| Platform | Permission | Why |
|----------|------------|-----|
| **macOS** | Camera | Webcam access for hand tracking |
| **macOS** | Accessibility | `pyautogui` needs this to move the mouse and type |
| **Windows** | Camera | Webcam access |
| **Linux** | Camera + display server | Webcam and cursor control |

On macOS: **System Settings → Privacy & Security → Camera / Accessibility**

---

## Usage

### Run the full application

```bash
source venv/bin/activate
python3 main.py
```

Use a different camera index:

```bash
python3 main.py 1
```

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `M` | Mouse mode |
| `K` | Keyboard mode |
| `A` | AI gesture analysis (requires Groq API key) |
| `Q` | Quit |

### Run individual modules

```bash
python3 test_hand_tracking.py   # Hand detection only
python3 virtual_mouse.py        # Mouse demo
python3 virtual_keyboard.py     # Keyboard demo
```

---

## Gesture Guide

### Mouse mode
1. Press **M**
2. Raise **index finger** (not a peace sign)
3. Keep fingertip inside the **purple Cursor Zone**
4. **Pinch** thumb + index to click
5. **Peace sign** + move hand up/down to scroll

### Keyboard mode
1. Press **K**
2. Hover index finger over a key (turns orange)
3. **Pinch** to type the key
4. Keep pinching and **glide** to adjacent keys for fast typing

---

## Project Structure

```
virtual-mouse-keyboard/
├── main.py                  # Main application entry point
├── hand_tracker.py          # MediaPipe hand detection & finger state
├── virtual_mouse.py         # Cursor, click, and scroll control
├── virtual_keyboard.py      # QWERTY overlay & glide typing
├── ui_overlay.py              # HUD, animations, and on-screen notices
├── groq_analyzer.py           # Optional Groq AI gesture analysis
├── utils.py                   # Webcam helpers and landmark utilities
├── test_hand_tracking.py      # Hand tracking test script
├── requirements.txt           # Python dependencies
├── .env.example               # Groq API key template (copy to .env)
├── LICENSE                    # MIT License
└── README.md
```

---

## Technologies

| Technology | Purpose |
|------------|---------|
| [Python 3](https://www.python.org/) | Core language |
| [OpenCV](https://opencv.org/) | Webcam capture, frame processing, UI drawing |
| [MediaPipe Hands](https://developers.google.com/mediapipe/solutions/vision/hand_landmarker) | Real-time hand landmark detection |
| [NumPy](https://numpy.org/) | Coordinate math and smoothing |
| [PyAutoGUI](https://pyautogui.readthedocs.io/) | System mouse and keyboard control |
| [Groq](https://groq.com/) | Optional LLM gesture analysis |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Webcam won't open | Check camera permissions; close other apps using the camera; try `python3 main.py 1` |
| Cursor doesn't move | Grant Accessibility permission (macOS); index finger up inside purple zone |
| Keys don't type | Grant Accessibility permission; pinch over a highlighted key |
| Jittery tracking | Improve lighting; use a plain background; hold hand steady |
| No hand detected | Show full hand in frame; move closer to camera |
| `python` not found (macOS) | Use `python3` and `pip3`, or activate `venv` first |

---

## Contributing

Contributions are welcome! Feel free to open an issue or submit a pull request.

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Acknowledgments

- [MediaPipe](https://developers.google.com/mediapipe) for hand tracking
- [OpenCV](https://opencv.org/) for computer vision utilities
- [PyAutoGUI](https://pyautogui.readthedocs.io/) for system input simulation
