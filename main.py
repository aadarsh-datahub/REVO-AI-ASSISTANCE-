import asyncio
import threading
import json
import sys
import traceback
import logging
import queue
import time
import webbrowser
import re
from pathlib import Path
from datetime import datetime

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import sounddevice as sd
from google import genai
from google.genai import types
from ui import REVOUI
from core.creator_identity import (
    CREATOR_NAME, CREATOR_LINKEDIN_URL, CREATOR_RESPONSE,
    creator_warning, validate_creator_identity,
)
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
    should_extract_memory, extract_memory
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app, resolve_installed_app, launch_resolved_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings, _detect_pc_control_locally
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.pc_health         import pc_health_scan
from actions.command_learning  import command_learning, find_learned_command
from actions.routine_assistant import routine_assistant
from actions.job_mode          import job_mode
from actions.safe_shopping     import safe_shopping
from actions.ai_brain          import ai_brain_status
from actions.security_mode     import log_action, is_confirmed, confirmation_required
from actions.emotional_companion import (
    emotional_companion,
    handle_companion_text,
    app_context_message,
    start_companion_scheduler,
    get_personality_mode,
)
from actions.media_download    import media_download, detect_media_request
from actions.smart_modes       import smart_modes
from actions.memory_system     import remember_text, goals_text, yesterday_text


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PERSONAL_SHORTCUTS_PATH = BASE_DIR / "config" / "personal_shortcuts.json"
USER_PROFILE_PATH = BASE_DIR / "config" / "user_profile.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LOG_DIR         = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
DEBUG_LOG_PATH  = LOG_DIR / "revo_debug.log"
logging.basicConfig(
    filename=str(DEBUG_LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)["gemini_api_key"]

DEFAULT_USER_PROFILE = {
    "user_name": "Sir",
    "assistant_name": "REVO",
    "career_goal": "",
    "current_projects": [],
}


def _windows_guess_name() -> str:
    try:
        import getpass
        name = (getpass.getuser() or "").strip()
        if name and name.lower() not in ("user", "admin", "administrator"):
            return name
    except Exception:
        pass
    return "Sir"


def _load_user_profile() -> dict:
    profile = dict(DEFAULT_USER_PROFILE)
    try:
        if USER_PROFILE_PATH.exists():
            data = json.loads(USER_PROFILE_PATH.read_text(encoding="utf-8-sig") or "{}")
            if isinstance(data, dict):
                profile.update({k: v for k, v in data.items() if v is not None})
        else:
            profile["user_name"] = _windows_guess_name()
            USER_PROFILE_PATH.parent.mkdir(exist_ok=True)
            USER_PROFILE_PATH.write_text(json.dumps(profile, indent=2, ensure_ascii=True), encoding="utf-8")
    except Exception:
        pass
    profile["assistant_name"] = "REVO"
    return profile


def _save_user_profile(profile: dict) -> None:
    clean = dict(DEFAULT_USER_PROFILE)
    clean.update(profile or {})
    clean["assistant_name"] = "REVO"
    USER_PROFILE_PATH.parent.mkdir(exist_ok=True)
    USER_PROFILE_PATH.write_text(json.dumps(clean, indent=2, ensure_ascii=True), encoding="utf-8")


def _user_name() -> str:
    return str(_load_user_profile().get("user_name") or "Sir").strip() or "Sir"


def _set_user_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 ._'-]", "", str(name or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)[:40]
    if not cleaned:
        return "Revo, naam clear nahi mila. Bolo: mera naam Rahul hai."
    profile = _load_user_profile()
    profile["user_name"] = cleaned
    _save_user_profile(profile)
    try:
        update_memory({"identity": {"name": {"value": cleaned}}, "preferences": {"assistant_name": {"value": "REVO"}}})
    except Exception:
        pass
    return f"Done {cleaned}, ab main tumhe {cleaned} bulaungi."


def _detect_name_update(text: str) -> str | None:
    t = re.sub(r"\s+", " ", str(text or "").strip())
    patterns = [
        r"(?:mera|my)\s+(?:naam|name)\s+(?:hai|is)\s+(.+)$",
        r"(?:call me|mujhe)\s+(.+?)\s+(?:bulao|bolo)$",
    ]
    for pat in patterns:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if m:
            return _set_user_name(m.group(1))
    return None


def _safe_audio_device_name(device_index, input_device: bool) -> str:
    try:
        if device_index is None:
            return "System default microphone" if input_device else "System default speaker"
        info = sd.query_devices(int(device_index))
        return str(info.get("name") or info)
    except Exception:
        return str(device_index) if device_index is not None else ("System default microphone" if input_device else "System default speaker")


def _available_audio_devices() -> dict:
    devices = {"microphones": [], "speakers": []}
    try:
        for dev in sd.query_devices():
            row = {"index": int(dev["index"]), "name": str(dev["name"])}
            if int(dev.get("max_input_channels", 0)) > 0:
                devices["microphones"].append(row)
            if int(dev.get("max_output_channels", 0)) > 0:
                devices["speakers"].append(row)
    except Exception:
        pass
    return devices


def _get_input_device():
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            config = json.load(f)
    except Exception:
        return None

    if "input_device_index" in config:
        try:
            return int(config["input_device_index"])
        except (TypeError, ValueError):
            pass

    return _find_audio_device(config.get("input_device_name"), input_device=True)


def _get_output_device():
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            config = json.load(f)
    except Exception:
        return None

    if "output_device_index" in config:
        try:
            return int(config["output_device_index"])
        except (TypeError, ValueError):
            pass

    return _find_audio_device(config.get("output_device_name"), input_device=False)


def _find_audio_device(requested_name, input_device: bool):
    requested = str(requested_name or "").strip().lower()
    if not requested:
        return None

    channel_key = "max_input_channels" if input_device else "max_output_channels"
    try:
        for device in sd.query_devices():
            name = str(device["name"])
            if int(device[channel_key]) > 0 and requested in name.lower():
                return int(device["index"])
    except Exception as e:
        kind = "Mic" if input_device else "Speaker"
        print(f"[REVO] {kind} lookup failed: {e}")
    return None


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            f"You are REVO, {_user_name()}'s AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â always call the appropriate tool. "
            f"If anyone asks who made you, reply exactly: {CREATOR_RESPONSE}"
        )


DEFAULT_PERSONAL_SHORTCUTS = {
    "my_youtube_playlist": "https://www.youtube.com/watch?v=wCQohfT6Q78&list=RDwCQohfT6Q78&start_radio=1"
}


