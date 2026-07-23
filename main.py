"""
mic_monitor.py
--------------
- Lists connected microphones and lets you select one (persisted to config.json,
  so next run you can just press Enter to reuse it if it's still connected).
- Streams real-time audio and computes the current volume (RMS level, 0.0-1.0).
- Prints a verbose status line every `status_print_interval` seconds (default 5)
  so the screen isn't spammed on every audio callback.
- Tracks a rolling average of the volume over the last `sustained_seconds`
  (default 5, adjustable). If that rolling average stays above
  `volume_threshold` for the full window, it's considered a "triggered" state:
  we print that the condition was met and call the configured action from
  actions.py.
- Optional live ASCII level meter (enabled by default), updated in real time
  on its own line independent of the periodic status prints.

All of the above (mic choice, threshold, sustained_seconds, print interval,
action name, visualization toggle) is persisted in config.json.
"""

import json
import os
import sys
import time
import threading
from collections import deque

import numpy as np
import sounddevice as sd

import actions

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "selected_mic_index": None,
    "selected_mic_name": None,
    "volume_threshold": 0.02,
    "sustained_seconds": 5,
    "status_print_interval": 5,
    "action": "print_alert",
    "visualization_enabled": True,
}


# ----------------------------------------------------------------------------
# Config handling
# ----------------------------------------------------------------------------

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            merged.update(cfg)
            return merged
        except (json.JSONDecodeError, OSError) as e:
            print(f"[CONFIG] Warning: could not read {CONFIG_PATH} ({e}), using defaults.")
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ----------------------------------------------------------------------------
# Microphone listing / selection
# ----------------------------------------------------------------------------

def list_input_devices():
    devices = sd.query_devices()
    input_devices = []
    for idx, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) > 0:
            input_devices.append((idx, dev))
    return input_devices


def select_microphone(cfg):
    input_devices = list_input_devices()
    if not input_devices:
        print("No input devices (microphones) found. Exiting.")
        sys.exit(1)

    print("\nAvailable microphones:")
    for pos, (idx, dev) in enumerate(input_devices):
        print(f"  [{pos}] (device index {idx}) {dev['name']}")

    last_idx = cfg.get("selected_mic_index")
    last_name = cfg.get("selected_mic_name")
    last_still_available = any(idx == last_idx for idx, _ in input_devices)

    if last_idx is not None and last_still_available:
        print(f"\nLast used mic: [{last_idx}] {last_name}")
        prompt = "Press Enter to use it again, or type a number from the list above: "
    else:
        if last_idx is not None:
            print(f"\nLast used mic ('{last_name}', index {last_idx}) is not currently connected.")
        prompt = "Type a number from the list above to select a microphone: "

    while True:
        choice = input(prompt).strip()

        if choice == "" and last_idx is not None and last_still_available:
            chosen_idx = last_idx
            chosen_name = last_name
            break

        if choice.isdigit():
            pos = int(choice)
            if 0 <= pos < len(input_devices):
                chosen_idx, chosen_dev = input_devices[pos]
                chosen_name = chosen_dev["name"]
                break

        print("Invalid selection, please try again.")

    cfg["selected_mic_index"] = chosen_idx
    cfg["selected_mic_name"] = chosen_name
    save_config(cfg)
    print(f"Selected microphone: [{chosen_idx}] {chosen_name}\n")
    return chosen_idx


# ----------------------------------------------------------------------------
# Action validation
# ----------------------------------------------------------------------------

def validate_action(cfg):
    action_name = cfg.get("action")
    available = actions.get_available_actions()
    if action_name not in available:
        print(f"[STARTUP] ERROR: action '{action_name}' set in config.json was not found in actions.py.")
        print(f"[STARTUP] Available actions: {list(available.keys())}")
        sys.exit(1)
    print(f"[STARTUP] Action '{action_name}' verified against actions.py.")
    return available[action_name]


# ----------------------------------------------------------------------------
# Volume monitoring
# ----------------------------------------------------------------------------

