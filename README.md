# Mic Volume Monitor

Monitors a microphone in real time, and if the volume stays above a threshold
(on average) for too long, runs a configurable action.

## Files
- `mic_monitor.py` — main program (device selection, monitoring loop, visualization)
- `actions.py` — action functions, called by name from `config.json`
- `config.json` — persisted settings (created/updated automatically)
- `requirements.txt` — dependencies

## Setup
```bash
pip install -r requirements.txt
```
Note: `sounddevice` requires the PortAudio library to be installed on your OS
(on most systems it's bundled; on Linux you may need `sudo apt install libportaudio2`).

`pygetwindow` (used by the window-minimize action) works best on Windows. On
macOS/Linux, window enumeration support is limited/absent — the action will
print an error rather than crash.

## Run
```bash
python mic_monitor.py
```
On first run you'll pick a microphone from a numbered list. On later runs,
if that same mic is still connected, you can just press Enter to reuse it.

## Config (`config.json`)
```json
{
  "selected_mic_index": 1,
  "selected_mic_name": "Built-in Microphone",
  "volume_threshold": 0.02,
  "sustained_seconds": 5,
  "status_print_interval": 5,
  "action": "print_alert",
  "visualization_enabled": true
}
```
- `volume_threshold` — RMS level (0.0–1.0-ish) that counts as "loud".
- `sustained_seconds` — how long the *rolling average* volume must stay above
  the threshold before the action triggers.
- `status_print_interval` — how often (seconds) to print a verbose status
  line, so the console doesn't get spammed on every audio frame.
- `action` — name of a function in `actions.py` to call when triggered. The
  program checks at startup that this function exists and will exit with an
  error if it doesn't.
- `visualization_enabled` — live ASCII level meter on/off (on by default).

## Actions (`actions.py`)
- `print_alert()` — just prints that the condition was met.
- `minimize_target_windows()` — scans all open window titles for a
  case-insensitive partial match against the hardcoded `TARGET_WINDOW_TITLES`
  list at the top of `actions.py`, and minimizes any matches, printing each
  step.

Add your own action by writing a new top-level function in `actions.py`, then
set `"action": "your_function_name"` in `config.json`.
