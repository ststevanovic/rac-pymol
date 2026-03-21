"""PyMOL driver — cmd-level entry points for save/apply.

This module is the PyMOL API frontend: it drives the PyMOL application
(GUI or headless) and bridges it to the engine-backed PyMOLController
defined in adapter.py.

Responsibilities:
  - save_scene:  capture the live session and persist to the shipped DB.
  - apply_scene: reconstruct visual state in PyMOL — chemistry-first,
                 cardinality-based colour restoration.
  - Register user-facing cmd.extend commands.

"""

import json

from pymol import cmd

from .adapter import PyMOLController

# ---------------------------------------------------------------------------
# Controller — engine owns the DB; this module just holds the instance.
# ---------------------------------------------------------------------------

_controller: PyMOLController | None = None


def _controller_() -> PyMOLController:
    """Return the module-level controller, initialising on first access."""
    global _controller
    if _controller is None:
        _controller = PyMOLController()
    return _controller


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Settings actually written by style() — the only ones worth replaying.
# Blasting all 779 global settings clobbers headless renderer state.
_STYLE_SETTINGS = [
    "bg_rgb", "ambient", "direct", "reflect",
    "specular", "shininess", "ray_opaque_background",
    "cartoon_transparency", "stick_radius", "sphere_scale",
    "cartoon_round_helices", "cartoon_fancy_sheets",
]

_REPS = ["cartoon", "sticks", "spheres", "surface",
         "mesh", "dots", "lines", "nonbonded"]


def _paint_proportional(sel: str, ratios: dict, rgb_map: dict) -> None:
    """Paint proportional atom-ID slices using stored colour ratios + RGB map.

    Strategy: paint dominant colour as a base over the whole selection first,
    then overwrite minority slices on top.  This guarantees the dominant colour
    fills every atom that isn't explicitly assigned to a minority.

    ``rgb_map`` is ``{str(color_index): [r, g, b]}`` captured at ingest time
    so no live colour-index lookup is needed during apply.
    """
    if not ratios:
        return

    # Sort ascending by ratio — dominant (highest) is last = base coat
    sorted_colors = sorted(ratios.items(), key=lambda kv: kv[1])
    dominant_cidx, _ = sorted_colors[-1]

    # ── base coat: paint entire selection with dominant colour ────────────
    dominant_rgb = rgb_map.get(dominant_cidx)
    if dominant_rgb is None:
        return
    dominant_name = f"_rac_{dominant_cidx}"
    cmd.set_color(dominant_name, list(dominant_rgb))
    cmd.color(dominant_name, sel)

    if len(sorted_colors) == 1:
        return  # monochromatic — done

    # ── minority overcoats: paint proportional slices for each minority ───
    target_n = cmd.count_atoms(sel)
    if target_n == 0:
        return
    atom_ids: list = []
    cmd.iterate(sel, "atom_ids.append(ID)", space={"atom_ids": atom_ids})

    assigned = 0
    for cidx_str, ratio in sorted_colors[:-1]:   # all except dominant
        rgb = rgb_map.get(cidx_str)
        if rgb is None:
            continue
        n = max(1, round(ratio * target_n))
        n = min(n, target_n - assigned)
        if n <= 0:
            continue
        subset_ids = atom_ids[assigned: assigned + n]
        assigned += n
        if subset_ids:
            color_name = f"_rac_{cidx_str}"
            cmd.set_color(color_name, list(rgb))
            cmd.color(color_name, "ID " + "+".join(map(str, subset_ids)))


# ---------------------------------------------------------------------------
# Save (capture + store)
# ---------------------------------------------------------------------------

def save_scene(name=None):
    """Capture the current PyMOL session and persist it to the database."""
    controller = _controller_()
    scene_id = controller.ingest_scene(source=None, name=name or "untitled_scene")
    print(f"[rac] saved scene '{name or 'untitled_scene'}' → id={scene_id}")
    return scene_id


# ---------------------------------------------------------------------------
# Apply (restore from DB → PyMOL session)
# ---------------------------------------------------------------------------

def _apply_colours(base_type: str, chem_sel: str, payload: dict) -> None:
    """Level 1 flat colour + Level 2 atom-name subtype restore."""
    bucket       = payload.get(base_type, {})
    color_ratios = bucket.get("color_ratios", {})
    rgb_map      = bucket.get("color_rgb", {})
    atom_names   = bucket.get("atom_names", {})

    if color_ratios:
        _paint_proportional(chem_sel, color_ratios, rgb_map)

    for aname, sub in atom_names.items():
        sub_ratios  = sub.get("color_ratios", {})
        sub_rgb_map = sub.get("color_rgb", rgb_map)
        if sub_ratios:
            _paint_proportional(f"{chem_sel} and name {aname}", sub_ratios, sub_rgb_map)


