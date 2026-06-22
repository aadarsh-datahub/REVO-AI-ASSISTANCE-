import json
import sys
from importlib.util import find_spec
from pathlib import Path

ROOT = Path(__file__).resolve().parent

REQUIRED_FILES = [
    "main.py",
    "ui.py",
    "requirements.txt",
    "config/api_keys.example.json",
    "config/user_profile.example.json",
    "core/prompt.txt",
]

PACKAGE_CHECKS = {
    "PyQt6": "PyQt6",
    "google-genai": "google.genai",
    "sounddevice": "sounddevice",
    "requests": "requests",
    "playwright": "playwright",
    "pyautogui": "pyautogui",
    "psutil": "psutil",
    "mss": "mss",
    "cv2/opencv-python": "cv2",
    "pycaw": "pycaw",
    "screen-brightness-control": "screen_brightness_control",
    "yt-dlp": "yt_dlp",
}


def ok(msg):
    print(f"[OK] {msg}")


def warn(msg):
    print(f"[WARN] {msg}")


def fail(msg):
    print(f"[FAIL] {msg}")



def _audio_summary(config: dict):
    try:
        import sounddevice as sd
    except Exception:
        warn("sounddevice unavailable; cannot inspect microphone.")
        return
    input_idx = config.get("input_device_index")
    output_idx = config.get("output_device_index")
    try:
        if input_idx is not None:
            mic = sd.query_devices(int(input_idx))
            ok(f"REVO microphone: {mic.get('name', input_idx)}")
        elif config.get("input_device_name"):
            ok(f"REVO microphone preference: {config.get('input_device_name')}")
        else:
            warn("No microphone configured; REVO will use system default.")
    except Exception as exc:
        warn(f"Configured microphone not available: {exc}")
    try:
        if output_idx is not None:
            speaker = sd.query_devices(int(output_idx))
            ok(f"REVO speaker: {speaker.get('name', output_idx)}")
        elif config.get("output_device_name"):
            ok(f"REVO speaker preference: {config.get('output_device_name')}")
        else:
            warn("No speaker configured; REVO will use system default.")
    except Exception as exc:
        warn(f"Configured speaker not available: {exc}")

def main():
    failures = 0
    print("REVO OS Doctor")
    print("==============")
    print(f"Python: {sys.version.split()[0]}")
    if sys.version_info < (3, 11):
        fail("Python 3.11+ recommended.")
        failures += 1
    elif sys.version_info >= (3, 13):
        warn("Python 3.11/3.12 recommended for best package compatibility.")
    else:
        ok("Python version looks good.")

    for rel in REQUIRED_FILES:
        path = ROOT / rel
        if path.exists():
            ok(f"Found {rel}")
        else:
            fail(f"Missing {rel}")
            failures += 1

    config_path = ROOT / "config" / "api_keys.json"
    if not config_path.exists():
        warn("config/api_keys.json missing. Copy config/api_keys.example.json and add keys.")
    else:
        try:
            data = json.loads(config_path.read_text(encoding="utf-8-sig"))
            gemini = str(data.get("gemini_api_key", ""))
            openrouter = str(data.get("openrouter_api_key", ""))
            if not gemini or "PASTE_" in gemini:
                warn("Gemini API key is missing or placeholder.")
            else:
                ok("Gemini API key is present.")
            if not openrouter or "PASTE_" in openrouter:
                warn("OpenRouter API key is missing or placeholder.")
            else:
                ok("OpenRouter API key is present.")
            _audio_summary(data)
        except Exception as exc:
            fail(f"Could not read config/api_keys.json: {exc}")
            failures += 1

    profile_path = ROOT / "config" / "user_profile.json"
    if profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
            ok(f"User profile present for: {profile.get('user_name') or 'Sir'}")
        except Exception as exc:
            warn(f"Could not read config/user_profile.json: {exc}")
    else:
        warn("config/user_profile.json missing. Run: python setup.py")

    missing = []
    for label, module in PACKAGE_CHECKS.items():
        if find_spec(module) is None:
            missing.append(label)
        else:
            ok(f"Package available: {label}")
    if missing:
        warn("Missing packages: " + ", ".join(missing))
        warn("Run: python -m pip install -r requirements.txt")

    if failures:
        print(f"\nDoctor finished with {failures} blocking issue(s).")
        return 1
    print("\nDoctor finished. If warnings are only missing keys, add keys and start REVO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())