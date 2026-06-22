# REVO OS Release Checklist

Use this before uploading/pushing to GitHub.

## 1. Clean Local Secrets

Make sure these files are NOT committed:

```text
config/api_keys.json
memory/long_term.json
memory/memory.json
logs/
runtime/
.venv/
*.log
*.err.log
```

They are listed in `.gitignore`, but always check before commit.

## 2. Run Validation

```cmd
python -m py_compile main.py ui.py setup.py revo_doctor.py
python -m json.tool config\api_keys.example.json
python -m json.tool config\personal_shortcuts.example.json
python revo_doctor.py
```

Warnings about Python 3.14 are okay on the developer machine. For public users, recommend Python 3.11/3.12.

## 3. Test Fresh Install Flow

From a clean folder or a copied repo:

```cmd
install_windows.bat
notepad config\api_keys.json
start_revo.bat
```

Confirm:

- UI opens
- API setup works
- Mic status is visible
- Voice status panel is visible
- `logs/revo_debug.log` is created
- `security report` command works
- `open youtube` opens Edge tab
- `volume 50` works

## 4. Git Commands

```cmd
git init
git add .
git status
```

Before commit, verify `git status` does NOT show:

```text
config/api_keys.json
logs/
runtime/
memory/long_term.json
memory/memory.json
```

Then:

```cmd
git commit -m "Prepare REVO OS local beta"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/REVO-OS.git
git push -u origin main
```

## 5. GitHub Description

Suggested repo description:

```text
REVO OS Local Beta - Windows-first personal AI desktop assistant with voice, PC controls, Edge automation, memory, security reports, and companion modes.
```

## 6. Public Safety Note

Add this to the GitHub repo description or release notes:

```text
This is a local beta. Review code before use. Do not share API keys. REVO OS can control apps, browser tabs, volume, brightness, screenshots, and local files with confirmation gates for sensitive actions.
```