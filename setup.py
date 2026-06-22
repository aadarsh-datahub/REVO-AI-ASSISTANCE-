import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"


def run(cmd):
    print("+", " ".join(map(str, cmd)))
    subprocess.run(list(map(str, cmd)), cwd=ROOT, check=True)


def _write_json(path: Path, data):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


def _load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    return default


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{prompt}{suffix}: ").strip()
        return value or default
    except EOFError:
        return default


def _list_audio_devices():
    try:
        import sounddevice as sd
    except Exception:
        return {"microphones": [], "speakers": []}
    devices = {"microphones": [], "speakers": []}
    try:
        for dev in sd.query_devices():
            row = {"index": int(dev["index"]), "name": str(dev["name"])}
            if int(dev.get("max_input_channels", 0)) > 0:
                devices["microphones"].append(row)
            if int(dev.get("max_output_channels", 0)) > 0:
                devices["speakers"].append(row)
    except Exception as exc:
        print(f"[WARN] Could not list audio devices: {exc}")
    return devices


def _choose_device(kind: str, rows: list[dict]):
    if not rows:
        print(f"[WARN] No {kind} devices detected. REVO will use system default.")
        return None
    print(f"\nDetected {kind} devices:")
    for row in rows:
        print(f"  {row['index']}: {row['name']}")
    default = str(rows[0]["index"])
    choice = _ask(f"Select {kind[:-1]} index for REVO", default)
    try:
        idx = int(choice)
        for row in rows:
            if row["index"] == idx:
                return row
    except ValueError:
        pass
    print(f"[WARN] Invalid selection. Using: {rows[0]['name']}")
    return rows[0]


def configure_local_profile():
    CONFIG_DIR.mkdir(exist_ok=True)

    profile_path = CONFIG_DIR / "user_profile.json"
    profile = _load_json(profile_path, {
        "user_name": "Sir",
        "assistant_name": "REVO",
        "career_goal": "",
        "current_projects": [],
    })
    profile["user_name"] = _ask("What should REVO call you?", str(profile.get("user_name") or "Sir"))
    profile["assistant_name"] = "REVO"
    profile["career_goal"] = _ask("Career goal (optional)", str(profile.get("career_goal") or ""))
    _write_json(profile_path, profile)

    api_example = CONFIG_DIR / "api_keys.example.json"
    api_target = CONFIG_DIR / "api_keys.json"
    if api_example.exists() and not api_target.exists():
        api_target.write_text(api_example.read_text(encoding="utf-8"), encoding="utf-8")
        print("Created config/api_keys.json. Add your API keys before running.")

    api_config = _load_json(api_target, {})
    devices = _list_audio_devices()
    mic = _choose_device("microphones", devices["microphones"])
    speaker = _choose_device("speakers", devices["speakers"])
    if mic:
        api_config["input_device_index"] = mic["index"]
        api_config["input_device_name"] = mic["name"]
    if speaker:
        api_config["output_device_index"] = speaker["index"]
        api_config["output_device_name"] = speaker["name"]
    if api_config:
        _write_json(api_target, api_config)

    print("\nREVO local setup summary")
    print("------------------------")
    print(f"User name: {profile['user_name']}")
    print(f"Assistant name: REVO")
    print(f"Operating microphone: {mic['name'] if mic else 'System default microphone'}")
    print(f"Output speaker: {speaker['name'] if speaker else 'System default speaker'}")
    print("Creator lock: Aadarsh Mishra + official LinkedIn profile are hard-coded in REVO tools.")


if __name__ == "__main__":
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    run([sys.executable, "-m", "playwright", "install"])
    configure_local_profile()
    print("\nSetup complete. Add API keys in config/api_keys.json, then run: python main.py")
