"""batch.py — RaC PyMOL batch pipeline.

Each run produces a timestamped subdir under .rendering/random/<YYYYMMDD_HHMMSS>/
containing loaded/staged/applied PNGs for the reference (1pdb) plus applied PNGs
for each subject, and a slides.html via slides.py.  A symlink latest.html always
points at the most recent run.

Structures are sourced from tests/data first, then downloaded from RCSB and
cached under .rendering/_cif_cache/.

Run from rac_pymol/:
    python pymol-workshop/batch.py
"""

import datetime as dt
import json
import os
import random
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pymol  # noqa: E402
pymol.finish_launching(["pymol", "-cq"])
from pymol import cmd  # noqa: E402

from pymol_backend.adapter import PyMOLController  # noqa: E402
from pymol_backend.driver import apply_scene  # noqa: E402

# ── config ─────────────────────────────────────────────────────────────────

FETCH_TIMEOUT = 15
RENDER_ROOT   = ROOT / ".rendering"
RANDOM_DIR    = RENDER_ROOT / "random"
CIF_CACHE     = RENDER_ROOT / "_cif_cache"
SLIDES_PY     = RENDER_ROOT / "slides.py"
RCSB_URL      = "https://files.rcsb.org/download/{}.cif"
RCSB_SEARCH   = "https://search.rcsb.org/rcsbsearch/v2/query"

# Category → RCSB entity-type / keyword used in full-text search
PDB_CATEGORIES = {
    "enzyme":        "enzyme catalytic",
    "antibody":      "immunoglobulin antibody",
    "membrane":      "membrane protein",
    "nucleic_acid":  "DNA RNA nucleic acid",
    "virus":         "viral capsid virus",
    "kinase":        "protein kinase",
    "receptor":      "receptor ligand binding",
}

# Pick one category per run (can be overridden via env var BATCH_CATEGORY)
_env_cat = os.environ.get("BATCH_CATEGORY", "")
SELECTED_CATEGORY = _env_cat if _env_cat in PDB_CATEGORIES else random.choice(list(PDB_CATEGORIES.keys()))
N_SUBJECTS = int(os.environ.get("BATCH_N_SUBJECTS", "5"))

RANDOM_DIR.mkdir(parents=True, exist_ok=True)
CIF_CACHE.mkdir(exist_ok=True)


# ── helpers ─────────────────────────────────────────────────────────────────

