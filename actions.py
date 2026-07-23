"""
actions.py
----------
Each function in this file is a potential "action" that mic_monitor.py can
trigger when the microphone volume stays above the configured threshold for
too long. The function name used in config.json's "action" field must match
a function defined here, with no required arguments.

Add your own actions by just adding a new top-level function below.
"""

import sys

# Hardcoded list of (partial, case-insensitive) window title matches.
# Any currently open window whose title CONTAINS one of these substrings
# (case-insensitive) will be minimized by minimize_target_windows().
TARGET_WINDOW_TITLES = [
    "spotify",
    "discord",
    "youtube",
    "netflix",
]


def print_alert():
    """Simple action: just announce that the condition was met."""
    print("[ACTION] Condition met: microphone volume stayed above threshold for too long!")


def minimize_target_windows():
    """
    Search all open window titles for a partial, case-insensitive match
    against TARGET_WINDOW_TITLES, and minimize any matches. Verbose about
    every step so you can see exactly what it's doing.
    """
    print("[ACTION] Starting window scan for targets:", TARGET_WINDOW_TITLES)

    try:
        import pygetwindow as gw
    except ImportError:
        print("[ACTION] ERROR: pygetwindow is not installed. Run: pip install pygetwindow")
        return

    try:
        all_windows = gw.getAllWindows()
    except Exception as e:
        print(f"[ACTION] ERROR: could not enumerate windows on this platform: {e}")
        print("[ACTION] Note: pygetwindow's window enumeration is most reliable on Windows.")
        return

    print(f"[ACTION] Found {len(all_windows)} open window(s). Scanning titles...")

    matched_any = False
    for win in all_windows:
        title = (win.title or "").strip()
        if not title:
            continue

        title_lower = title.lower()
        for target in TARGET_WINDOW_TITLES:
            if target.lower() in title_lower:
                matched_any = True
                print(f"[ACTION]   Match: window '{title}' contains target '{target}'")
                try:
                    if win.isMinimized:
                        print(f"[ACTION]   -> Already minimized, skipping: '{title}'")
                    else:
                        win.minimize()
                        print(f"[ACTION]   -> Minimized: '{title}'")
                except Exception as e:
                    print(f"[ACTION]   -> Failed to minimize '{title}': {e}")
                break  # no need to check other targets for this window

    if not matched_any:
        print("[ACTION] No open windows matched any target title.")

    print("[ACTION] Window scan complete.")


def get_available_actions():
    """Utility used by mic_monitor.py to validate the configured action name."""
    return {
        name: obj
        for name, obj in globals().items()
        if callable(obj) and not name.startswith("_") and name != "get_available_actions"
    }


if __name__ == "__main__":
    # Allows quick manual testing: python actions.py print_alert
    if len(sys.argv) > 1:
        fn_name = sys.argv[1]
        fn = get_available_actions().get(fn_name)
        if fn:
            fn()
        else:
            print(f"No such action: {fn_name}")
            print("Available actions:", list(get_available_actions().keys()))
    else:
        print("Available actions:", list(get_available_actions().keys()))
