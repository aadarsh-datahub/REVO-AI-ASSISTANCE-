# REVO AI ASSISTANCE

## The Ultimate Windows Personal AI Assistant — By Aadarsh Mishra

REVO AI Assistance is a real-time personal AI desktop assistant designed to bring a Jarvis-style experience to Windows. It can listen, understand, respond, remember, automate workflows, control PC settings, open applications, manage browser tasks, analyze screenshots, support productivity, assist with job hunting, and act like a smart companion for daily computer use.

REVO is not just a chatbot. It is a practical AI layer between the user and the operating system. Through natural voice and text commands, REVO can perform direct actions, switch modes, interact with websites, control system settings, manage personal shortcuts, and provide intelligent support with a futuristic desktop interface.

It is built for local-first usage, personal productivity, AI automation, and real desktop control.

---

## Overview

REVO AI Assistance is built to feel like a personal AI companion that lives on your desktop. It combines real-time AI voice interaction, system automation, Microsoft Edge browser control, local memory, emotional companion behavior, security checks, gaming/productive workflows, and privacy-safe setup into one Windows application.

The assistant is designed to understand intent quickly. Common commands such as opening apps, launching websites, changing volume, adjusting brightness, playing music, opening playlists, switching modes, or checking PC health are handled directly without unnecessary AI reasoning. This makes REVO faster and more practical than a normal chat assistant.

Each user can configure their own name, microphone, speaker, API keys, and local profile during setup. Sensitive data stays local and is excluded from the public GitHub export.

---

## Core Capabilities

| Feature | Description |
|---|---|
| Real-time Voice | Voice-based AI conversation using Gemini Live |
| Desktop Control | Open apps, control volume, brightness, media keys, and system workflows |
| Browser Automation | Microsoft Edge-only browsing for YouTube, LinkedIn, GitHub, Gmail, ChatGPT, and more |
| Screenshot Helper | Capture screen and open ChatGPT workflow for screenshot analysis |
| Local Memory | Saves goals, preferences, reminders, and useful user context locally |
| Personal Shortcuts | Custom shortcuts like personal YouTube playlist and user-defined links |
| Gaming Mode | Opens Discord/Riot/Valorant workflow, starts playlist, adjusts volume |
| Productive Mode | Helps focus by reducing distractions and setting a work-ready environment |
| Security Mode | PC health/security report with Defender and firewall checks |
| Job Hunter Mode | Opens LinkedIn, Wellfound, Internshala, and Indeed job searches |
| Companion Mode | Supportive Hinglish companion with mood tracking and check-ins |
| Media Download | yt-dlp based download flow with permission confirmation |
| Privacy Export | Safe GitHub export tool that removes secrets and runtime data |

---

## What Makes REVO Unique

### App-First Command Resolution

REVO does not blindly send every request to AI. It first checks whether the command matches an installed application, personal shortcut, known website, PC control, mode switch, or direct workflow. Only when needed does it use AI reasoning. This makes common actions faster and more reliable.

Priority order:

1. Installed applications
2. Personal shortcuts
3. Known websites
4. AI reasoning
5. Web search as last resort

### Microsoft Edge-Only Browser Mode

REVO is designed to open websites in normal Microsoft Edge tabs instead of popup windows or app-mode windows. This applies to YouTube, LinkedIn, GitHub, Gmail, ChatGPT, Google, WhatsApp, and creator profile links.

### Jarvis-Style Desktop Interface

REVO includes a futuristic PyQt interface with a central radar/orb, voice state display, current task tracking, conversation panel, quick actions, and a dark blue assistant-style theme.

### Smart Modes

REVO includes multiple modes for different workflows:

- Gaming Mode
- Productive Mode
- Normal Mode
- Companion Mode
- Listener Mode
- Friend Mode
- Motivation Mode
- Security Mode

### Local Personalization

During setup, REVO asks what it should call the user and detects available microphones and speakers. It stores this locally in configuration files that are ignored by GitHub.

Users can also say:

```text
mera naam Rahul hai
my name is Rahul
```

REVO will then use that user’s local name.

---

## Safety and Privacy

REVO is designed with strict safety boundaries:

- It does not delete files without confirmation.
- It does not shut down or restart the PC without confirmation.
- It does not enter passwords, OTPs, CVVs, UPI PINs, or payment secrets.
- It does not make payments automatically.
- It does not disable Windows Defender.
- It does not run raw AI-generated PowerShell or CMD commands directly.
- It does not download private/protected media without permission.
- It keeps API keys, memory, logs, screenshots, browser profiles, and user settings local.

The public GitHub export excludes private files such as API keys, local user profile, memory files, logs, runtime data, screenshots, and browser profiles.

---

## Quick Start

### 1. Clone the Repository

```cmd
git clone https://github.com/YOUR_USERNAME/REVO-OS.git
cd REVO-OS
```

### 2. Run the Windows Installer

```cmd
install_windows.bat
```

The installer will:

- create a virtual environment
- install requirements
- install Playwright browsers
- create local config files
- ask what REVO should call you
- detect your microphone and speaker
- save your selected audio devices locally

### 3. Add API Keys

Open:

```cmd
notepad config\api_keys.json
```

Add your keys:

```json
{
  "gemini_api_key": "PASTE_GEMINI_API_KEY_HERE",
  "openrouter_api_key": "PASTE_OPENROUTER_API_KEY_HERE",
  "os_system": "windows",
  "input_device_name": "",
  "output_device_name": ""
}
```

### 4. Run Health Check

```cmd
python revo_doctor.py
```

### 5. Start REVO

```cmd
start_revo.bat
```

Manual start:

```cmd
.venv\Scripts\activate
python main.py
```

---

## Requirements

| Requirement | Details |
|---|---|
| OS | Windows 10/11 recommended |
| Python | Python 3.11 or 3.12 recommended |
| Browser | Microsoft Edge |
| Microphone | Required for voice interaction |
| Speaker/Headphones | Required for voice output |
| API Keys | Gemini API key + OpenRouter API key |

Python 3.14 may work, but Python 3.11/3.12 is recommended for better compatibility with audio and Windows automation packages.

---

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

---

## GitHub Safe Export

Before uploading to GitHub, generate a safe export:

```cmd
python export_project_tree.py
```

This creates:

```text
files.txt
REVO_OS_GITHUB_SAFE.zip
```

The export excludes:

- API keys
- local user profile
- personal shortcuts
- memory files
- logs
- runtime data
- screenshots
- browser profiles
- cache files

Upload the extracted safe ZIP contents to GitHub.

---

## License

This project is released for personal, educational, and portfolio use. Public forks should preserve original creator attribution. Commercial use, resale, or redistribution as a paid product is not permitted without permission from the creator.

---

## Connect with the Creator

| Platform | Link |
|---|---|
| LinkedIn | https://www.linkedin.com/in/aadarsh-mishra-4aa400395 |

---

## Creator

Made by **Aadarsh Mishra**.
