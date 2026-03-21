"""
This script follows procedure from the following medium blogs:


#1 : customization [set up pymol like a pro with pymolrc](https://yarrowmadrona.medium.com/smarter-pymol-1-set-up-pymol-like-a-pro-with-pymolrc-96c07b72348f)

#2: render [Automate Beautiful Molecular Illustrations in PyMOL with one Click Using .PML scripts](https://yarrowmadrona.medium.com/smarter-pymol-2-automate-beautiful-molecular-illustrations-in-pymol-with-one-click-using-pml-332a728c8b72)

#3: python [🔬Smarter PyMOL #3: Automate Molecular Figures with Python (Beyond .PML)](
    https://yarrowmadrona.medium.com/smarter-pymol-3-supercharge-molecular-figures-with-python-automation-beyond-pml-9526e19d3013
)
"""


import os
from pymol import cmd, util
from typing import Iterable


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
        "bg_rgb": "light_grey",
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
        "red",
        "green",
        "blue",
        "yellow",
        "cyan",
        "magenta",
        "orange",
        "slate",
        "teal",
        "violet",
        "salmon",
        "lime",
        "pink",
        "marine",
        "wheat",
        "white",
        "grey",
        "black",
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
    for name in names:
        # hide waters and small components from default view
        cmd.hide("everything", f"{name} and resname HOH")
        cmd.hide("everything", f"{name} and organic")
        cmd.hide("everything", f"{name} and inorganic")

        # organics as white spheres
        cmd.create(f"{name}_organics", f"{name} and organic")
        cmd.show("spheres", f"{name}_organics")
        cmd.color("white", f"{name}_organics")

        # inorganics as colored spheres near organics
        cmd.create(f"{name}_inorganics", f"inorganic within 3.5 of {name}_organics")
        cmd.show("spheres", f"{name}_inorganics")
        cmd.color("LG3", f"{name}_inorganics")

        # active site residues: protein residues near organics
        cmd.create(
            f"{name}_active_site_residues",
            f"byres ({name} and polymer.protein within 3.5 of {name}_organics)",
        )
        util.cbay(f"{name}_active_site_residues")
        cmd.show("sticks", f"{name}_active_site_residues and not name n+c+o")
        cmd.hide("cartoon", f"{name}_active_site_residues")

        color_protein_chains(name)


# preserve originals so we can restore if needed
_original_load = cmd.load
_original_fetch = cmd.fetch


def custom_load(*args, **kwargs):
    """Wrap cmd.load to call styling after load."""
    result = _original_load(*args, **kwargs)

    obj_name = kwargs.get("object")
    if not obj_name and len(args) > 1 and isinstance(args[1], str):
        obj_name = args[1]
    if not obj_name and len(args) > 0 and isinstance(args[0], str):
        obj_name = os.path.basename(args[0]).split(".")[0]

    if obj_name:
        after_load([obj_name])

    return result


def custom_fetch(*args, **kwargs):
    """Wrap cmd.fetch to call styling after fetch."""
    result = _original_fetch(*args, **kwargs)

    names = result if isinstance(result, list) else [result]
    valid = [n for n in names if n and n in cmd.get_names("objects")]

    if valid:
        after_load(valid)

    return result


def install_hooks() -> None:
    """Replace PyMOL load/fetch with wrapped versions that style loaded objects."""
    cmd.load = custom_load
    cmd.fetch = custom_fetch


def load_pretty(filename: str, object_name: str = "") -> None:
    """Convenience command to load and style an object immediately."""
    cmd.load(filename, object_name)
    obj_name = object_name if object_name else os.path.basename(filename).split(".")[0]
    if obj_name:
        after_load([obj_name])


# expose a CLI-style initializer for scripts that want to apply the style
def apply_style_startup() -> None:
    apply_colors()
    apply_display_settings()
    apply_render_settings()
    install_hooks()


# register the convenience command in PyMOL
cmd.extend("load_pretty", load_pretty)


# auto-apply on import (matches previous .pymolrc behavior)
apply_style_startup()


if __name__ == "__main__":

    # expected output :
