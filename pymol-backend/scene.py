from pymol import cmd
import json
from pathlib import Path

# Default database path (shipped with repo)
DEFAULT_DB_PATH = Path(__file__).parent.parent / "db" / "scenography.db"

# Global state for tight integration
_db_path = None
_controller = None


def setup_db(db_path=None):
    """Configure database path for PyMOL integration.

    Call this once at PyMOL startup to set the database path.
    If not called, uses the default shipped scenography.db.

    Parameters
    ----------
    db_path : str or Path, optional
        Custom database path. If None, uses default shipped db.
    """
    global _db_path, _controller
    _db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
    _controller = None  # Reset controller to force reconnection


def get_db_path():
    """Return the active database path."""
    global _db_path
    if _db_path is None:
        _db_path = DEFAULT_DB_PATH
    return _db_path


def get_controller():
    """Get or create the controller instance with configured db path."""
    global _controller
    from engine.api import get_controller as _get_controller

    if _controller is None:
        _controller = _get_controller(db_path=get_db_path())
    return _controller


# ==========================================================
# EXPORT VISUAL SYSTEM STATE
# ==========================================================
def export_visual_system_state():
    """Capture current PyMOL visual state and return as dict.

    This function extracts global settings, camera, viewport, and per-object
    visual data from the live PyMOL session.

    Returns
    -------
    dict
        Structured visual state suitable for persistence via controller.
    """
    data = {}

    # -------------------------
    # Global Settings
    # -------------------------
    global_settings = {}
    for name in cmd.setting.get_name_list():
        try:
            global_settings[name] = cmd.get(name)
        except Exception:
            pass
    data["global_settings"] = global_settings

    # -------------------------
    # Camera + Viewport
    # -------------------------
    data["view_matrix"] = cmd.get_view()
    data["viewport"] = cmd.get_viewport()

    # -------------------------
    # Per-Object Visual State
    # -------------------------
    objects_data = {}

    for obj in cmd.get_names("objects"):

        obj_info = {}

        # Object transformation matrix
        obj_info["object_matrix"] = cmd.get_object_matrix(obj)

        # Representation visibility flags
        reps = {}
        for rep in [
            "cartoon",
            "sticks",
            "spheres",
            "surface",
            "mesh",
            "dots",
            "lines",
            "nonbonded",
        ]:
            reps[rep] = cmd.count_atoms(f"{obj} and rep {rep}") > 0
        obj_info["representations"] = reps

        # Object-level setting overrides
        try:
            obj_info["object_settings"] = cmd.get_object_settings(obj)
        except Exception:
            obj_info["object_settings"] = None

        # Object base color (index)
        try:
            obj_info["object_color_index"] = cmd.get_object_color_index(obj)
        except Exception:
            obj_info["object_color_index"] = None

        # Atom-level colors (stable key -> string)
        atom_colors = {}
        cmd.iterate(
            obj,
            "atom_colors[f'{chain}|{resi}|{name}|{alt}'] = color",
            space={"atom_colors": atom_colors}
        )
        obj_info["atom_colors"] = atom_colors

        objects_data[obj] = obj_info

    data["objects"] = objects_data

    return data


def save_scene_json(outfile="visual_system_state.json"):
    """Debug helper: export visual state to JSON file.

    This is NOT the primary workflow (use controller.ingest_scene instead).
    It exists for inspection and debugging only.
    """
    data = export_visual_system_state()
    with open(outfile, "w") as f:
        json.dump(data, f, indent=2)


cmd.extend("save_scene_json", save_scene_json)


def capture_and_store(name=None):
    """Capture current PyMOL state and store directly to database.

    This is the primary workflow: no JSON file created, direct DB write.

    Parameters
    ----------
    name : str, optional
        Scene name for the database record.

    Returns
    -------
    int
        Scene ID in the database.
    """
    controller = get_controller()
    scene_id = controller.ingest_scene(filepath=None, name=name)
    print(f"Stored scene '{name or 'untitled'}' as ID {scene_id}")
    return scene_id


