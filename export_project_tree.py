from __future__ import annotations

import fnmatch
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES_TXT = ROOT / "files.txt"
ZIP_PATH = ROOT / "REVO_OS_GITHUB_SAFE.zip"

IGNORE_DIRS = {
    ".venv",
    "__pycache__",
    ".git",
    "node_modules",
    "logs",
    "runtime",
    "browser_profiles",
    "screenshots",
}

IGNORE_FILES = {
    Path("config/api_keys.json"),
    Path("config/user_profile.json"),
    Path("config/personal_shortcuts.json"),
    Path("memory/memory.json"),
    Path("memory/long_term.json"),
}

IGNORE_PATTERNS = {
    "*.log",
    "*.err.log",
    "*.pyc",
    "*.pyo",
    "REVO_OS_GITHUB_SAFE.zip",
    "files.txt",
}

FORBIDDEN_NAME_PARTS = {
    "edge_chatgpt_profile",
    "browser_profile",
    "browser_profiles",
    "screenshot",
    "screenshots",
}


def _norm_rel(path: Path) -> Path:
    return Path(*path.relative_to(ROOT).parts)


def _is_ignored(path: Path) -> bool:
    rel = _norm_rel(path)
    parts_lower = {part.lower() for part in rel.parts}

    if parts_lower & {d.lower() for d in IGNORE_DIRS}:
        return True

    if any(part in parts_lower for part in FORBIDDEN_NAME_PARTS):
        return True

    rel_posix = rel.as_posix()
    if rel in IGNORE_FILES or Path(rel_posix) in IGNORE_FILES:
        return True

    # Public exports should include config examples only, never local state/config JSON.
    if rel.parts and rel.parts[0].lower() == "config" and path.suffix.lower() == ".json" and not path.name.endswith(".example.json"):
        return True

    name = path.name
    for pattern in IGNORE_PATTERNS:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_posix, pattern):
            return True

    return False


def _safe_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if _is_ignored(path):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda p: p.relative_to(ROOT).as_posix().lower())


def _tree_lines(files: list[Path]) -> list[str]:
    lines = [f"REVO OS project tree: {ROOT}", ""]
    seen_dirs: set[Path] = set()

    for file_path in files:
        rel = _norm_rel(file_path)
        parent = Path()
        for part in rel.parent.parts:
            parent = parent / part
            if parent not in seen_dirs:
                seen_dirs.add(parent)
                indent = "  " * (len(parent.parts) - 1)
                lines.append(f"{indent}{parent.name}/")
        indent = "  " * len(rel.parent.parts)
        lines.append(f"{indent}{rel.name}")

    return lines


def main() -> int:
    files = _safe_files()

    FILES_TXT.write_text("\n".join(_tree_lines(files)) + "\n", encoding="utf-8")

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            arcname = _norm_rel(file_path).as_posix()
            zf.write(file_path, arcname)

    print("REVO OS safe export complete.")
    print(f"Files listed in: {FILES_TXT}")
    print(f"Safe ZIP created: {ZIP_PATH}")
    print(f"Safe files included: {len(files)}")
    print("")
    print("This export excludes secrets, API keys, local user profile, memory JSON, logs, screenshots, browser profiles, and runtime data.")
    print("")
    print("Next steps:")
    print("- Upload REVO_OS_GITHUB_SAFE.zip to ChatGPT if review is needed.")
    print("- Or unzip REVO_OS_GITHUB_SAFE.zip and push the extracted files to GitHub.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

