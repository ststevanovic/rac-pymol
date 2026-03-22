"""enzyme.py — enzyme style library + DB store.

Stores one scene to DB from the reference molecule (9ax6).
batch.py is the consumer — it reads the scene from DB and applies it.

Run from rac_pymol/:
    python pymol-workshop/enzyme.py
"""
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pymol  # noqa: E402
pymol.finish_launching(["pymol", "-cq"])
from pymol import cmd, util  # noqa: E402

from pymol_backend.driver import SceneSession  # noqa: E402


# ── styling library ───────────────────────────────────────────────────────────

def apply_colors() -> None:
    """Define custom palette colors used by styles."""
    cmd.set_color("light_grey", [0.827, 0.827, 0.827])
    cmd.set_color("LG1", [0.969, 0.812, 0.588])
    cmd.set_color("LG2", [0.886, 0.690, 0.416])
    cmd.set_color("LG3", [0.776, 0.733, 0.788])
    cmd.set_color("LG4", [0.141, 0.627, 0.596])
    cmd.set_color("LG5", [0.357, 0.827, 0.796])


def apply_display_settings() -> None:
    """Apply display-level PyMOL settings."""
    settings = {
        "cartoon_gap_cutoff": 0,
        "seq_view": 1,
        "valence": 0,
        "stick_radius": 0.3,
        "stick_ball": "on",
        "stick_ball_ratio": 1.7,
        # "bg_rgb": "light_gray" custom color
        "bg_rgb": [0.827, 0.827, 0.827],
        "cartoon_fancy_helices": 1,
        "cartoon_side_chain_helper": 1,
        "label_size": 14,
        "label_color": "black",
        "ambient": 0.4,
        "two_sided_lighting": 1,
        "depth_cue": 0,
        "orthoscopic": 1,
    }
    for key, value in settings.items():
        cmd.set(key, value)


def apply_render_settings() -> None:
    """Apply rendering-level PyMOL settings."""
    render_settings = {
        "ray_trace_mode": 0,
        "ray_shadows": 1,
        "ray_trace_gain": 0.1,
        "antialias": 2,
    }
    for key, value in render_settings.items():
        cmd.set(key, value)


def color_protein_chains(obj_name: str) -> None:
    """Split protein chains into separate objects and color them."""
    chains = cmd.get_chains(f"{obj_name} and polymer.protein")
    palette = [
        "red", "green", "blue", "yellow", "cyan", "magenta",
        "orange", "slate", "teal", "violet", "salmon", "lime",
        "pink", "marine", "wheat", "white", "grey", "black",
    ]
    for i, chain in enumerate(chains):
        color = f"LG{i+1}" if len(chains) <= 5 else palette[i % len(palette)]
        new_obj = f"{obj_name}_{chain}"
        cmd.create(new_obj, f"{obj_name} and polymer.protein and chain {chain}")
        cmd.show("cartoon", new_obj)
        cmd.set("cartoon_color", color, new_obj)
    cmd.hide("everything", obj_name)


def after_load(names: Iterable[str]) -> None:
    """Style objects after they are loaded into the session."""
    apply_colors()
    for name in names:
        cmd.hide("everything", f"{name} and resname HOH")

        # create derived objects BEFORE hiding on parent so atoms are visible
        cmd.create(f"{name}_organics", f"{name} and organic")
        cmd.create(f"{name}_inorganics", f"inorganic within 3.5 of {name}_organics")
        cmd.create(
            f"{name}_active_site_residues",
            f"byres ({name} and polymer.protein within 3.5 of {name}_organics)",
        )

        # now hide originals on parent
        cmd.hide("everything", f"{name} and organic")
        cmd.hide("everything", f"{name} and inorganic")

        # style derived objects
        cmd.show("spheres", f"{name}_organics")
        cmd.color("white", f"{name}_organics")

        cmd.show("spheres", f"{name}_inorganics")
        cmd.color("LG3", f"{name}_inorganics")

        util.cbay(f"{name}_active_site_residues")
        cmd.show("sticks", f"{name}_active_site_residues and not name n+c+o")
        cmd.hide("cartoon", f"{name}_active_site_residues")

        color_protein_chains(name)


def style_enzyme(obj: str) -> None:
    """Apply full enzyme presentation style to *obj*."""
    apply_colors()
    apply_display_settings()
    apply_render_settings()
    after_load([obj])
    cmd.zoom(obj)
    cmd.orient(obj)


# ── main ─────────────────────────────────────────────────────────────────────
OUTPUT_DIR = ROOT / ".rendering"
REFERENCE = ROOT / "tests" / "data" / "9ax6.cif"
ref_tag   = REFERENCE.stem

session = SceneSession(OUTPUT_DIR, f"enzyme_{ref_tag}", "enzyme.py")
session.run_reference(ref_tag, REFERENCE, style_enzyme)
session.apply_reference(ref_tag, REFERENCE)

print("\n[enzyme.py] Done.")
cmd.quit()