def query_rcsb_by_category(category: str, n: int = 10) -> list[str]:
    """Return up to *n* PDB IDs matching *category* via RCSB full-text search."""
    keyword = PDB_CATEGORIES.get(category, category)
    payload = json.dumps({
        "query": {
            "type": "terminal",
            "service": "full_text",
            "parameters": {"value": keyword},
        },
        "return_type": "entry",
        "request_options": {
            "paginate": {"start": 0, "rows": n * 3},
            "sort": [{"sort_by": "score", "direction": "desc"}],
        },
    }).encode()
    req = urllib.request.Request(
        RCSB_SEARCH,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            hits = json.loads(resp.read())
        ids = [h["identifier"] for h in hits.get("result_set", [])]
        random.shuffle(ids)
        return ids[:n]
    except Exception as exc:
        print(f"  [WARN]   RCSB search failed for '{category}': {exc}")
        return []


def locate_cif(pdb_id: str, cif_dir: Path | None = None) -> Path | None:
    """Return CIF path: tests/data first, then *cif_dir* (run-local cache),
    then global CIF_CACHE, then download and store in both."""
    local = ROOT / "tests" / "data" / f"{pdb_id.lower()}.cif"
    if local.exists():
        return local

    # run-local timestamped cache dir (preferred store)
    run_cached = (cif_dir / f"{pdb_id.lower()}.cif") if cif_dir else None
    if run_cached and run_cached.exists():
        return run_cached

    global_cached = CIF_CACHE / f"{pdb_id.lower()}.cif"
    if global_cached.exists():
        # copy into run dir as well
        if run_cached:
            run_cached.write_bytes(global_cached.read_bytes())
        return run_cached or global_cached

    url = RCSB_URL.format(pdb_id.upper())
    try:
        print(f"  [fetch]  {url}")
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as resp:
            data = resp.read()
        global_cached.write_bytes(data)
        if run_cached:
            run_cached.write_bytes(data)
        return run_cached or global_cached
    except Exception as exc:
        print(f"  [WARN]   fetch failed for {pdb_id}: {exc}")
        return None


def write_run_meta(path: Path, meta: dict) -> None:
    """Append / overwrite the run metadata JSON at *path*."""
    path.write_text(json.dumps(meta, indent=2))
    print(f"  [meta]   {path.name} written")


RCSB_ENTRY_URL = "https://www.rcsb.org/structure/{}"


def rcsb_entry_url(pdb_id: str) -> str:
    """Return the canonical RCSB entry URL for *pdb_id* (hardcoded template)."""
    return RCSB_ENTRY_URL.format(pdb_id.upper())



# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ctrl = PyMOLController()
    print(f"[batch] DB: {ctrl._db.path}")

    # Timestamped output dir for this run
    run_tag = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RANDOM_DIR / run_tag
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[batch] run dir: {run_dir}")

    REF = "1pdb"
    _source_meta = {
        "template": Path(__file__).name,
        "template_path": str(Path(__file__).relative_to(ROOT.parent)),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "category": SELECTED_CATEGORY,
        "rcsb_urls": {REF.upper(): rcsb_entry_url(REF)},
    }
    source_path = run_dir / ".source.json"
    source_path.write_text(json.dumps(_source_meta, indent=2))
    ref_cif = locate_cif(REF)
    if ref_cif is None:
        print(f"[batch] ERROR: cannot locate reference CIF {REF}")
        cmd.quit()
        return

    print(f"\n[batch] REFERENCE ── {REF}")
    scene_name = f"batch_{REF}"

    # Check whether the scene already exists in DB
    existing = [s for s in ctrl.list_scenes() if s["name"] == scene_name]
    scene_id = existing[-1]["id"] if existing else None

    # Step 1 — loaded (raw default state — always rendered)
    cmd.reinitialize()
    cmd.load(str(ref_cif), REF)
    cmd.viewport(800, 600)
    cmd.png(str(run_dir / f"{REF}_loaded.png"), width=800, height=600, ray=1)
    print(f"  ✓ {REF}_loaded.png  [raw default]")


    print(f"  [db] scene '{scene_name}' found (id={scene_id}) — DB replay only")
    apply_scene(scene_id=scene_id)
    cmd.png(str(run_dir / f"{REF}_applied.png"), width=800, height=600, ray=1)
    print(f"  ✓ {REF}_applied.png  [DB replay only]")

    # ── Phase B: subjects — DB replay only, no style() ───────────────────
    # Every subject is: reinitialize → load CIF → apply_scene from DB → png
    # style() is NEVER called here. The DB owns the visual definition.
    print(f"\n[batch] querying RCSB category '{SELECTED_CATEGORY}' …")
    subject_ids = query_rcsb_by_category(SELECTED_CATEGORY, n=N_SUBJECTS)
    if not subject_ids:
        print("[batch] WARN: no subjects from RCSB, falling back to hardcoded list")
        subject_ids = ["1lp3", "6j6j", "1mbo", "1hew", "1igt"]

    rendered = []
    for pdb_id in subject_ids:
        cif = locate_cif(pdb_id)
        if cif is None:
            continue

        print(f"\n[batch] SUBJECT ── {pdb_id}  [DB replay only]")
        cmd.reinitialize()
        cmd.load(str(cif), pdb_id)
        cmd.viewport(800, 600)
        apply_scene(scene_id=scene_id)   # ← sole source of visual state
        cmd.png(str(run_dir / f"{pdb_id}_applied.png"), width=800, height=600, ray=1)
        print(f"  ✓ {pdb_id}_applied.png")
        rendered.append(pdb_id)

    # Patch source.json with final PDB list and all RCSB URLs
    _source_meta["PDB_codes"] = [REF] + rendered
    for pid in rendered:
        _source_meta["rcsb_urls"][pid.upper()] = rcsb_entry_url(pid)
    source_path.write_text(json.dumps(_source_meta, indent=2))

    cmd.quit()

    # ── Phase C: slides — call slides.py via etl-regression env ─────────
    print("\n[batch] Generating slides …")
    import subprocess
    molecules_arg = ",".join([REF] + rendered)
    result = subprocess.run(
        ["conda", "run", "-n", "etl-regression", "--no-capture-output",
         "python", str(SLIDES_PY), molecules_arg,
         "--output-dir", str(run_dir)],
        check=False,
    )
    if result.returncode != 0:
        print("[batch] WARN: slides.py exited with errors")

    # copy latest.html — real standalone file, not a symlink
    import shutil
    latest = RANDOM_DIR / "latest.html"
    shutil.copy2(run_dir / "slides.html", latest)
    print(f"  [copy]   latest.html ← {run_tag}/slides.html")
    print("[batch] Done.")


if __name__ == "__main__":
    main()
