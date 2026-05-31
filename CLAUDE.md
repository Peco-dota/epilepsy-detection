# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
cd epilepsy-detection
source .venv/bin/activate
python src/main.py
```

Python 3.10–3.12 required. Python 3.13 is not supported (mediapipe incompatibility).

## Environment setup

`.env` must be placed inside `src/` (loaded via `load_dotenv(dotenv_path=Path(__file__).with_name(".env"))`):

```
GEMINI_API_KEY=""         # required — get free key at aistudio.google.com
TWILIO_ACCOUNT_SID=""     # optional — SMS alerts
TWILIO_AUTH_TOKEN=""      # optional
TWILIO_WHATSAPP_FROM=""   # optional
TELEPHONE_NUMBER=""       # optional
```

Twilio is only initialised if all four env vars are present. The app runs without it.

## Key runtime flags in `main.py`

- `debug=True` — skips the GUI menu, goes straight to camera. Set `False` for full user flow.
- `solo_video=False` — mosaic view showing all 7 detection windows. `True` = single overlay window.

## Architecture

### Signal pipeline (per frame)

`main.py` → `FaceDetection` orchestrates the frame loop. Each frame:
1. Camera frame captured via `cv2.VideoCapture` (macOS: `CAP_AVFOUNDATION`, auto-selects built-in over iPhone Continuity Camera)
2. MediaPipe FaceMesh extracts 468 facial landmarks
3. Seven detection modules run in sequence, each returning a score in `[0, 1]`:
   - `shake_detection.py` — head tremor (energy + direction flips over 20-frame deque)
   - `twitch_detector.py` — myoclonic twitches (5s sliding window, cooldown)
   - `face_freeze.py` — absence episodes (landmark stillness duration)
   - `face_drooping.py` — facial asymmetry via mouth corner rotation
   - `eye_tracking.py` — iris deviation + movement speed (30-frame deque)
   - `check_blink_eye.py` — blink rate (10s window, 0.17/s normal → 2.0/s seizure)
   - `health_monitor_module.py` — heart rate via rPPG (FFT on green channel, 150-frame calibration) + skin color
4. Two weighted risk scores computed: `convulsive_risk` and `x_non_convulsive`
5. `PreIctalDetector.update()` runs temporal analysis across all 8 signals
6. CSV logged at 1Hz; alert overlay drawn on frame

### Adaptive weights

Weights live in `weights.json` (next to `src/`), loaded at startup, saved after each feedback event. Default weights are in `DEFAULT_WEIGHTS` in `face_detection.py`. The two risk formulas are:
- `convulsive = w_bpm·bpm + w_shake·shake + w_blink·blink + w_color·color`
- `non_convulsive = w_asym·asym + w_freeze·freeze + w_blink_nc·blink + w_bpm_nc·bpm + w_color·color + w_twitch·twitch`

### Pre-ictal temporal model (`pre_ictal_detector.py`)

EWMA-smoothed signals → online linear regression slope → 4-stage HMM-style progression (Baseline → Prodromal → Pre-ictal → Imminent). Score = stage(50%) + co-activation(30%) + trend(20%). Warning fires at score ≥ 0.55. Thresholds are scaled by context multipliers from the pre-session check-in.

### AI integration (`gpt_client.py`)

Single `AIClient` class, all calls via OpenAI SDK pointed at Gemini's OpenAI-compatible endpoint. Model: `gemini-3.1-flash-lite`. Four prompt types:
- `get_response()` — symptom text → JSON weights for slider defaults
- `assess_context()` — pre-session context → per-signal sensitivity multipliers (0.5–2.0)
- `analyze_session()` — CSV summary → plain-English session report
- `recalibrate_weights()` — feedback events → updated weight JSON

All calls use `_call_with_retry()` with exponential backoff on 429 rate limit errors.

### GUI flow (`menu.py`, `summary_window.py`)

PySide6 throughout — no tkinter/customtkinter anywhere except `epilepsy_content_recognition.py` which is spawned as a separate subprocess.

**Pre-session menu** (3 screens, only shown when `debug=False`):
1. Context check-in (sleep/stress/medication/screen chips + free text) → Gemini → multipliers
2. Symptom description → Gemini → slider defaults
3. Threshold sliders with context badges

**Post-session review** (`SessionReviewWindow`):
- Left: AI analysis rendered as HTML via `QWebEngineView` (markdown → HTML conversion in `markdown_to_html()`), score bars parsed from summary text
- Right: multi-turn Gemini chat for weight calibration. When Gemini outputs a `\`\`\`json\`\`\`` block containing known weight keys, the Save button appears.
- Collapsible manual weight sliders also on left panel
- "Start New Session" button spawns a new `main.py` process

### Epilepsy content protection (`epilepsy_content_recognition.py`)

Runs as a **separate subprocess** (not a thread) when `debug=False`. Monitors screen for photosensitive flash patterns using Quartz APIs (macOS only). Hides offending apps via AppleScript. Uses PySide6 for its notification dialog.

## macOS-specific notes

- `pyobjc-framework-Quartz` and `pyobjc-framework-Cocoa` are macOS-only. Comment them out on Windows.
- Camera selection uses `system_profiler SPCameraDataType` to identify and skip iPhone Continuity Camera.
- Keyboard listener uses `termios`/`tty` (POSIX only).

## Data flow for personalisation

Context multipliers from the menu flow into `FaceDetection.apply_context_multipliers()`, which divides each `_SignalTracker.threshold` in `PreIctalDetector` by the multiplier (higher multiplier = more sensitive). Multipliers are also applied to slider defaults in the menu before display. In-session Y/N feedback on alerts adjusts weights by ×1.15 (correct) or ×0.85 (false positive) for signals that were above 0.3 at alert time, then saves to `weights.json`. End-of-session Gemini recalibration takes all feedback events and proposes a full weight revision.