cmd.extend("capture_and_store", capture_and_store)
cmd.extend("setup_db", setup_db)


# ==========================================================
# APPLY VISUAL SYSTEM STATE
# ==========================================================
def apply_scene(scene_id=None, scene_name=None, db_path=None):  # noqa: C901
    """Restore a scene from scenography.db.

    Parameters
    ----------
    scene_id : int, optional
        Scene ID to load. Takes precedence over scene_name.
    scene_name : str, optional
        Scene name to load (searches by name if scene_id not provided).
    db_path : str, optional
        Custom database path (overrides setup_db configuration).
        If not provided, uses the configured or default path.

    Raises
    ------
    ValueError
        If neither scene_id nor scene_name is provided, or scene not found.
    """
    if scene_id is None and scene_name is None:
        raise ValueError("Must provide scene_id or scene_name")

    # Use custom db_path if provided, otherwise use configured path
    if db_path:
        from engine.api import get_controller as _get_controller
        controller = _get_controller(db_path=Path(db_path))
    else:
        controller = get_controller()

    # Load scene record
    if scene_id is not None:
        scene = controller.load_scene(scene_id)
    else:
        # Find by name
        scenes = controller.list_scenes()
        matches = [s for s in scenes if s["name"] == scene_name]
        if not matches:
            raise ValueError(f"Scene '{scene_name}' not found in database")
        scene = controller.load_scene(matches[0]["id"])

    if not scene:
        raise ValueError(f"Scene {scene_id or scene_name} not found")

    # Load scene objects
    objects_list = controller.load_scene_objects(scene["id"])

    # Reconstruct data dict from database records
    data = {
        "global_settings": json.loads(scene["meta"]),
        "view_matrix": json.loads(scene["view"]),
        "viewport": json.loads(scene["size"]),
        "objects": {}
    }

    for obj_rec in objects_list:
        data["objects"][obj_rec["name"]] = json.loads(obj_rec["payload"])

    # -------------------------
    # Global Settings
    # -------------------------
    supported = set(cmd.setting.get_name_list())

    for key, value in data.get("global_settings", {}).items():
        if key in supported:
            try:
                cmd.set(key, value)
            except Exception:
                pass

    # -------------------------
    # Restore Viewport
    # -------------------------
    if "viewport" in data:
        w, h = data["viewport"]
        cmd.viewport(w, h)

    # -------------------------
    # Restore Camera Orientation
    # -------------------------
    if "view_matrix" in data:
        cmd.set_view(data["view_matrix"])

    # -------------------------
    # Restore Per-Object State
    # -------------------------
    for obj, obj_data in data.get("objects", {}).items():

        if obj not in cmd.get_names("objects"):
            continue

        cmd.matrix_reset(obj)

        matrix = obj_data.get("object_matrix")
        if matrix:
            cmd.transform_object(obj, matrix, state=0)

        idx = obj_data.get("object_color_index")
        if idx is not None:
            rgb = cmd.get_color_tuple(idx)
            cmd.set_object_color(obj, rgb)

        obj_settings = obj_data.get("object_settings")
        if obj_settings:
            for entry in obj_settings:
                try:
                    setting_name = entry[0]
                    value = entry[-1]
                    cmd.set(setting_name, value, obj)
                except Exception:
                    pass

        reps = obj_data.get("representations", {})
        for rep, enabled in reps.items():
            if enabled:
                cmd.show(rep, obj)
            else:
                cmd.hide(rep, obj)

        # Restore atom-level colors
        atom_colors = obj_data.get("atom_colors", {})
        for key, color_index in atom_colors.items():
            parts = key.split("|")
            if len(parts) != 4:
                continue
            chain, resi, name, alt = parts
            sel = f"{obj} and chain {chain} and resi {resi} and name {name}"
            if alt and alt != "":
                sel += f" and alt {alt}"
            cmd.alter(sel, f"color={color_index}")

    cmd.rebuild()
    cmd.refresh()


cmd.extend("apply_scene", apply_scene)