#     {
#   "global_settings": {
#     "min_mesh_spacing": "0.60000",
#     "dot_density": "2",
#     "dot_mode": "0",
#     "solvent_radius": "1.40000",
#     "sel_counter": "0",
#     "bg_rgb": "light_grey",
#     "ambient": "0.40000",
#     "direct": "0.45000",
#     "reflect": "0.45000",
#     "light": "[ -0.40000, -0.40000, -1.00000 ]",
#     "power": "1.00000",
#     "sculpt_bond_weight": "2.25000",
#     "sculpt_angl_weight": "1.00000",
#     "sculpt_pyra_weight": "1.00000",
#     "sculpt_plan_weight": "1.00000",
#     "sculpting_cycles": "10",
#     "sphere_transparency": "0.00000",
#     "sphere_color": "default",
#     "sculpt_field_mask": "511",
#     "sculpt_hb_overlap": "1.00000",
#     "ss_strand_phi_target": "-129.00000",
#     "ss_strand_phi_include": "40.00000",
#     "ss_strand_phi_exclude": "100.00000",
#     "movie_loop": "on",
#     "pdb_retain_ids": "off",
#     "pdb_no_end_record": "off",
#     "cgo_dot_width": "2.00000",
#     "cgo_dot_radius": "-1.00000",
#     "defer_updates": "off",
#     "normalize_o_maps": "on",
#     "swap_dsn6_bytes": "on",
#     "pdb_insertions_go_first": "off",
#     "roving_origin_z": "on",
#     "roving_origin_z_cushion": "3.00000",
#     "specular_intensity": "0.50000",
#     "overlay_lines": "5",
#     "ray_transparency_spec_cut": "0.90000",
#     "internal_prompt": "on",
#     "normalize_grd_maps": "off"
#   },
#   "view_matrix": [
#     -0.6800104379653931,
#     0.027444228529930115,
#     -0.7326892614364624,
#     0.7115711569786072,
#     -0.2162483185529709,
#     -0.6685096621513367,
#     -0.17678986489772797,
#     -0.9759534597396851,
#     0.12752199172973633,
#     0.0,
#     0.0,
#     -240.30552673339844,
#     13.729042053222656,
#     -20.910694122314453,
#     -21.940711975097656,
#     212.982421875,
#     267.6286315917969,
#     20.0
#   ],
#   "viewport": [
#     2632,
#     1166
#   ],
#   "objects": {
#     "9ax6": {
#       "object_matrix": [
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0
#       ],
#       "representations": {
#         "cartoon": false,
#         "sticks": false,
#         "spheres": false,
#         "surface": false,
#         "mesh": false,
#         "dots": false,
#         "lines": false,
#         "nonbonded": false
#       },
#       "object_settings": null,
#       "object_color_index": 5271,
#       "atom_colors": {
#         "A|0|N|": 27,
#         "A|0|CA|": 5271,
#         "A|0|C|": 5271,
#         "A|0|O|": 28
#       }
#     },
#     "9ax6_organics": {
#       "object_matrix": [
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0
#       ],
#       "representations": {
#         "cartoon": false,
#         "sticks": false,
#         "spheres": true,
#         "surface": false,
#         "mesh": false,
#         "dots": false,
#         "lines": false,
#         "nonbonded": false
#       },
#       "object_settings": null,
#       "object_color_index": 0,
#       "atom_colors": {
#         "A|201|O1A|": 0,
#         "A|201|O1B|": 0,
#         "A|201|O1G|": 0,
#         "A|201|C2|": 0,
#         "A|201|N2|": 0,
#         "A|201|O2A|": 0,
#         "A|201|O2B|": 0
#       }
#     },
#     "9ax6_inorganics": {
#       "object_matrix": [
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0
#       ],
#       "representations": {
#         "cartoon": false,
#         "sticks": false,
#         "spheres": true,
#         "surface": false,
#         "mesh": false,
#         "dots": false,
#         "lines": false,
#         "nonbonded": false
#       },
#       "object_settings": null,
#       "object_color_index": 5391,
#       "atom_colors": {
#         "A|202|MG|": 5391,
#         "B|202|MG|": 5391
#       }
#     },
#     "9ax6_active_site_residues": {
#       "object_matrix": [
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0
#       ],
#       "representations": {
#         "cartoon": false,
#         "sticks": true,
#         "spheres": false,
#         "surface": false,
#         "mesh": false,
#         "dots": false,
#         "lines": false,
#         "nonbonded": false
#       },
#       "object_settings": null,
#       "object_color_index": 5271,
#       "atom_colors": {
#         "A|0|N|": 27,
#         "A|0|CA|": 6,
#         "A|0|C|": 6,
#         "A|0|O|": 28,
#         "A|0|CB|": 6
#       }
#     },
#     "9ax6_A": {
#       "object_matrix": [
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0
#       ],
#       "representations": {
#         "cartoon": true,
#         "sticks": false,
#         "spheres": false,
#         "surface": false,
#         "mesh": false,
#         "dots": false,
#         "lines": false,
#         "nonbonded": false
#       },
#       "object_settings": [
#         [
#           236,
#           5,
#           5389
#         ]
#       ],
#       "object_color_index": 5271,
#       "atom_colors": {
#         "A|0|N|": 27,
#         "A|0|CA|": 5271,
#         "A|0|C|": 5271
#       }
#     },
#     "9ax6_B": {
#       "object_matrix": [
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0
#       ],
#       "representations": {
#         "cartoon": true,
#         "sticks": false,
#         "spheres": false,
#         "surface": false,
#         "mesh": false,
#         "dots": false,
#         "lines": false,
#         "nonbonded": false
#       },
#       "object_settings": [
#         [
#           236,
#           5,
#           5390
#         ]
#       ],
#       "object_color_index": 5271,
#       "atom_colors": {
#         "B|0|N|": 27,
#         "B|0|CA|": 5271,
#         "B|0|C|": 5271,
#         "B|0|O|": 28
      