class VolumeMonitor:
    def __init__(self, cfg, action_fn):
        self.cfg = cfg
        self.action_fn = action_fn

        self.threshold = float(cfg["volume_threshold"])
        self.sustained_seconds = float(cfg["sustained_seconds"])
        self.status_interval = float(cfg["status_print_interval"])
        self.visualization_enabled = bool(cfg["visualization_enabled"])

        # Rolling window of (timestamp, rms) samples for the sustained check
        self.window = deque()
        self.window_lock = threading.Lock()

        self.current_level = 0.0
        self.level_lock = threading.Lock()

        self.last_status_print = 0.0
        self.triggered = False  # prevents re-triggering every loop while still above threshold

        self.running = True

    def audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[AUDIO] Stream status: {status}")

        # RMS of this block, as a 0.0-1.0-ish level (float32 samples are -1..1)
        rms = float(np.sqrt(np.mean(np.square(indata))))
        now = time.monotonic()

        with self.level_lock:
            self.current_level = rms

        with self.window_lock:
            self.window.append((now, rms))
            cutoff = now - self.sustained_seconds
            while self.window and self.window[0][0] < cutoff:
                self.window.popleft()

    def get_window_average_and_span(self):
        with self.window_lock:
            if not self.window:
                return 0.0, 0.0
            avg = sum(v for _, v in self.window) / len(self.window)
            span = self.window[-1][0] - self.window[0][0]
            return avg, span

    def draw_meter(self, level):
        bar_width = 40
        filled = min(bar_width, int(level * bar_width / 0.5))  # scale so ~0.5 rms = full bar
        bar = "#" * filled + "-" * (bar_width - filled)
        thresh_marker_pos = min(bar_width - 1, int(self.threshold * bar_width / 0.5))
        bar = (
            bar[:thresh_marker_pos]
            + "|"
            + bar[thresh_marker_pos + 1:]
        )
        sys.stdout.write(f"\r[LEVEL] [{bar}] {level:.4f}   ")
        sys.stdout.flush()

    def run(self):
        device_index = self.cfg["selected_mic_index"]

        print(f"[MONITOR] Listening on device index {device_index}...")
        print(
            f"[MONITOR] threshold={self.threshold}, sustained_seconds={self.sustained_seconds}, "
            f"status_print_interval={self.status_interval}, action='{self.cfg['action']}'"
        )
        print("[MONITOR] Press Ctrl+C to stop.\n")

        with sd.InputStream(
            device=device_index,
            channels=1,
            samplerate=44100,
            blocksize=1024,
            callback=self.audio_callback,
        ):
            self.last_status_print = time.monotonic()
            try:
                while self.running:
                    time.sleep(0.05)

                    with self.level_lock:
                        level = self.current_level

                    if self.visualization_enabled:
                        self.draw_meter(level)

                    now = time.monotonic()
                    avg, span = self.get_window_average_and_span()

                    # Periodic verbose status print (separate from the live meter)
                    if now - self.last_status_print >= self.status_interval:
                        self.last_status_print = now
                        prefix = "\n" if self.visualization_enabled else ""
                        print(
                            f"{prefix}[STATUS] current={level:.4f} "
                            f"rolling_avg({self.sustained_seconds}s)={avg:.4f} "
                            f"threshold={self.threshold} "
                            f"{'[ABOVE THRESHOLD]' if avg > self.threshold else '[below threshold]'}"
                        )

                    # Sustained-condition check: only counts once we have a full window's
                    # worth of data (span >= sustained_seconds) so we don't trigger early.
                    condition_met = avg > self.threshold and span >= self.sustained_seconds

                    if condition_met and not self.triggered:
                        self.triggered = True
                        prefix = "\n" if self.visualization_enabled else ""
                        print(
                            f"{prefix}[TRIGGER] Volume has averaged {avg:.4f} (> {self.threshold}) "
                            f"over the last {self.sustained_seconds}s. Running action '{self.cfg['action']}'..."
                        )
                        try:
                            self.action_fn()
                        except Exception as e:
                            print(f"[TRIGGER] Action raised an exception: {e}")
                        print("[TRIGGER] Action finished. Resuming normal monitoring.\n")

                        # Reset the window so we require a fresh sustained period
                        # before triggering again.
                        with self.window_lock:
                            self.window.clear()

                    elif not condition_met and self.triggered:
                        self.triggered = False

            except KeyboardInterrupt:
                print("\n[MONITOR] Stopped by user.")


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    cfg = load_config()

    action_fn = validate_action(cfg)
    select_microphone(cfg)

    monitor = VolumeMonitor(cfg, action_fn)
    monitor.run()


if __name__ == "__main__":
    main()
