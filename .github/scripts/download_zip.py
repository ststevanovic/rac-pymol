#!/usr/bin/env python3
"""download_zip.py — Package the latest rendered slide deck for download.

Zips `.rendering/random/latest.html` (and the full timestamped run dir it
was copied from) into `.rendering/random/latest.zip`.

Run from rac_pymol/:
    python .github/scripts/download_zip.py
"""

import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
RANDOM_DIR = ROOT / ".rendering" / "random"


def find_latest_run_dir() -> Path | None:
    """Return the most recently created timestamped subdir under RANDOM_DIR."""
    candidates = sorted(
        (d for d in RANDOM_DIR.iterdir() if d.is_dir() and d.name[0].isdigit()),
        key=lambda d: d.name,
    )
    return candidates[-1] if candidates else None


def main() -> None:
    latest_html = RANDOM_DIR / "latest.html"
    if not latest_html.exists():
        print("[download-zip] ERROR: latest.html not found — nothing to package")
        sys.exit(1)

    run_dir = find_latest_run_dir()
    zip_path = RANDOM_DIR / "latest.zip"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Always include the top-level latest.html as the entry point
        zf.write(latest_html, "slides/index.html")
        print(f"  [zip] added slides/index.html  ({latest_html.stat().st_size // 1024} KB)")

        # Include all files from the timestamped run dir if found
        if run_dir:
            for fpath in sorted(run_dir.rglob("*")):
                if fpath.is_file() and fpath.suffix in (".html", ".png", ".json"):
                    arcname = "slides/" + fpath.relative_to(run_dir).as_posix()
                    zf.write(fpath, arcname)
                    print(f"  [zip] added {arcname}")

    size_kb = zip_path.stat().st_size // 1024
    print(f"[download-zip] → {zip_path}  ({size_kb} KB)")


if __name__ == "__main__":
    main()
