"""Push a prepared release to remote and optionally create a GitHub release.

This helper implements the final steps described in ``release/README.md``:

  * push current branch and tags to the default remote
  * optionally call ``gh release create`` if the GitHub CLI is installed

Usage::

    python -m release.push

No arguments are necessary; the script reads the version from
``pyproject.toml``.
"""

from __future__ import annotations

# imports at top
from release.shared import get_version, git_push, create_github_release


def main() -> None:
    ver = get_version()
    # push branch and tags
    git_push(tags=False)
    git_push(tags=True)

    # create github release with minimal notes
    create_github_release(ver, notes="See HISTORY.md for details.")


if __name__ == "__main__":
  main()