def _load_personal_shortcuts() -> dict:
    try:
        if not PERSONAL_SHORTCUTS_PATH.exists():
            PERSONAL_SHORTCUTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            PERSONAL_SHORTCUTS_PATH.write_text(
                json.dumps(DEFAULT_PERSONAL_SHORTCUTS, indent=2),
                encoding="utf-8"
            )
        with open(PERSONAL_SHORTCUTS_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        changed = False
        for key, value in DEFAULT_PERSONAL_SHORTCUTS.items():
            if key not in data:
                data[key] = value
                changed = True
        if changed:
            PERSONAL_SHORTCUTS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data
    except Exception as e:
        print(f"[Shortcuts] load failed: {e}")
        return dict(DEFAULT_PERSONAL_SHORTCUTS)


def _detect_personal_shortcut(text: str) -> dict | None:
    normalized = re.sub(r"\s+", " ", (text or "").lower().strip())
    playlist_patterns = (
        "open my playlist",
        "open my youtube playlist",
        "meri playlist kholo",
        "revo playlist",
        "revo playlist chalao",
        "my music playlist",
        "youtube playlist chalao",
        "playlist chalao",
    )
    if any(pattern in normalized for pattern in playlist_patterns):
        shortcuts = _load_personal_shortcuts()
        return {
            "key": "my_youtube_playlist",
            "url": shortcuts.get("my_youtube_playlist", DEFAULT_PERSONAL_SHORTCUTS["my_youtube_playlist"]),
            "reply": "Done Revo, tumhari playlist Microsoft Edge me chala di. Edge minimize kar diya."
        }
    return None


KNOWN_WEBSITES = {
    "youtube": "https://www.youtube.com",
    "linkedin": "https://www.linkedin.com",
    "gmail": "https://mail.google.com/mail/u/0/#inbox",
    "github": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "google": "https://www.google.com",
    "whatsapp": "https://web.whatsapp.com",
}


def _extract_open_target(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    lower = normalized.lower()
    prefixes = (
        "open ",
        "launch ",
        "start ",
        "kholo ",
        "khol ",
    )
    for prefix in prefixes:
        if lower.startswith(prefix):
            return normalized[len(prefix):].strip()
    if lower.endswith(" kholo"):
        return normalized[:-6].strip()
    return ""


def _known_website_url(target: str) -> str | None:
    lower = (target or "").lower().strip()
    for key, url in KNOWN_WEBSITES.items():
        if key == lower or key in lower:
            return url
    return None


def _is_gemini_quota_error(error: Exception) -> bool:
    msg = str(error).lower()
    markers = (
        "429",
        "quota",
        "resource_exhausted",
        "resource exhausted",
        "rate limit",
        "rate_limit",
        "exceeded your current quota",
        "free tier",
        "billing",
    )
    return any(marker in msg for marker in markers)
    
_last_memory_input = ""

def _update_memory_async(user_text: str, REVO_text: str) -> None:
    global _last_memory_input

    user_text   = (user_text   or "").strip()
    REVO_text = (REVO_text or "").strip()

    if len(user_text) < 5 or user_text == _last_memory_input:
        return
    _last_memory_input = user_text

    try:
        api_key = _get_api_key()
        if not should_extract_memory(user_text, REVO_text, api_key):
            return
        data = extract_memory(user_text, REVO_text, api_key)
        if data:
            update_memory(data)
            print(f"[Memory] ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ {list(data.keys())}")
    except Exception as e:
        if "429" not in str(e):
            print(f"[Memory] ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¯ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¸ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â {e}")

TOOL_DECLARATIONS = [
    {
        "name": "open_creator_linkedin",
        "description": (
            "Opens the LinkedIn page of REVO's creator, Aadarsh Mishra. "
            "Call this whenever the user asks to open the LinkedIn page/profile of "
            "the person who made, built, or created you. Also use for Hinglish/Hindi "
            "requests like 'jisne tumko banaya uska LinkedIn kholo'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "open_world_news_monitor",
        "description": (
            "Opens the live world news/global event monitor. "
            "Call this whenever the user asks for news, latest news, current news, "
            "world news, global updates, conflicts, war updates, or says 'news batao'. "
            "Use this instead of answering from model memory."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "open_app",
        "description": (
            "Opens any application on the Windows computer. "
            "Use this whenever the user asks to open, launch, or start an installed app/program. "
            "App-first priority: use this before browser_control or web_search for app names. "
            "Known apps include Riot Client, Valorant, Discord, Chrome, Edge, Task Manager, "
            "Control Panel, Settings, Device Manager, PC Manager, VS Code, Steam, Spotify."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for information. LAST RESORT only: use after installed apps, personal shortcuts, known websites, and direct AI reasoning fail.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Windows Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "For volume use actions volume_set, volume_increase, volume_decrease, mute, unmute. "
            "For brightness use brightness_set, brightness_increase, brightness_decrease. "
            "Hinglish: awaz means volume, screen light means brightness, badhao means increase, "
            "kam karo means decrease, set karo/kar do means execute. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume/brightness level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls Microsoft Edge only. Use for opening websites, YouTube playback, "
            "ChatGPT screenshot analysis, clicking elements, filling forms, scrolling, "
            "uploading files, personal shortcuts, and web automation. Never use Brave/Chrome/default browser."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | open_website | open_youtube | open_youtube_playlist | restore_youtube | show_youtube | maximize_youtube | pause_music | resume_music | next_song | previous_song | search | play_youtube | chatgpt_screen_solution | click | type | scroll | fill_form | smart_click | smart_type | get_text | press | close"},
                "url":         {"type": "STRING", "description": "URL or site name for go_to/open_website action. Examples: youtube, linkedin, gmail, github, chatgpt, google, whatsapp"},
                "query":       {"type": "STRING", "description": "Search query for search or play_youtube action"},
                "prompt":      {"type": "STRING", "description": "Prompt to type into ChatGPT for chatgpt_screen_solution"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up or down for scroll"},
                "key":         {"type": "STRING", "description": "Key name for press action"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "pc_health_scan",
        "description": (
            "Shows PC health and security report. Use for CPU/RAM/disk/GPU checks, slow PC, "
            "startup apps, suspicious downloads, Defender threat history, virus scan, or security scan. "
            "Safe only: never delete, quarantine, uninstall, or change files."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "summary | security | quick_scan | virus_scan"},
                "description": {"type": "STRING", "description": "User's health/security request"}
            },
            "required": []
        }
    },
    {
        "name": "command_learning",
        "description": (
            "Learns user command corrections and custom meanings. Use when user says galat samjha, "
            "maine X bola tha, remember this command, or 'is command ka matlab ye hai'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "remember | forget | list"},
                "wrong": {"type": "STRING", "description": "Phrase REVO heard or should learn"},
                "correct": {"type": "STRING", "description": "Correct command/meaning"},
                "text": {"type": "STRING", "description": "Raw correction sentence"}
            },
            "required": []
        }
    },
    {
        "name": "routine_assistant",
        "description": (
            "Daily routine assistant: water reminders, focus timers, daily plan, motivation, "
            "and non-repeating Hinglish productivity/health tips."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "tip | water | focus | plan | motivate"},
                "minutes": {"type": "NUMBER", "description": "Timer minutes for water/focus reminders"},
                "description": {"type": "STRING", "description": "Natural language routine request"}
            },
            "required": []
        }
    },
    {
        "name": "job_mode",
        "description": (
            "Job and internship mode. Opens LinkedIn job searches, drafts cold emails/DMs, "
            "saves job leads, and gives resume tips. Never auto-apply."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "search | cold_email | dm | resume_tips | save_lead"},
                "role": {"type": "STRING", "description": "Role or internship keyword"},
                "location": {"type": "STRING", "description": "Job location"},
                "company": {"type": "STRING", "description": "Company name"},
                "query": {"type": "STRING", "description": "Search query"}
            },
            "required": []
        }
    },
    {
        "name": "safe_shopping",
        "description": (
            "Safe shopping helper for Zepto, Blinkit, Amazon, Flipkart. Can open/search stores, "
            "but must stop before checkout, payment, OTP, or order placement."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "open | search | add_to_cart | checkout_request"},
                "store": {"type": "STRING", "description": "zepto | blinkit | amazon | flipkart"},
                "item": {"type": "STRING", "description": "Item to search"},
                "query": {"type": "STRING", "description": "Shopping search query"}
            },
            "required": []
        }
    },
    {
        "name": "ai_brain_status",
        "description": "Shows REVO's intent classification/debug brain panel for a user command.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text": {"type": "STRING", "description": "Command to classify"},
                "description": {"type": "STRING", "description": "Natural language debug request"}
            },
            "required": []
        }
    },
    {
        "name": "emotional_companion",
        "description": (
            "Emotional companion system. Use for mood tracking, listener/friend/motivation/focus/work modes, "
            "supportive Hinglish emotional replies, daily summary, goals panel, check-ins, and tips. "
            "Use AI only for emotional/chat responses; do not route simple PC commands here."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "status | mood | ask_mood | mode | daily_summary | goals | emotional_memory | checkin_history | checkin | tip"},
                "mood": {"type": "STRING", "description": "great | normal | bad | stressed | tired"},
                "mode": {"type": "STRING", "description": "work | friend | motivation | listener | focus"},
                "text": {"type": "STRING", "description": "User emotional message or companion request"},
                "description": {"type": "STRING", "description": "Natural language companion request"}
            },
            "required": []
        }
    },
    {
        "name": "media_download",
        "description": (
            "Downloads user-owned/permitted YouTube/Instagram media using yt-dlp. "
            "Use for 'iska audio download karo', 'iska video download karo', 'is link ka mp3 nikalo', "
            "'is reel ko download karo', 'youtube audio save karo'. Must ask permission confirmation first. "
            "Never bypass DRM, paywalls, login/private restrictions, or auto-download without permission."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "download | open_folder"},
                "url": {"type": "STRING", "description": "YouTube/Instagram URL"},
                "type": {"type": "STRING", "description": "audio | video"},
                "permissionConfirmed": {"type": "BOOLEAN", "description": "True only when user confirms rights/permission"},
                "confirmed": {"type": "STRING", "description": "yes/confirm if user confirmed permission"},
                "text": {"type": "STRING", "description": "Raw user request"}
            },
            "required": []
        }
    },
    {
        "name": "smart_modes",
        "description": (
            "Activates REVO smart modes: Productive Mode/Focus/Work, Gaming Mode/Game/Valorant, Normal Mode, "
            "and reports current mode. Productive mode closes distracting apps, keeps work apps, sets volume 30, "
            "enables DND, clears notifications, then asks what app to open. Gaming mode closes work apps, opens Discord, "
            "Riot Client, Valorant, personal playlist, sets volume 85, High Performance power, disables notifications."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "productive_mode | gaming_mode | normal_mode | current_mode"},
                "mode": {"type": "STRING", "description": "productive | gaming | normal | status"},
                "include_chrome": {"type": "BOOLEAN", "description": "Close Chrome in productive mode only after user confirms"},
                "description": {"type": "STRING", "description": "Natural language mode request"}
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
    "name": "shutdown_revo",
    "description": (
        "Shuts down the assistant completely. "
        "Call this when the user expresses intent to end the conversation, "
        "close the assistant, say goodbye, or stop REVO. "
        "The user can say this in ANY language."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
    }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â name, age, birthday, city, job, language, nationality | "
                        "preferences ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â favorite food/color/music/film/game/sport, hobbies | "
                        "projects ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â active projects, goals, things being built | "
                        "relationships ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â friends, family, partner, colleagues | "
                        "wishes ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â future plans, things to buy, travel dreams | "
                        "notes ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
]


