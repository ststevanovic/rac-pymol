"""Shared helpers used by the release sub‑commands.

These utilities are intentionally small – the goal is to make the manual
workflow described in ``release/README.md`` easier to automate without
introducing heavyweight dependencies.

Typical usage:

	from release.shared import bump_version, append_history, ensure_git_clean
	bump_version('0.2.0')          # edit pyproject.toml
	append_history('Added new feature X')
	ensure_git_clean()             # raise if git working tree is dirty

The scripts ``prepare.py`` and ``push.py`` import these helpers.
"""

from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path


# --- filesystem constants --------------------------------------------------
ROOT = Path(__file__).parent.parent
PYPROJECT = ROOT / "pyproject.toml"
HISTORY = ROOT / "HISTORY.md"


def _read_pyproject() -> str:
    return PYPROJECT.read_text(encoding="utf-8")


def get_version() -> str:
    """Return the current version string from pyproject.toml."""
    text = _read_pyproject()
    m = re.search(r"^version\s*=\s*[\'\"]([^\'\"]+)[\'\"]", text, re.M)
    if not m:
        raise RuntimeError("unable to locate version in pyproject.toml")
    return m.group(1)


def set_version(new: str) -> None:
    """Update the version field in ``pyproject.toml``.

    The function performs a simple regex replace and writes the file back.
    It does **not** create a git commit; callers are responsible for
    staging/committing the change.
    """
    text = _read_pyproject()
    # use a callable replacement to avoid backreference ambiguity when the
    # new version begins with a digit (``\10`` would otherwise be interpreted
    # as a reference to group 10).
    def _repl(match: re.Match) -> str:
        return f"{match.group(1)}{new}{match.group(3)}"

    out = re.sub(
        r"(^version\s*=\s*[\'\"])([^\'\"]+)([\'\"])",
        _repl,
        text,
        flags=re.M,
    )
    PYPROJECT.write_text(out, encoding="utf-8")


def bump_version(level: str = "patch") -> str:
    """Increment the semantic version string.

    ``level`` may be ``major``, ``minor`` or ``patch``.  The updated
    version is written back to ``pyproject.toml`` and also returned.
    """
    sem = get_version()
    parts = sem.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"current version '{sem}' is not semver-compatible")
    major, minor, patch = map(int, parts)
    if level == "major":
        major += 1
        minor = 0
        patch = 0
    elif level == "minor":
        minor += 1
        patch = 0
    elif level == "patch":
        patch += 1
    else:
        raise ValueError("level must be 'major','minor' or 'patch'")
    new = f"{major}.{minor}.{patch}"
    set_version(new)
    return new


def ensure_history() -> None:
    """Create a HISTORY.md file with header if it doesn't exist."""
    if not HISTORY.exists():
        HISTORY.write_text("# Changelog\n\n", encoding="utf-8")


def append_history(entry: str) -> None:
    """Append a dated entry to ``HISTORY.md`` (creates file if needed)."""
    ensure_history()
    stamp = date.today().isoformat()
    line = f"* {stamp} – {entry.strip()}\n"
    HISTORY.write_text(HISTORY.read_text(encoding="utf-8") + line,
                       encoding="utf-8")


def ensure_git_clean() -> None:
    """Raise ``RuntimeError`` if the git working tree has uncommitted changes."""
    res = subprocess.run(["git", "status", "--porcelain"],
                         capture_output=True,
                         text=True,
                         check=True)
    if res.stdout.strip():
        raise RuntimeError("git working tree is dirty; commit or stash changes")


def git_tag(version: str) -> None:
    """Create a lightweight git tag for the given version."""
    subprocess.run(["git", "tag", f"v{version}"], check=True)


def git_push(tags: bool = False) -> None:
    cmd = ["git", "push"]
    if tags:
        cmd.append("--tags")
    subprocess.run(cmd, check=True)


def create_github_release(version: str, notes: str = "") -> None:
    """Use the GitHub CLI (gh) to create a release.

    This is an optional helper; if ``gh`` is not installed the function
    prints a warning and returns silently.
    """
    try:
        subprocess.run([
            "gh", "release", "create", f"v{version}", "--notes", notes
        ], check=True)
    except FileNotFoundError:
        print("gh CLI not available; skip GitHub release step")

