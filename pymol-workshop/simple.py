"""simple.py — RaC PyMOL toolkit demo (Python template).

Outputs (all under .rendering/):
  {ref}_loaded.png  — reference molecule, before style
  {ref}_staged.png  — reference molecule, styled
  {ref}_staged.pse  — PyMOL session for inspection
  {ref}_applied.png — reference re-applied from DB (round-trip check)

Run from rac_pymol/:
    python pymol-workshop/simple.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pymol  # noqa: E402
pymol.finish_launching(["pymol", "-cq"])
from pymol import cmd  # noqa: E402

from pymol_backend.driver import SceneSession  # noqa: E402

# ── style ──────────────────────────────────────────────────────────
def style(obj: str) -> None:
    cmd.hide("everything", obj)
    cmd.show("cartoon", f"({obj}) and polymer")
    cmd.show("spheres", f"({obj}) and organic")
    cmd.show("spheres", f"({obj}) and inorganic")
    cmd.color("slate", f"({obj}) and polymer")
    cmd.bg_color("white")
    cmd.set("ray_opaque_background", "off")
    cmd.set("ambient", 0.2)
    cmd.set("specular", 0.5)
    cmd.set("shininess", 10)
    cmd.set("cartoon_transparency", 0.0)
    cmd.zoom(obj)
    cmd.orient(obj)


# ── main ──────────────────────────────────────────────────────────
OUTPUT_DIR = ROOT / ".rendering"
INPUTS = [
    ROOT / "tests" / "data" / "1pdb.cif",
]
REFERENCE = INPUTS[0]
ref_tag   = REFERENCE.stem

session = SceneSession(OUTPUT_DIR, f"simple_{ref_tag}", "simple.py")
session.run_reference(ref_tag, REFERENCE, style)
session.apply_reference(ref_tag, REFERENCE)

print("\n[simple.py] Done.")
cmd.quit()
