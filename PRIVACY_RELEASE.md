# REVO OS Public Release Privacy Checklist

Before uploading to GitHub, do **not** publish your working folder directly if it contains runtime data.

## Safe Release Command

```cmd
cd /d "C:\path\to\Revo-OS-main"
python scripts\prepare_github_release.py
```

Upload the generated folder:

```text
REVO_OS_GITHUB_RELEASE_SAFE
```

## Never Commit

- `config/api_keys.json`
- `config/user_profile.json`
- `config/personal_shortcuts.json`
- `memory/*.json`
- `runtime/`
- `logs/`
- screenshots
- Edge/ChatGPT browser profile data
- `*.log`

## Safe Files To Commit

- Source code: `main.py`, `ui.py`, `actions/`, `memory/` Python files
- Examples: `config/*.example.json`
- Install scripts and docs
- `requirements.txt`

## Creator Lock

REVO creator identity is intentionally hard-coded and should not be replaced in public forks:

- Original Creator: Aadarsh Mishra
- Original Creator LinkedIn: `https://www.linkedin.com/in/aadarsh-mishra-4aa400395`
- Locked source file: `core/creator_identity.py`

Users can change only their own local display name in `config/user_profile.json`. Creator attribution is locked in `core/creator_identity.py`; forks should preserve the original creator name and LinkedIn attribution.
