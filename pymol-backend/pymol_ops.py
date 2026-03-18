"""PyMOL tool operations — GUI and headless entry points.

This module bridges the PyMOL application (GUI or headless) and the
engine-backed PyMOLController defined in backend.py.

Responsibilities:
  - save_scene:  capture the live session and persist to the shipped DB.
  - apply_scene: reconstruct visual state in PyMOL using BaseType-driven
                 universal selections + distribution-based positional
                 variants (structure-independent replay).
  - Register user-facing cmd.extend commands.

"""

import json

from pymol import cmd

from .backend import PyMOLController

# ---------------------------------------------------------------------------
# Controller — engine owns the DB; this module just holds the instance.
# The shipped scenography.db lives at db/scenography.db relative to the
# project root.  No setup command is exposed to users.
# ---------------------------------------------------------------------------

_controller: PyMOLController | None = None


def _controller_() -> PyMOLController:
    """Return the module-level controller, initialising on first access."""
    global _controller
    if _controller is None:
        _controller = PyMOLController()
    return _controller


# ---------------------------------------------------------------------------
# Save (capture + store)
# ---------------------------------------------------------------------------

def save_scene(name=None):
    """Capture the current PyMOL session and persist it to the database.

    Parameters
    ----------
    name : str, optional
        Human-readable label for the scene.  Defaults to "untitled_scene".

    Returns
    -------
    int
        The assigned scene ID.
    """
    controller = _controller_()
    scene_id = controller.ingest_scene(source=None, name=name or "untitled_scene")
    print(f"[rac] saved scene '{name or 'untitled_scene'}' → id={scene_id}")
    return scene_id


# ---------------------------------------------------------------------------
# Apply (restore from DB → PyMOL session)
# ---------------------------------------------------------------------------

def apply_scene(scene_id: int = None, scene_name: str = None):  # noqa: C901
    """Restore a scene from the database into the active PyMOL session.

    Uses BaseType-driven universal selections so the scene applies to any
    compatible structure, not just the one it was captured from.

    Positional colour variants (stored as distribution percentiles) are
    mapped to the current structure's atom count, preserving relative
    positioning across structures of different sizes.

    Parameters
    ----------
    scene_id : int, optional
        Scene ID to load.  Takes precedence over scene_name.
    scene_name : str, optional
        Scene name (searches by name when scene_id is not provided).

    Raises
    ------
    ValueError
        If neither identifier is given, or the scene is not found.
    """
    if scene_id is None and scene_name is None:
        raise ValueError("Provide scene_id or scene_name")

    controller = _controller_()

    # --- resolve scene record ---
    if scene_id is not None:
        scene = controller.load_scene(scene_id)
    else:
        matches = [s for s in controller.list_scenes() if s["name"] == scene_name]
        if not matches:
            raise ValueError(f"Scene '{scene_name}' not found")
        scene = controller.load_scene(matches[0]["id"])

    if not scene:
        raise ValueError(f"Scene {scene_id or scene_name!r} not found")

    scene_objects = controller.load_scene_objects(scene["id"])

    # --- global renderer settings ---
    supported = set(cmd.setting.get_name_list())
    for key, value in json.loads(scene["meta"]).items():
        if key in supported:
            try:
                cmd.set(key, value)
            except Exception:
                pass

    # --- viewport + camera ---
    viewport = json.loads(scene["size"])
    if viewport:
        cmd.viewport(*viewport)

    view = json.loads(scene["view"])
    if view:
        cmd.set_view(view)

    # --- per-object restoration ---
    for obj_rec in scene_objects:
        base_type = obj_rec["base_type"]
        payload   = json.loads(obj_rec["payload"])
        obj_name  = obj_rec["name"]

        # selector: empty string → "all" fallback
        selector = controller.get_selector(base_type) or "all"

        # -- dominant atom-type colours --
        basetype_data    = payload.get(base_type, {})
        atom_type_colors = basetype_data.get("atom_type_colors", {})

        for atom_type, color_idx in atom_type_colors.items():
            sel = f"name {atom_type} and {selector}"
            if cmd.count_atoms(sel) == 0:
                continue  # BaseType absent in this structure — skip silently
            try:
                rgb = cmd.get_color_tuple(color_idx)
                cmd.color(rgb, sel)
            except Exception:
                pass

        # -- special subcategory: user-scoped GUI selections + positional variants --
        #
        # The "special" key in a payload is a *list* of per-selection entries.
        # Each entry can originate from two sources (both stored the same way):
        #
        #   1. Statistical colour variant  — a minority colour on a specific
        #      atom type within the base chemistry (e.g. 20% of CA atoms in a
        #      tail region colored differently).
        #
        #   2. User GUI selection          — a named PyMOL selection the user
        #      defined (e.g. "active_site_residues") that sub-scopes the parent
        #      base_type object.  The selection carries its own atom_type_colors
        #      and a distribution range so it can be replayed on a different
        #      structure.
        #
        # Current implementation:  only statistical variants are replayed
        # (distribution-based positional mapping).
        #
        # TODO (utils.py § reconstruct_special_selection):
        #   Once utils.detect_special_selections() is wired into capture_scene,
        #   each entry here will also include a "name" key.  At that point:
        #     - Call utils.reconstruct_special_selection(group, selector) instead
        #       of the inline loop below.
        #     - Pass controller.get_selector(group["base_type"]) as parent_selector
        #       (the parent_selector may differ from the current obj's selector if
        #       an organic sub-selection lives inside a macromolecular object).
        #     - Optionally recreate the named selection via cmd.select(name, sel)
        #       so the user's label is available in the restored session.
        #
        for group in payload.get("special", []):
            distribution = group.get("distribution", {"start": 0.0, "end": 1.0})

            for atom_type, color_idx in group.get("atom_type_colors", {}).items():
                sel = f"name {atom_type} and {selector}"

                atom_data: list = []
                cmd.iterate(
                    sel,
                    "atom_data.append((int(resi), ID))",
                    space={"atom_data": atom_data},
                )
                if not atom_data:
                    continue

                atom_data.sort(key=lambda x: x[0])
                total     = len(atom_data)
                start_idx = int(total * distribution["start"])
                end_idx   = int(total * distribution["end"])

                ids = [aid for _, aid in atom_data[start_idx:end_idx]]
                if ids:
                    try:
                        rgb = cmd.get_color_tuple(color_idx)
                        cmd.color(rgb, f"ID {'+'.join(map(str, ids))}")
                    except Exception:
                        pass

        # -- representations --
        reps = payload.get("representations", {})
        for rep, enabled in reps.items():
            target = obj_name if cmd.count_atoms(obj_name) > 0 else selector
            if enabled:
                cmd.show(rep, target)
            else:
                cmd.hide(rep, target)

        # -- object matrix --
        matrix = payload.get("object_matrix")
        if matrix and obj_name in cmd.get_names("objects"):
            try:
                cmd.matrix_reset(obj_name)
                cmd.transform_object(obj_name, matrix, state=0)
            except Exception:
                pass

        # -- object-level settings --
        obj_settings = payload.get("object_settings") or []
        for entry in obj_settings:
            try:
                cmd.set(entry[0], entry[-1], obj_name)
            except Exception:
                pass

    cmd.rebuild()
    cmd.refresh()
    print(f"[rac] applied scene id={scene['id']} name={scene['name']!r}")


# ---------------------------------------------------------------------------
# cmd.extend registrations — user-facing PyMOL commands
# ---------------------------------------------------------------------------

cmd.extend("save_scene",  save_scene)
cmd.extend("apply_scene", apply_scene)
