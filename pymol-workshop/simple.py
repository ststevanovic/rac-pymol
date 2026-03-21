"""simple.py — RaC PyMOL toolkit demo (Python template).

Outputs (all under .rendering/):
  {ref}_staged.png  — reference molecule, styled
  {ref}_staged.json — snapshot for diff / debugging
  {ref}_staged.pse  — PyMOL session for inspection
  {ref}_applied.png — reference re-applied from DB (round-trip check)
  {subj}_applied.png — each subject with reference scene applied

Run from rac_pymol/:
    python pymol-templates/simple.py
"""
import json
import datetime as _dt
import json as _json
import sqlite3 as _sq
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pymol  # noqa: E402
pymol.finish_launching(["pymol", "-cq"])
from pymol import cmd  # noqa: E402
import pymol.setting as ps  # noqa: E402

from pymol_backend.adapter import PyMOLController  # noqa: E402
from pymol_backend.driver import apply_scene  # noqa: E402

OUTPUT_DIR = ROOT / ".rendering"
OUTPUT_DIR.mkdir(exist_ok=True)

_source_meta = {
    "template": Path(__file__).name,
    "template_path": str(Path(__file__).relative_to(ROOT.parent)),
    "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
}
with open(OUTPUT_DIR / ".source.json", "w") as _f:
    _json.dump(_source_meta, _f, indent=2)

ctrl = PyMOLController()

# Wipe DB so each run starts clean — no stale scenes from previous runs
_db_path = ctrl._db.path
_con = _sq.connect(str(_db_path))
_con.execute("DELETE FROM scene_objects")
_con.execute("DELETE FROM scenes")
_con.commit()
_con.close()
print(f"[simple.py] DB wiped: {_db_path}")

# ── inputs ────────────────────────────────────────────────────────
INPUTS = [
    ROOT / "tests" / "data" / "1pdb.cif",
    ROOT / "tests" / "data" / "1lp3.cif",
    ROOT / "tests" / "data" / "9ax6.cif",
]

_TRACKED_SETTINGS = ["cartoon_color", "sphere_color", "stick_color", "surface_color"]


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


def snapshot() -> dict:
    session = cmd.get_session()
    name_list = ps.get_name_list()
    global_settings = {n: cmd.get_setting_text(n) for n in name_list}
    view_matrix = list(cmd.get_view())
    camera_position = list(cmd.get_position())
    viewport = list(session.get("main", []))
    objects: dict = {}
    for obj in cmd.get_names("objects"):
        obj_settings = []
        for sname in _TRACKED_SETTINGS:
            try:
                idx = name_list.index(sname)
                typ, (val,) = cmd.get_setting_tuple(sname, obj)
                _, (gval,) = cmd.get_setting_tuple(sname)
                if val != gval:
                    obj_settings.append([idx, typ, val])
            except Exception:
                pass
        try:
            vis = cmd.get_vis()
            visibility = vis[0].get(obj) if vis else None
        except Exception:
            visibility = None
        objects[obj] = {
            "object_settings": obj_settings or None,
            "visibility": visibility,
            "color_index": cmd.get_object_color_index(obj),
            "object_matrix": list(cmd.get_object_matrix(obj)),
        }
    return {
        "global_settings": global_settings,
        "view_matrix": view_matrix,
        "camera_position": camera_position,
        "viewport": viewport,
        "objects": objects,
    }


# ── main loop ─────────────────────────────────────────────────────
REFERENCE = INPUTS[0]   # staged here — scene stored to DB
SUBJECTS  = INPUTS[1:]  # only loaded + applied

# ── Phase A: reference molecule — loaded / staged / ingested ──────
ref_tag = REFERENCE.stem
scene_name = f"simple_{ref_tag}"
print(f"\n[simple.py] REFERENCE ── {ref_tag} ─────────────────────")

cmd.reinitialize()
cmd.load(str(REFERENCE), ref_tag)
cmd.viewport(800, 600)

ref_loaded_png = OUTPUT_DIR / f"{ref_tag}_loaded.png"
cmd.png(str(ref_loaded_png), width=800, height=600, ray=1)
print(f"  \u2713 {ref_loaded_png.name}")

style(ref_tag)

ref_staged_png  = OUTPUT_DIR / f"{ref_tag}_staged.png"
ref_staged_json = OUTPUT_DIR / f"{ref_tag}_staged.json"
ref_staged_pse  = OUTPUT_DIR / f"{ref_tag}_staged.pse"

cmd.png(str(ref_staged_png), width=800, height=600, ray=1)
print(f"  ✓ {ref_staged_png.name}")

doc = snapshot()
with open(ref_staged_json, "w") as f:
    json.dump(doc, f, indent=2)
print(f"  ✓ {ref_staged_json.name}")

cmd.save(str(ref_staged_pse))
print(f"  ✓ {ref_staged_pse.name}")

scene_id = ctrl.ingest_scene(name=scene_name)
print(f"  ✓ ingested → scene_id={scene_id}  name={scene_name}")

# also save an applied render of the reference itself for completeness
cmd.reinitialize()
cmd.load(str(REFERENCE), ref_tag)
cmd.viewport(800, 600)
apply_scene(scene_name=scene_name)
ref_applied_png  = OUTPUT_DIR / f"{ref_tag}_applied.png"
ref_applied_json = OUTPUT_DIR / f"{ref_tag}_applied.json"
cmd.png(str(ref_applied_png), width=800, height=600, ray=1)
print(f"  ✓ {ref_applied_png.name}")
doc = snapshot()
with open(ref_applied_json, "w") as f:
    json.dump(doc, f, indent=2)
print(f"  ✓ {ref_applied_json.name}")

# ── Phase B: subject molecules — loaded / applied only ───────────
for cif in SUBJECTS:
    tag = cif.stem
    print(f"\n[simple.py] SUBJECT ── {tag} ──────────────────────────")

    cmd.reinitialize()
    cmd.load(str(cif), tag)
    cmd.viewport(800, 600)

    apply_scene(scene_name=scene_name)   # same scene as reference

    applied_png = OUTPUT_DIR / f"{tag}_applied.png"
    cmd.png(str(applied_png), width=800, height=600, ray=1)
    print(f"  ✓ {applied_png.name}")

print("\n[simple.py] Done.")
cmd.quit()