def _apply_object(controller, obj_rec: dict, live_objs: list) -> None:
    """Restore representations, colours, and settings for one scene object."""
    obj_name  = obj_rec["name"]
    base_type = obj_rec["base_type"]
    payload   = json.loads(obj_rec["payload"])

    selector = controller.get_selector(base_type)
    if obj_name in live_objs:
        apply_target = obj_name
    else:
        apply_target = live_objs[0] if live_objs else None
    if not apply_target:
        return

    obj_scope = f"({apply_target})"
    chem_sel  = f"{obj_scope} and {selector}" if selector else obj_scope

    # a. representations
    # Representations are scoped to avoid applying chem-specific reps
    # (spheres/sticks for organic/inorganic) to the whole object which
    # would put spheres on solvent/polymer atoms.
    # cartoon → whole object; spheres/sticks → chem_sel only; rest → whole.
    _CHEM_SCOPED = {"spheres", "sticks"}
    reprs = payload.get("representations") or {}
    if reprs:
        cmd.hide("everything", apply_target)
        for rep in _REPS:
            if reprs.get(rep):
                scoped = rep in _CHEM_SCOPED and chem_sel != obj_scope
                cmd.show(rep, chem_sel if scoped else apply_target)

    # b+c. colour restore (Level 1 flat → Level 2 atom-name subtypes)
    _apply_colours(base_type, chem_sel, payload)

    # d. per-object setting overrides
    for entry in (payload.get("object_settings") or []):
        if isinstance(entry, (list, tuple)) and len(entry) >= 3:
            try:
                cmd.set(entry[0], entry[2], apply_target)
            except Exception:
                pass


def _resolve_scene(controller, scene_id, scene_name):
    """Look up a scene record by id or name; raise ValueError if not found."""
    if scene_id is not None:
        scene = controller.load_scene(scene_id)
    else:
        matches = [s for s in controller.list_scenes() if s["name"] == scene_name]
        if not matches:
            raise ValueError(f"Scene '{scene_name}' not found")
        scene = controller.load_scene(matches[-1]["id"])
    if not scene:
        raise ValueError(f"Scene {scene_id or scene_name!r} not found")
    return scene


def _replay_settings_and_view(scene: dict, restore_view: bool = True) -> None:
    """Replay targeted style settings and optionally the view matrix."""
    meta = json.loads(scene["meta"])
    gs   = meta.get("global_settings", {})
    for setting_name in _STYLE_SETTINGS:
        if setting_name in gs:
            try:
                cmd.set(setting_name, gs[setting_name])
            except Exception:
                pass
    viewport = json.loads(scene["size"])
    if viewport and any(v > 0 for v in viewport):
        cmd.viewport(*viewport)
    if restore_view:
        view = json.loads(scene["view"])
        if view:
            cmd.set_view(view[:18])


def apply_scene(scene_id: int = None, scene_name: str = None):
    """Restore a scene from the database into the active PyMOL session.

    Replay order:
      1. Style settings only  (bg_rgb, ambient, cartoon_* … — not all 779)
      2. Viewport + view matrix
      3. Per-object:
           a. Representations  — hide all, re-show captured reps
           b. Colour Level 1   — flat bucket ratios over chem selector
           c. Colour Level 2   — per-atom-name subtype overrides
           d. Object settings  — cartoon_color, sphere_color etc. (last)

    Does NOT call cmd.rebuild() — the caller owns the render cycle.
    """
    if scene_id is None and scene_name is None:
        raise ValueError("Provide scene_id or scene_name")

    controller = _controller_()
    scene = _resolve_scene(controller, scene_id, scene_name)

    # Detect cross-molecule: if the stored object name isn't loaded, the
    # reference view matrix points at different coordinates — skip it and
    # zoom/orient to whatever is actually loaded.
    stored_names = {r["name"] for r in controller.load_scene_objects(scene["id"])}
    live_objs = cmd.get_names("objects")
    same_molecule = bool(stored_names & set(live_objs))

    _replay_settings_and_view(scene, restore_view=same_molecule)
    if not same_molecule and live_objs:
        cmd.zoom(live_objs[0])
        cmd.orient(live_objs[0])

    for obj_rec in controller.load_scene_objects(scene["id"]):
        _apply_object(controller, obj_rec, live_objs)

    print(f"[rac] applied scene id={scene['id']} name={scene['name']!r}")


# ---------------------------------------------------------------------------
# cmd.extend registrations — user-facing PyMOL commands
# ---------------------------------------------------------------------------

cmd.extend("save_scene",  save_scene)
cmd.extend("apply_scene", apply_scene)