#       }
#     },
#     "9ax6_C": {
#       "object_matrix": [
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0
#       ],
#       "representations": {
#         "cartoon": true,
#         "sticks": false,
#         "spheres": false,
#         "surface": false,
#         "mesh": false,
#         "dots": false,
#         "lines": false,
#         "nonbonded": false
#       },
#       "object_settings": [
#         [
#           236,
#           5,
#           5391
#         ]
#       ],
#       "object_color_index": 5271,
#       "atom_colors": {
#         "C|0|CA|": 5271,
#         "C|1|CA|": 5271,
#         "C|2|N|": 27,
#         "C|2|CA|": 5271,
#         "C|2|C|": 5271,
#         "C|2|O|": 28,
#         "C|2|CB|": 5271,
#         "C|2|CG1|": 5271
#       }
#     },
#     "9ax6_D": {
#       "object_matrix": [
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0,
#         0.0,
#         0.0,
#         0.0,
#         0.0,
#         1.0
#       ],
#       "representations": {
#         "cartoon": true,
#         "sticks": false,
#         "spheres": false,
#         "surface": false,
#         "mesh": false,
#         "dots": false,
#         "lines": false,
#         "nonbonded": false
#       },
#       "object_settings": [
#         [
#           236,
#           5,
#           5392
#         ]
#       ],
#       "object_color_index": 5271,
#       "atom_colors": {
#         "D|0|CA|": 5271,
#         "D|1|CA|": 5271,
#         "D|2|N|": 27,
#         "D|2|CA|": 5271,
#         "D|2|C|": 5271,
#         "D|2|O|": 28,
#         "D|2|CB|": 5271,
#         "D|2|CG1|": 5271,
#         "D|2|CG2|": 5271,
#         "D|3|N|": 27,
#         "D|3|CA|": 5271,
#         "D|3|C|": 5271,
#         "D|165|OXT|": 28
#       }
#     }
#   }
# }
  

    import sys
    import json
    from pathlib import Path
    import pymol.setting as ps

    pymol_path = Path(__file__).parent.parent
    sys.path.insert(0, str(pymol_path))

    import pymol as _pymol
    _pymol.finish_launching(["pymol", "-cq"])

    cif = Path(__file__).parent.parent.parent / "workdir" / "9ax6.cif"
    cmd.load(str(cif), "9ax6")

    session = cmd.get_session()
    name_list = ps.get_name_list()
    names_by_obj = {e[0]: e for e in session["names"] if e is not None}

    # ── global_settings: ALL settings as {name: text_value} ──
    global_settings = {
        name: cmd.get_setting_text(name) for name in name_list
    }

    # ── view_matrix (18 floats) ──
    view_matrix = list(cmd.get_view())

    # ── camera_position ──
    camera_position = list(cmd.get_position())

    # ── viewport ──
    viewport = list(session.get("main", []))

    # ── objects ──
    _TRACKED_SETTINGS = ["cartoon_color", "sphere_color", "stick_color", "surface_color"]
    objects: dict = {}
    for obj in cmd.get_names("objects"):
        # object_settings — per-object overrides via get_setting_tuple
        object_settings = []
        for sname in _TRACKED_SETTINGS:
            try:
                idx = name_list.index(sname)
                typ, (val,) = cmd.get_setting_tuple(sname, obj)
                global_typ, (global_val,) = cmd.get_setting_tuple(sname)
                if val != global_val:
                    object_settings.append([idx, typ, val])
            except Exception:
                pass
        object_settings = object_settings or None

        # visibility from cmd.get_vis
        try:
            vis = cmd.get_vis()
            visibility = vis[0].get(obj) if vis else None
        except Exception:
            visibility = None

        objects[obj] = {
            "object_settings": object_settings,
            "visibility": visibility,
            "color_index": cmd.get_object_color_index(obj),
            "object_matrix": list(cmd.get_object_matrix(obj)),
        }

    out = {
        "global_settings": global_settings,
        "view_matrix": view_matrix,
        "camera_position": camera_position,
        "viewport": viewport,
        "objects": objects,
    }

    output = Path(__file__).parent.parent / ".rendering"
    output.mkdir(exist_ok=True)
    dst = output / "enzyme_session.json"
    with open(dst, "w") as f:
        json.dump(out, f, indent=2)
    print(f"[enzyme] saved → {dst}")

    cmd.save(str(output / "enzyme_session.pse"))
    print(f"[enzyme] saved → {output / 'enzyme_session.pse'}")

    cmd.ray(2400, 1600)
    img_path = output / "enzyme_session.png"
    cmd.png(str(img_path), dpi=150)
    print(f"[enzyme] saved → {img_path}")

    cmd.quit()