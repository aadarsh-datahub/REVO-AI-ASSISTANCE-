# REVO OS

REVO OS is a Windows-first personal AI desktop assistant made by **Aadarsh Mishra**. It includes voice conversation, PC controls, Microsoft Edge automation, screenshot helper, memory, Job Hunter, Security Mode, Gaming/Productive modes, companion mode, and a Jarvis-style PyQt interface.

This repo is now prepared for public GitHub release. Local names, API keys, memory, logs, screenshots, browser profiles, and runtime data are ignored and should not be uploaded.

## Recommended System

- Windows 10/11
- Python 3.11 or 3.12 recommended
- Microsoft Edge
- Microphone + speakers/headphones
- Gemini API key
- OpenRouter API key

Python 3.14 can work, but 3.11/3.12 is safer for Windows/audio packages.

## Step-by-Step Install

1. Download or clone the repo.

```cmd
git clone https://github.com/YOUR_USERNAME/REVO-OS.git
cd REVO-OS
```

2. Run the Windows installer.

```cmd
install_windows.bat
```

The installer will:

- create `.venv`
- install Python requirements
- install Playwright browsers
- create `config\api_keys.json`
- ask what REVO should call you
- detect microphones/speakers
- save the selected mic/speaker locally
- tell you which mic REVO will use

3. Add your API keys.

Open:

```cmd
notepad config\api_keys.json
```

Fill:

```json
{
  "gemini_api_key": "PASTE_GEMINI_API_KEY_HERE",
  "openrouter_api_key": "PASTE_OPENROUTER_API_KEY_HERE",
  "os_system": "windows",
  "input_device_name": "",
  "output_device_name": ""
}
```

4. Run health check.

```cmd
python revo_doctor.py
```

5. Start REVO.

```cmd
start_revo.bat
```

Manual start:

```cmd
.venv\Scripts\activate
python main.py
```

## Personalization

Each user gets their own local profile:

```text
config\user_profile.json
```

Users can say:

```text
mera naam Rahul hai
my name is Rahul
```

REVO will use that user’s name locally. The assistant name remains `REVO`.

## Creator Lock

Creator identity is intentionally fixed and should not be replaced in public forks:

- Original Creator: **Aadarsh Mishra**
- Original Creator LinkedIn: https://www.linkedin.com/in/aadarsh-mishra-4aa400395
- Locked source file: `core/creator_identity.py`

If anyone asks `who made you`, REVO replies exactly:

```text
Aadarsh Mishra made me.
```

If anyone asks to open the creator LinkedIn profile, REVO opens the locked creator URL. Local users can change their own name, but creator identity should not be changed.

## Features Kept

- Voice input and Gemini Live voice
- App-first command resolution
- Microsoft Edge-only website automation
- YouTube playback/playlist controls
- Screenshot-to-ChatGPT helper
- Volume and brightness controls
- Gaming Mode
- Productive Mode
- Normal Mode
- PC Scan / Security report
- Job Hunter Mode
- Companion/personality modes
- Local memory system
- Media download with permission confirmation
- TTS/STT watchdog and debug logging

## Useful Commands

```text
open youtube
open linkedin
open github
open gmail
open chatgpt
open valorant
gaming mode
productive mode
normal mode
volume 50
brightness 60
screenshot analyze karo
security report
internship dhundo
companion mode
change personality
mera naam Rahul hai
```

## GitHub Release Safety

Before uploading your current working copy, create a safe release folder:

```cmd
python scripts\prepare_github_release.py
```

Upload/push this generated folder:

```text
REVO_OS_GITHUB_RELEASE_SAFE
```

Do **not** upload local runtime data.

Ignored private files include:

- `config/api_keys.json`
- `config/user_profile.json`
- `config/personal_shortcuts.json`
- `memory/*.json`
- `runtime/`
- `logs/`
- screenshots
- browser profile data
- `*.log`

## Troubleshooting

If install fails:

```cmd
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python -m playwright install
```

If voice/mic is wrong:

1. Run `python setup.py` again.
2. Choose the correct microphone index.
3. Run `python revo_doctor.py` and check the reported REVO microphone.

If voice stops:

- Check `logs\revo_debug.log`
- Restart with `start_revo.bat`
- Confirm Windows microphone permission is enabled

## Project Structure

```text
main.py                      Main app and Gemini Live session
ui.py                        PyQt REVO OS interface
actions/                     PC/browser/job/security/media tools
agent/                       Planner/executor helpers
core/prompt.txt              REVO system prompt
config/*.example.json        Safe sample config files
scripts/prepare_github_release.py  Creates safe upload folder
memory/                      Local memory Python system; JSON memory ignored
logs/                        Runtime debug logs; ignored
runtime/                     Temporary runtime files; ignored
```

## License

Personal/non-commercial use recommended unless you add a license.

## Creator

Made by Aadarsh Mishra.