class REVOLive:

    def __init__(self, ui: REVOUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._quota_alerted = False
        self._pending_media_download = None
        self._greeted_this_process = False
        self._last_greeting_ts = 0.0
        self._last_interaction_ts = time.time()
        self._memory_cache = load_memory()
        self._memory_cache_ts = time.time()
        self._last_stt_start_ts = 0.0
        self._voice_fast_handled = False
        self._awaiting_reply = False
        self._awaiting_stage = "idle"
        self._awaiting_since = 0.0
        self._last_reply_ts = time.time()
        self._restart_requested = False
        self._speech_queue = queue.Queue()
        self._speech_in_progress = False
        self._latest_response_text = ""
        self._last_speech_time = 0.0
        self._last_tts_request_ts = 0.0
        self._last_audio_start_ts = 0.0
        self._last_audio_write_ts = 0.0
        self._tts_fail_count = 0
        self._tts_engine = "Gemini Live Voice"
        self._current_voice = "Charon"
        self._browser_voice_mode = False
        self._last_user_voice_ui_ts = 0.0
        self._mic_announced = False
        self._mic_drop_count = 0
        self._last_mic_drop_log_ts = 0.0
        self.ui.on_text_command = self._on_text_command
        self._seed_personal_memory()
        if not validate_creator_identity():
            warning = creator_warning()
            print(f"[REVO] {warning}")
            try:
                self.ui.write_log(f"REVO: {warning}")
            except Exception:
                pass
        start_companion_scheduler(self.ui)

    def _seed_personal_memory(self):
        profile = _load_user_profile()
        name = str(profile.get("user_name") or "Sir")
        projects = profile.get("current_projects") or []
        if isinstance(projects, list):
            projects_value = ", ".join(str(x) for x in projects if x) or "REVO OS / Jarvis"
        else:
            projects_value = str(projects or "REVO OS / Jarvis")
        update_memory({
            "identity": {"name": {"value": name}},
            "preferences": {"assistant_name": {"value": "REVO"}},
            "projects": {
                "career_goal": {"value": str(profile.get("career_goal") or "")},
                "current_projects": {"value": projects_value},
            },
        })

    def _startup_greeting_text(self) -> str:
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return (
                "Good Morning Sir.\n"
                "Aapka din kaisa ja raha hai?\n"
                "Hope ki aaj ka din achha ja raha hoga.\n"
                "Batayiye, aaj main aapke liye kya kar sakta hoon?"
            )
        if 12 <= hour < 17:
            return (
                "Good Afternoon Sir.\n"
                "Umeed karta hoon aapka din productive ja raha hoga.\n"
                "Batayiye aaj kya kaam karna hai?"
            )
        if 17 <= hour < 22:
            return (
                "Good Evening Sir.\n"
                "Aaj ka din kaisa raha?\n"
                "Main ready hoon. Batayiye kya help kar sakta hoon."
            )
        return (
            "Good Evening Sir.\n"
            "Kaafi der tak kaam kar rahe hain.\n"
            "Main online hoon. Batayiye kya karna hai."
        )
    async def _delayed_startup_greeting(self):
        await asyncio.sleep(1.5)
        if self._greeted_this_process:
            return
        self._greeted_this_process = True
        self._last_greeting_ts = time.time()
        greeting = self._startup_greeting_text()
        self.ui.write_log(f"REVO: {greeting}")
        if not self._mic_announced:
            mic_name = _safe_audio_device_name(_get_input_device(), input_device=True)
            self._mic_announced = True
            self.ui.write_log(f"REVO: Mic active: {mic_name}")
            greeting = f"{greeting}\nMic active: {mic_name}."
        self.ui.set_state("SPEAKING")
        self.speak(greeting)
        await asyncio.sleep(2.5)
        if not self.ui.muted:
            self.ui.set_state("LISTENING")
        self._log_latency("startup_greeting", 0.0, 0.0, 0.0, 2500.0)

    def _maybe_idle_or_wake_greeting(self, text: str) -> None:
        now = time.time()
        t = (text or "").lower().strip()
        wake = t in ("revo", "hey revo", "wake up revo", "revo wake up", "revo sun")
        long_idle = now - self._last_interaction_ts > 60 * 60
        self._last_interaction_ts = now
        if not (wake or long_idle):
            return
        if now - self._last_greeting_ts < 15 * 60:
            return
        self._last_greeting_ts = now
        greeting = self._startup_greeting_text()
        self.ui.write_log(f"REVO: {greeting}")
        self.speak(greeting)

    def _debug_stage(self, stage: str, detail: str = "", error: Exception | str | None = None) -> None:
        msg = f"[{stage}]"
        if detail:
            msg += f" {detail}"
        if error is not None:
            msg += f" ERROR: {error}"
        try:
            logging.error(msg) if error is not None else logging.info(msg)
        except Exception:
            pass
        try:
            self.ui.write_log(msg)
        except Exception:
            print(msg)

    def _set_voice_status(self, voice=None, ai=None, tts=None, memory=None, **extra) -> None:
        try:
            if hasattr(self.ui, "set_voice_status"):
                self.ui.set_voice_status(voice=voice, ai=ai, tts=tts, memory=memory, **extra)
        except Exception as exc:
            logging.error("[STATUS PANEL] update failed: %s", exc)

    def _pcm_rms(self, data: bytes) -> float:
        if not data:
            return 0.0
        try:
            sample_count = len(data) // 2
            if sample_count <= 0:
                return 0.0
            step = max(1, sample_count // 256)
            total = 0
            used = 0
            for i in range(0, sample_count, step):
                j = i * 2
                sample = int.from_bytes(data[j:j+2], byteorder="little", signed=True)
                total += sample * sample
                used += 1
            return (total / max(1, used)) ** 0.5
        except Exception:
            return 0.0

    def _mark_user_voice_activity(self, data: bytes) -> None:
        rms = self._pcm_rms(data)
        now = time.time()
        if rms > 650 and now - self._last_user_voice_ui_ts > 0.08:
            self._last_user_voice_ui_ts = now
            try:
                if hasattr(self.ui, "set_user_voice_active"):
                    self.ui.set_user_voice_active(True)
            except Exception:
                pass

    def _enqueue_realtime_audio(self, media: dict) -> None:
        try:
            if not self.out_queue:
                return
            if self.out_queue.full():
                self._mic_drop_count += 1
                now = time.time()
                if now - self._last_mic_drop_log_ts > 5:
                    self._last_mic_drop_log_ts = now
                    self._debug_stage("STT FAILED", f"mic queue full; dropped {self._mic_drop_count} chunks")
                return
            self.out_queue.put_nowait(media)
        except Exception as exc:
            self._debug_stage("STT FAILED", "enqueue realtime audio", exc)

    def _start_reply_watch(self, stage: str) -> None:
        self._awaiting_reply = True
        self._awaiting_stage = stage
        self._awaiting_since = time.time()

    def _mark_reply_generated(self, stage: str = "reply") -> None:
        self._awaiting_reply = False
        self._awaiting_stage = stage
        self._last_reply_ts = time.time()

    async def _voice_watchdog(self):
        self._debug_stage("WATCHDOG START", "10s voice recovery active")
        while True:
            await asyncio.sleep(1)
            if self._awaiting_reply and time.time() - self._awaiting_since > 10:
                msg = f"No reply generated for 10 seconds at stage: {self._awaiting_stage}"
                self._debug_stage("WATCHDOG RESTART", msg, RuntimeError(msg))
                self._set_voice_status(voice="failed", ai="failed", tts="failed")
                self._restart_requested = True
                fallback = "Revo, AI backend me issue aa gaya hai. Main recover kar rahi hoon."
                try:
                    self.ui.write_log(f"REVO: {fallback}")
                except Exception:
                    pass
                self._mark_reply_generated("watchdog_fallback")
                raise RuntimeError(msg)

    def _split_speech_chunks(self, text: str, max_chars: int = 300) -> list[str]:
        clean = str(text or "").strip()
        if not clean:
            return []
        if len(clean) <= max_chars:
            return [clean]
        chunks = []
        current = ""
        for part in re.split(r"(?<=[.!?à¥¤])\s+", clean):
            if not part:
                continue
            if len(current) + len(part) + 1 <= max_chars:
                current = (current + " " + part).strip()
            else:
                if current:
                    chunks.append(current)
                while len(part) > max_chars:
                    chunks.append(part[:max_chars].strip())
                    part = part[max_chars:].strip()
                current = part
        if current:
            chunks.append(current)
        return chunks[:12]

    def _update_tts_debug_panel(self):
        self._set_voice_status(
            tts="failed" if self._tts_fail_count >= 3 else "running",
            tts_engine=self._tts_engine,
            current_voice=self._current_voice,
            queue_length=self._speech_queue.qsize() if hasattr(self, "_speech_queue") else 0,
            last_speech_time=self._last_speech_time,
        )

    def _clear_audio_queue(self):
        try:
            if self.audio_in_queue:
                while not self.audio_in_queue.empty():
                    self.audio_in_queue.get_nowait()
        except Exception:
            pass

    def _browser_voice_fallback(self, text: str):
        self._browser_voice_mode = True
        self._tts_engine = "Browser Voice"
        self._current_voice = "Browser default"
        msg = "ElevenLabs unavailable. Switched to Browser Voice."
        self._debug_stage("TTS RESTART", msg)
        try:
            self.ui.write_log(msg)
            self.ui.write_log(f"REVO TEXT: {text}")
        except Exception:
            pass
        self._update_tts_debug_panel()

    def _restart_tts_engine(self, reason: str = ""):
        self._tts_fail_count += 1
        self._debug_stage("TTS RESTART", reason or "Restarting Gemini Live Voice")
        try:
            self.ui.write_log("[VOICE ENGINE RESTARTING]")
        except Exception:
            pass
        self._set_voice_status(tts="failed")
        self._clear_audio_queue()
        if self._tts_fail_count >= 3:
            self._browser_voice_fallback(self._latest_response_text)
            return
        self._restart_requested = True
        self._update_tts_debug_panel()
        return False

    async def _speech_queue_worker(self):
        self._debug_stage("TTS START", "speech queue worker online")
        while True:
            text = await asyncio.to_thread(self._speech_queue.get)
            if text is None:
                await asyncio.sleep(0.05)
                continue
            self._speech_in_progress = True
            self._latest_response_text = str(text)
            chunks = self._split_speech_chunks(str(text), 300)
            for idx, chunk in enumerate(chunks, 1):
                if self._browser_voice_mode:
                    self._browser_voice_fallback(chunk)
                    continue
                if not self._loop or not self.session:
                    self._debug_stage("TTS FAILED", "No active session for speech queue", RuntimeError("No active session"))
                    try:
                        self.ui.write_log(f"REVO TEXT: {chunk}")
                    except Exception:
                        pass
                    continue
                before_audio = self._last_audio_start_ts
                self._last_tts_request_ts = time.time()
                self._debug_stage("TTS START", f"chunk {idx}/{len(chunks)}: {chunk[:120]}")
                self._update_tts_debug_panel()
                try:
                    await self.session.send_client_content(
                        turns={"parts": [{"text": chunk}]},
                        turn_complete=True,
                    )
                    # TTS watchdog: audio must start within 3 seconds.
                    deadline = time.time() + 3.0
                    while time.time() < deadline:
                        if self._last_audio_start_ts > before_audio:
                            break
                        await asyncio.sleep(0.05)
                    if self._last_audio_start_ts <= before_audio:
                        self._debug_stage("TTS FAILED", "No audio started within 3 seconds", RuntimeError("TTS start timeout"))
                        self._set_voice_status(tts="failed")
                        self._restart_tts_engine("No audio started within 3 seconds")
                        break
                    self._debug_stage("TTS COMPLETE", f"chunk {idx}/{len(chunks)}")
                    self._tts_fail_count = 0
                    self._last_speech_time = time.time()
                    self._update_tts_debug_panel()
                    await asyncio.sleep(0.15)
                except Exception as exc:
                    self._debug_stage("TTS FAILED", f"chunk {idx}/{len(chunks)}", exc)
                    self._set_voice_status(tts="failed")
                    try:
                        self.ui.write_log(f"REVO TEXT: {chunk}")
                    except Exception:
                        pass
                    if self._tts_fail_count >= 3:
                        self._browser_voice_fallback(chunk)
                    else:
                        self._restart_tts_engine(str(exc))
                    break
            self._speech_in_progress = False
            self._speech_queue.task_done()

    async def _tts_heartbeat(self):
        self._debug_stage("TTS START", "heartbeat online")
        while True:
            await asyncio.sleep(15)
            tts_engine_alive = bool(self.session and self.audio_in_queue is not None)
            self._debug_stage("TTS HEARTBEAT", f"tts_engine_alive={tts_engine_alive} queue={self._speech_queue.qsize()}")
            self._update_tts_debug_panel()
            if not tts_engine_alive:
                self._restart_tts_engine("heartbeat detected dead TTS engine")

    def _log_latency(self, source: str, stt_ms: float = 0.0, intent_ms: float = 0.0, ai_ms: float = 0.0, total_ms: float = 0.0):
        msg = (
            f"DEBUG SPEED [{source}] STT Time: {stt_ms:.0f} ms | "
            f"Intent Time: {intent_ms:.0f} ms | AI Time: {ai_ms:.0f} ms | "
            f"TTS Time: 0 ms | Total Response Time: {total_ms:.0f} ms"
        )
        try:
            self.ui.write_log(msg)
        except Exception:
            print(msg)

    def _cached_memory(self, ttl_seconds: int = 300) -> dict:
        now = time.time()
        try:
            if not getattr(self, "_memory_cache", None) or now - getattr(self, "_memory_cache_ts", 0.0) > ttl_seconds:
                self._memory_cache = load_memory()
                self._memory_cache_ts = now
            self._set_voice_status(memory="running")
            return self._memory_cache
        except Exception as exc:
            self._debug_stage("MEMORY FAILED", "load_memory", exc)
            self._set_voice_status(memory="failed")
            return getattr(self, "_memory_cache", {}) or {}

    def _refresh_memory_cache_async(self) -> None:
        def _refresh():
            try:
                self._memory_cache = load_memory()
                self._memory_cache_ts = time.time()
            except Exception:
                pass
        threading.Thread(target=_refresh, daemon=True).start()

    def _is_fast_command(self, text: str) -> bool:
        t = (text or "").lower().strip()
        if not t:
            return False
        fast_phrases = (
            "open ", "kholo", "volume", "awaz", "brightness", "screen light",
            "gaming mode", "game mode", "valorant mode", "productive mode", "focus mode",
            "work mode", "normal mode", "current mode", "open my playlist", "meri playlist",
            "revo playlist", "screenshot", "ss leke", "screen problem", "chatgpt ko screenshot",
            "security report", "pc secure hai", "virus check", "pc health", "open valorant",
            "open discord", "open youtube", "youtube kholo", "linkedin kholo", "github kholo",
            "gmail kholo", "chatgpt kholo", "play ", "pause music", "resume music", "next song",
            "previous song", "mute", "unmute", "max volume", "internship dhundo", "job dhundo",
            "remote jobs dhundo", "ai engineer jobs dhundo",
        )
        return any(p in t for p in fast_phrases)

    def _fast_command_reply(self, text: str) -> str:
        t = (text or "").lower().strip()
        if "volume" in t or "awaz" in t or t in ("mute", "unmute", "max volume"):
            return "Done Sir, volume command execute kar raha hoon."
        if "brightness" in t or "screen light" in t:
            return "Done Sir, brightness adjust kar raha hoon."
        if "gaming mode" in t or "game mode" in t or "valorant mode" in t:
            return "Gaming Mode Activated."
        if "productive mode" in t or "focus mode" in t or "work mode" in t:
            return "Productive Mode Activated."
        if "playlist" in t:
            return "Done Sir, playlist chala raha hoon."
        if "screenshot" in t or "ss leke" in t or "screen problem" in t:
            return "Screenshot analyze workflow start kar raha hoon."
        if "security" in t or "virus" in t or "pc secure" in t:
            return "Security report bana raha hoon."
        if "open" in t or "kholo" in t:
            return "Opening Sir."
        return "Done Sir."

    def _route_fast_command(self, text: str, source: str = "text", stt_ms: float = 0.0) -> bool:
        start = time.perf_counter()
        if not self._is_fast_command(text):
            self._log_latency(source, stt_ms, (time.perf_counter() - start) * 1000, 0.0, stt_ms + ((time.perf_counter() - start) * 1000))
            return False
        intent_ms = (time.perf_counter() - start) * 1000
        pc_command = _detect_pc_control_locally(text)
        if pc_command and pc_command.get("action") in (
            "volume_set", "volume_increase", "volume_decrease", "mute", "unmute",
            "brightness_set", "brightness_increase", "brightness_decrease"
        ):
            def _run_pc_fast():
                result = computer_settings(parameters=pc_command, response=None, player=self.ui)
                self.ui.write_log(f"REVO: {str(result)[:500]}")
            threading.Thread(target=_run_pc_fast, daemon=True).start()
            reply = self._fast_command_reply(text)
            self.ui.write_log(f"REVO: {reply}")
            if not self.ui.muted:
                self.speak(reply)
            self._log_latency(source, stt_ms, intent_ms, 0.0, stt_ms + intent_ms)
            return True

        reply = self._fast_command_reply(text)
        self.ui.write_log(f"REVO: {reply}")
        if not self.ui.muted:
            self.speak(reply)
        self._log_latency(source, stt_ms, intent_ms, 0.0, stt_ms + intent_ms)
        self._on_text_command(text, fast_routed=True)
        return True

    def _on_text_command(self, text: str, fast_routed: bool = False):
        command_start = time.perf_counter()
        self._maybe_idle_or_wake_greeting(text)
        normalized_text = (text or "").lower().strip()
        name_update = _detect_name_update(text)
        if name_update:
            self.ui.write_log(f"You: {text}")
            self.ui.write_log(f"REVO: {name_update}")
            if not self.ui.muted:
                self.speak(name_update)
            log_action("user_profile", "updated", {"text": text}, self.ui)
            self._mark_reply_generated("name_update")
            return
        if not fast_routed and self._route_fast_command(text, source="text"):
            return
        personality_direct = handle_companion_text(text, player=self.ui)
        if personality_direct and any(key in normalized_text for key in ("change personality", "professional mode", "friend mode", "motivator mode", "roaster mode", "roast mode")):
            self.ui.write_log(f"You: {text}")
            self.ui.write_log(f"REVO: {personality_direct}")
            log_action("personality", "updated", {"text": text, "result": personality_direct[:200]}, self.ui)
            return

        screenshot_aliases = (
            "ss leke chatgpt par daal",
            "screenshot analyze karo",
            "screen problem bata",
            "chatgpt ko screenshot bhejo",
            "screenshot leke chatgpt par upload karo",
            "screenshot leke chatgpt par daal",
            "screen ka solution batao",
            "screen ka issue check karo",
        )
        if any(alias in normalized_text for alias in screenshot_aliases):
            self.ui.write_log(f"You: {text}")
            self.ui.write_log("REVO: Screenshot le rahi hoon aur ChatGPT par upload kar rahi hoon.")

            def _run_chatgpt_screenshot():
                result = browser_control(
                    parameters={
                        "action": "chatgpt_screen_solution",
                        "prompt": (
                            "Analyze this screenshot and tell me:\n"
                            "1. What issue is visible?\n"
                            "2. What caused it?\n"
                            "3. How to fix it?\n"
                            "4. Step-by-step solution."
                        ),
                    },
                    player=self.ui,
                )
                self.ui.write_log(f"REVO: {result[:1200]}")

            threading.Thread(target=_run_chatgpt_screenshot, daemon=True).start()
            return
        forced_edge_sites = {
            "open youtube": "https://www.youtube.com",
            "youtube kholo": "https://www.youtube.com",
            "open linkedin": "https://www.linkedin.com",
            "linkedin kholo": "https://www.linkedin.com",
            "open github": "https://github.com",
            "github kholo": "https://github.com",
            "open chatgpt": "https://chatgpt.com",
            "chatgpt kholo": "https://chatgpt.com",
            "open gmail": "https://mail.google.com/mail/u/0/#inbox",
            "gmail kholo": "https://mail.google.com/mail/u/0/#inbox",
        }
        forced_url = forced_edge_sites.get(normalized_text)
        if forced_url:
            self.ui.write_log(f"You: {text}")
            self.ui.write_log("REVO: Microsoft Edge ke existing/new tab me open kar rahi hoon.")

            def _run_forced_edge_site():
                log_action("open_website", "requested", {"url": forced_url, "edge_only": True}, self.ui)
                result = browser_control(
                    parameters={"action": "open_website", "url": forced_url},
                    player=self.ui,
                )
                log_action("open_website", "completed", {"url": forced_url, "result": result[:300]}, self.ui)
                self.ui.write_log(f"[website:edge-only] {result[:500]}")

            threading.Thread(target=_run_forced_edge_site, daemon=True).start()
            return

        smart_mode_aliases = {
            "productive mode": "productive_mode",
            "focus mode": "productive_mode",
            "work mode": "productive_mode",
            "gaming mode": "gaming_mode",
            "game mode": "gaming_mode",
            "valorant mode": "gaming_mode",
            "normal mode": "normal_mode",
            "current mode": "current_mode",
        }
        smart_mode_action = smart_mode_aliases.get(normalized_text)
        if smart_mode_action:
            self.ui.write_log(f"You: {text}")

            def _run_smart_mode():
                result = smart_modes(parameters={"action": smart_mode_action}, player=self.ui)
                self.ui.write_log(f"REVO: {result}")

            threading.Thread(target=_run_smart_mode, daemon=True).start()
            return

        job_hunter_aliases = (
            "internship dhundo",
            "job dhundo",
            "remote jobs dhundo",
            "ai engineer jobs dhundo",
        )
        if any(alias in normalized_text for alias in job_hunter_aliases):
            self.ui.write_log(f"You: {text}")
            self.ui.write_log("REVO: Job Hunter Mode start kar rahi hoon. LinkedIn, Wellfound, Internshala aur Indeed check karungi.")

            def _run_job_hunter():
                result = job_mode(parameters={"action": "search", "query": text, "location": "India"}, player=self.ui)
                self.ui.write_log(f"REVO: {result[:1400]}")
                log_action("job_mode", "completed", {"query": text, "result": result[:500]}, self.ui)

            threading.Thread(target=_run_job_hunter, daemon=True).start()
            return

        security_aliases = (
            "pc secure hai",
            "virus check karo",
            "security report",
        )
        if any(alias in normalized_text for alias in security_aliases):
            self.ui.write_log(f"You: {text}")
            self.ui.write_log("REVO: Security report bana rahi hoon. Kuch delete/quarantine nahi karungi.")

            def _run_security_report():
                action = "virus_scan" if "virus" in normalized_text else "security"
                result = pc_health_scan(parameters={"action": action}, player=self.ui)
                self.ui.write_log(f"REVO: {result[:1600]}")
                log_action("pc_health_scan", "completed", {"action": action, "result": result[:500]}, self.ui)

            threading.Thread(target=_run_security_report, daemon=True).start()
            return

        if normalized_text == "companion mode":
            self.ui.write_log(f"You: {text}")
            result = emotional_companion(parameters={"action": "mode", "mode": "friend", "text": text}, player=self.ui)
            self.ui.write_log(f"REVO: {result}")
            return

        if normalized_text.startswith("yaad rakho") or normalized_text.startswith("remember "):
            self.ui.write_log(f"You: {text}")
            result = remember_text(text)
            self.ui.write_log(f"REVO: {result}")
            log_action("memory_system", "remembered", {"text": text}, self.ui)
            return

        if "kal maine kya bola" in normalized_text or "kal kya bola tha" in normalized_text:
            self.ui.write_log(f"You: {text}")
            result = yesterday_text()
            self.ui.write_log(f"REVO: {result}")
            return

        if "mera goal kya hai" in normalized_text or "mere goals kya" in normalized_text:
            self.ui.write_log(f"You: {text}")
            result = goals_text()
            self.ui.write_log(f"REVO: {result}")
            return
        if self._pending_media_download and normalized_text in ("yes", "haan", "ha", "confirm", "confirmed", "permission hai", "right hai", "kar do"):
            pending = dict(self._pending_media_download)
            pending["permissionConfirmed"] = True
            self._pending_media_download = None
            self.ui.write_log(f"You: {text}")
            self.ui.write_log("REVO: Permission confirmed. Media download start kar rahi hoon.")

            def _run_media_download():
                result = media_download(parameters=pending, player=self.ui)
                self.ui.write_log(f"REVO: {result[:900]}")

            threading.Thread(target=_run_media_download, daemon=True).start()
            return

        media_request = detect_media_request(text)
        if media_request:
            self._pending_media_download = media_request
            self.ui.write_log(f"You: {text}")
            result = media_download(parameters=media_request, player=self.ui)
            self.ui.write_log(f"REVO: {result}")
            return

        companion_reply = handle_companion_text(text, player=self.ui)
        if companion_reply:
            self.ui.write_log(f"You: {text}")
            self.ui.write_log(f"REVO: {companion_reply}")
            log_action("emotional_companion", "completed", {"text": text, "result": companion_reply[:300]}, self.ui)
            return

        learn_match = re.search(
            r"(?:remember this command[: ]*)?(.+?)\s+(?:means|ka matlab|matlab)\s+(.+)",
            text or "",
            re.I,
        )
        if learn_match and any(word in (text or "").lower() for word in ("remember", "matlab", "means")):
            wrong = learn_match.group(1).strip(" :")
            correct = learn_match.group(2).strip(" .")
            self.ui.write_log(f"You: {text}")
            result = command_learning(parameters={"action": "remember", "wrong": wrong, "correct": correct}, player=self.ui)
            self.ui.write_log(f"REVO: {result}")
            log_action("command_learning", "completed", {"wrong": wrong, "correct": correct}, self.ui)
            return

        learned = find_learned_command(text)
        if learned and learned.get("correct") and learned.get("correct").lower().strip() != (text or "").lower().strip():
            corrected = learned["correct"]
            self.ui.write_log(f"You: {text}")
            self.ui.write_log(f"REVO: Learned command matched. Running: {corrected}")
            self._on_text_command(corrected)
            return

        target = _extract_open_target(text)
        if target:
            resolved_app = resolve_installed_app(target)
            if resolved_app:
                self.ui.write_log(f"You: {text}")
                reply = f"Opening {resolved_app.get('name') or target}."
                self.ui.write_log(f"REVO: {reply}")

                def _run_app():
                    log_action("open_app", "requested", {"target": target}, self.ui)
                    ok = launch_resolved_app(resolved_app, target)
                    log_action("open_app", "completed" if ok else "failed", {"target": target}, self.ui)
                    self.ui.write_log(f"[app:{target}] {'launched' if ok else 'launch failed'}")
                    if ok:
                        msg = app_context_message(target)
                        if msg:
                            self.ui.write_log(f"REVO: {msg}")

                threading.Thread(target=_run_app, daemon=True).start()
                return

        shortcut = _detect_personal_shortcut(text)
        if shortcut:
            self.ui.write_log(f"You: {text}")
            self.ui.write_log(f"REVO: {shortcut['reply']}")

            def _run_shortcut():
                log_action("personal_shortcut", "requested", {"key": shortcut["key"], "url": shortcut["url"]}, self.ui)
                result = browser_control(
                    parameters={
                        "action": "open_youtube_playlist",
                        "url": shortcut["url"],
                    },
                    player=self.ui,
                )
                log_action("personal_shortcut", "completed", {"key": shortcut["key"]}, self.ui)
                self.ui.write_log(f"[shortcut:{shortcut['key']}] {result[:400]}")

            threading.Thread(target=_run_shortcut, daemon=True).start()
            return

        if target:
            website = _known_website_url(target)
            if website:
                self.ui.write_log(f"You: {text}")
                self.ui.write_log(f"REVO: Opening {target} in Microsoft Edge.")

                def _run_website():
                    log_action("open_website", "requested", {"target": target, "url": website}, self.ui)
                    result = browser_control(
                        parameters={"action": "open_website", "url": website},
                        player=self.ui,
                    )
                    log_action("open_website", "completed", {"target": target, "url": website}, self.ui)
                    self.ui.write_log(f"[website:{target}] {result[:400]}")

                threading.Thread(target=_run_website, daemon=True).start()
                return

        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        clean = str(text or "").strip()
        if not clean:
            return
        self._latest_response_text = clean
        self._debug_stage("TTS START", f"queued len={len(clean)}")
        try:
            self._speech_queue.put_nowait(clean)
            self._update_tts_debug_panel()
        except Exception as exc:
            self._debug_stage("TTS FAILED", "speech_queue put", exc)
            self._set_voice_status(tts="failed")
            try:
                self.ui.write_log(f"REVO TEXT: {clean}")
            except Exception:
                pass

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _handle_quota_error(self, error: Exception):
        if self._quota_alerted:
            return
        self._quota_alerted = True
        msg = (
            "Gemini API quota/rate limit lag raha hai. "
            "API key setup portal khol raha hoon; new Gemini API key paste kar do."
        )
        print(f"[REVO] Gemini quota warning: {error}")
        self.ui.write_log(f"SYS: {msg}")
        try:
            self.ui.open_api_key_portal(msg)
        except Exception as portal_error:
            print(f"[REVO] Could not open API key portal: {portal_error}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        self._debug_stage("AI REQUEST START", "build Live config")
        self._set_voice_status(ai="running")
        memory     = self._cached_memory()
        mem_str    = format_memory_for_prompt(memory)
        profile = _load_user_profile()
        sys_prompt = _load_system_prompt()
        sys_prompt = sys_prompt.replace("{{USER_NAME}}", str(profile.get("user_name") or "Sir"))
        sys_prompt = sys_prompt.replace("{{ASSISTANT_NAME}}", "REVO")
        sys_prompt = sys_prompt.replace("{{CREATOR_NAME}}", CREATOR_NAME)
        sys_prompt = sys_prompt.replace("{{CREATOR_LINKEDIN_URL}}", CREATOR_LINKEDIN_URL)

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n"
            f"Fast Response Mode: normal chat replies should be 1-2 short sentences, about 120 tokens max unless the user asks for detail.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        self._debug_stage("AI REQUEST SUCCESS", "config ready")
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[REVO] tool {name}  {args}")
        self._debug_stage("INTENT DETECTED", f"tool={name} args={args}")
        log_action(name, "requested", args, self.ui)
        self.ui.set_state("THINKING")
        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â°ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¸ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â‚¬Å¾Ã‚Â¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¾ save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_creator_linkedin":
                url = CREATOR_LINKEDIN_URL
                await loop.run_in_executor(None, lambda: browser_control(parameters={"action": "go_to", "url": url}, player=self.ui))
                self.ui.write_log(f"REVO: Opening Aadarsh Mishra's LinkedIn profile.")
                result = f"Opened in Microsoft Edge: {url}"

            elif name == "open_world_news_monitor":
                url = "https://www.worldmonitor.app/?lat=20.0000&lon=0.0000&zoom=1.00&view=global&timeRange=7d&layers=conflicts%2Cbases%2Chotspots%2Cnuclear%2Csanctions%2Cweather%2Ceconomic%2Cwaterways%2Coutages%2Cmilitary%2Cnatural%2CiranAttacks"
                await loop.run_in_executor(None, lambda: browser_control(parameters={"action": "go_to", "url": url}, player=self.ui))
                self.ui.write_log("REVO: Opening live world news monitor.")
                result = f"Opened in Microsoft Edge: {url}"

            elif name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."
                msg = app_context_message(args.get("app_name", ""))
                if msg:
                    self.ui.write_log(f"REVO: {msg}")

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                action = str(args.get("action", "")).lower().strip()
                target = str(args.get("url") or args.get("query") or args.get("text") or "").strip()
                if action in ("go_to", "open_website", "search") and target:
                    resolved_app = resolve_installed_app(target)
                    if resolved_app:
                        launched = await loop.run_in_executor(
                            None,
                            lambda: launch_resolved_app(resolved_app, target)
                        )
                        result = (
                            f"Opening {resolved_app.get('name') or target}."
                            if launched else
                            f"Could not open {target}."
                        )
                        return types.FunctionResponse(
                            id=fc.id, name=name,
                            response={"result": result}
                        )
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."


            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None},
                    daemon=True
                ).start()
                result = "Vision module activated. Stay completely silent ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â vision module will speak directly."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "pc_health_scan":
                r = await loop.run_in_executor(None, lambda: pc_health_scan(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "command_learning":
                r = await loop.run_in_executor(None, lambda: command_learning(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "routine_assistant":
                r = await loop.run_in_executor(None, lambda: routine_assistant(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "job_mode":
                r = await loop.run_in_executor(None, lambda: job_mode(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "safe_shopping":
                r = await loop.run_in_executor(None, lambda: safe_shopping(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "ai_brain_status":
                r = await loop.run_in_executor(None, lambda: ai_brain_status(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "emotional_companion":
                r = await loop.run_in_executor(None, lambda: emotional_companion(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "media_download":
                r = await loop.run_in_executor(None, lambda: media_download(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "smart_modes":
                r = await loop.run_in_executor(None, lambda: smart_modes(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."
            elif name == "shutdown_revo":
                if not is_confirmed(args):
                    result = confirmation_required("shutdown_revo")
                    log_action(name, "blocked_confirmation_required", args, self.ui)
                    if not self.ui.muted:
                        self.ui.set_state("LISTENING")
                    return types.FunctionResponse(
                        id=fc.id, name=name,
                        response={"result": result}
                    )
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")

                def _shutdown():
                    import time, sys, os
                    time.sleep(1)
                    os._exit(0)

                threading.Thread(target=_shutdown, daemon=True).start()
            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            self._debug_stage("INTENT FAILED", name, e)
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[REVO] ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â°ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¸ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¤ {name} ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â‚¬Å¾Ã‚Â¢ {str(result)[:80]}")
        log_action(name, "completed", {"result": str(result)[:500]}, self.ui)
        self._mark_reply_generated("tool_response")

        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            try:
                await self.session.send_realtime_input(media=msg)
            except Exception as exc:
                self._debug_stage("STT FAILED", "send realtime input", exc)
                self._set_voice_status(voice="failed")
                raise

    async def _listen_audio(self):
        self._debug_stage("STT START", "microphone listener starting")
        self._set_voice_status(voice="running")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                REVO_speaking = self._is_speaking
            if not REVO_speaking and not self.ui.muted:
                data = indata.tobytes()
                self._mark_user_voice_activity(data)
                loop.call_soon_threadsafe(
                    self._enqueue_realtime_audio,
                    {"data": data, "mime_type": "audio/pcm"}
                )

        try:
            input_device = _get_input_device()
            mic_name = _safe_audio_device_name(input_device, input_device=True)
            print(f"[REVO] Using microphone: {mic_name}")
            try:
                self.ui.write_log(f"REVO: Operating microphone: {mic_name}")
            except Exception:
                pass
            with sd.InputStream(
                device=input_device,
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                self._debug_stage("STT SUCCESS", "microphone stream open")
                self._set_voice_status(voice="running")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            self._debug_stage("STT FAILED", "microphone listener", e)
            self._set_voice_status(voice="failed")
            raise

    async def _receive_audio(self):
        self._debug_stage("AI REQUEST START", "receive loop started")
        self._set_voice_status(ai="running")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        self._last_audio_start_ts = time.time()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            self.set_speaking(True)
                            self._debug_stage("TTS START", "output transcription received")
                            self._set_voice_status(tts="running")
                            txt = sc.output_transcription.text.strip()
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = sc.input_transcription.text.strip()
                            if txt:
                                if not in_buf:
                                    self._last_stt_start_ts = time.perf_counter()
                                    try:
                                        if hasattr(self.ui, "set_user_voice_active"):
                                            self.ui.set_user_voice_active(True)
                                    except Exception:
                                        pass
                                    self._debug_stage("STT START", "transcription chunk started")
                                in_buf.append(txt)

                        if sc.turn_complete:
                            self.set_speaking(False)

                            full_in = " ".join(in_buf).strip()
                            stt_ms = 0.0
                            if full_in and self._last_stt_start_ts:
                                stt_ms = (time.perf_counter() - self._last_stt_start_ts) * 1000
                            if full_in:
                                self._debug_stage("STT SUCCESS", full_in[:180])
                                self._set_voice_status(voice="running")
                                self._start_reply_watch("intent_or_ai")
                                self.ui.write_log(f"You: {full_in}")
                                if self._route_fast_command(full_in, source="voice", stt_ms=stt_ms):
                                    self._mark_reply_generated("fast_command")
                                    out_buf = []
                                    in_buf = []
                                    try:
                                        while not self.audio_in_queue.empty():
                                            self.audio_in_queue.get_nowait()
                                    except Exception:
                                        pass
                                    continue
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self._debug_stage("AI REQUEST SUCCESS", full_out[:180])
                                self._debug_stage("TTS SUCCESS", "audio/text output completed")
                                self._set_voice_status(ai="running", tts="running")
                                self.ui.write_log(f"REVO: {full_out}")
                                self._mark_reply_generated("ai_response")
                            out_buf = []

                            if full_in and len(full_in) > 5:
                                threading.Thread(
                                    target=_update_memory_async,
                                    args=(full_in, full_out),
                                    daemon=True
                                ).start()

                    if response.tool_call:
                        self._debug_stage("INTENT DETECTED", "tool_call received")
                        self._set_voice_status(ai="running")
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[REVO] ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â°ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¸ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¾ {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )

        except Exception as e:
            self._debug_stage("AI REQUEST FAILED", "receive loop", e)
            self._set_voice_status(ai="failed")
            traceback.print_exc()
            if _is_gemini_quota_error(e):
                self._handle_quota_error(e)
            fallback = "Revo, AI backend me issue aa gaya hai. Main recover kar rahi hoon."
            try:
                self.ui.write_log(f"REVO: {fallback}")
            except Exception:
                pass
            raise

    async def _play_audio(self):
        self._debug_stage("TTS START", "audio playback starting")
        loop = asyncio.get_event_loop()

        output_device = _get_output_device()
        print(f"[REVO] Using speaker: {_safe_audio_device_name(output_device, input_device=False)}")

        stream = sd.RawOutputStream(
            device=output_device,
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()
        self._debug_stage("TTS SUCCESS", "audio output stream open")
        self._set_voice_status(tts="running")
        try:
            while True:
                chunk = await self.audio_in_queue.get()
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
                self._last_audio_write_ts = time.time()
        except Exception as e:
            self._debug_stage("TTS FAILED", "audio playback", e)
            self._set_voice_status(tts="failed")
            self._restart_tts_engine("audio playback crashed")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        while True:
            try:
                print("[REVO] ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â°ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¸ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚ÂÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ Connecting...")
                self.ui.set_state("THINKING")
                client = genai.Client(
                    api_key=_get_api_key(),
                    http_options={"api_version": "v1beta"}
                )
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)

                    print("[REVO] ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦ Connected.")
                    self.ui.set_state("LISTENING")
                    self._set_voice_status(voice="running", ai="running", tts="running", memory="running")
                    self.ui.write_log("SYS: REVO online.")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._voice_watchdog())
                    tg.create_task(self._tts_heartbeat())
                    tg.create_task(self._speech_queue_worker())
                    tg.create_task(self._delayed_startup_greeting())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    
            except Exception as e:
                self._debug_stage("AI REQUEST FAILED", "session/run loop", e)
                self._set_voice_status(voice="failed", ai="failed", tts="failed")
                fallback = "Revo, AI backend me issue aa gaya hai. Main recover kar rahi hoon."
                try:
                    self.ui.write_log(f"REVO: {fallback}")
                except Exception:
                    pass
                traceback.print_exc()
                if _is_gemini_quota_error(e):
                    self._handle_quota_error(e)
                    await asyncio.to_thread(self.ui.wait_for_api_key)
                    self._quota_alerted = False
            self.set_speaking(False)
            self.ui.set_state("THINKING")
            print("[REVO] ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â°ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¸ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¾ Reconnecting in 3s...")
            await asyncio.sleep(3)

def main():
    ui = REVOUI("face.png")

    def runner():
        ui.wait_for_api_key()
        REVO = REVOLive(ui)
        try:
            asyncio.run(REVO.run())
        except KeyboardInterrupt:
            print("\nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â°ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¸ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚ÂÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â´ Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()


if __name__ == "__main__":
    main()







