"""Prepare a new release by bumping the version and updating history.

Usage::

    python -m release.prepare [major|minor|patch]

If no argument is provided the ``patch`` level is assumed.  The script will:

  * ensure the git working tree is clean
  * bump the version in ``pyproject.toml``
  * append a templated entry to ``HISTORY.md``
  * stage the modified files and commit with a sensible message

This mirrors step 1-3 in ``release/README.md`` but automates the mechanical
parts.  The resulting commit should be pushed and tagged separately (see
``push.py``).
"""

from __future__ import annotations

import sys

from release.shared import (
    bump_version,
    append_history,
    ensure_git_clean,
    git_tag,
)


def main() -> None:
    level = sys.argv[1] if len(sys.argv) > 1 else "patch"
    if level not in ("major", "minor", "patch"):
        print("usage: prepare.py [major|minor|patch]")
        sys.exit(1)

    ensure_git_clean()
    new_ver = bump_version(level)
    append_history(f"prepare for {new_ver}")

    # stage and commit
    msg = f"Bump version to {new_ver}"
    subprocess = __import__("subprocess")
    subprocess.run(["git", "add", "pyproject.toml", "HISTORY.md"], check=True)
    subprocess.run(["git", "commit", "-m", msg], check=True)

    # tag the commit as an optional convenience
    git_tag(new_ver)


if __name__ == "__main__":
    main()
