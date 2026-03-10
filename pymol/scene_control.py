from pymol import cmd
import json


# ==========================================================
# EXPORT VISUAL SYSTEM STATE
# ==========================================================
def export_visual_system_state(outfile="visual_system_state.json"):

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

    with open(outfile, "w") as f:
        json.dump(data, f, indent=2)


cmd.extend("export_scene", export_visual_system_state)


# ==========================================================
# APPLY VISUAL SYSTEM STATE
# ==========================================================
def apply_scene(infile="visual_system_state.json"):  # noqa: C901

    with open(infile, "r") as f:
        data = json.load(f)

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
