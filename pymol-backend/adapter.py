"""PyMOL backend — engine integration.

Defines PyMOLController, the sole BackendController subclass for PyMOL.
Imports ONLY from engine.api.

Responsibilities:
  - Implement MolecularClassifier abstract slots (is_X methods) using
    PyMOL's native cmd selectors.
  - Implement capture_scene: read live PyMOL session → (SceneRecord, [SceneObject]).
  - Expose get_selector: BaseType → PyMOL selection keyword (used by driver).

Not responsible for:
  - DB path management (engine handles connections)
  - PyMOL command registration (see driver.py)
  - Scene restoration (see driver.py)
"""

import json
from pathlib import Path

from engine.api import BackendController
from engine import condenser

try:
    from pymol import cmd
    import pymol.setting as _ps
    _HAVE_CMD = True
except Exception:
    cmd = None
    _ps = None
    _HAVE_CMD = False

_TRACKED_SETTINGS = ["cartoon_color", "sphere_color", "stick_color", "surface_color"]


def _classify_live(obj: str) -> str:
    """Classify a PyMOL object by dominant chemistry while cmd is live.

    Priority (chemistry-first): chains → macromolecular → organic → inorganic
    → special (solvent/ions/unrecognised).

    Solvent is checked LAST — a protein with water molecules is still
    macromolecular; only a pure-solvent or pure-ion object is special.
    Tiny objects (≤ 4 atoms) that are not polymer/organic/inorganic fall
    through to special (covers lone ions, CGO pseudo-atoms, axes).
    """
    from engine.models import BaseType
    if not _HAVE_CMD:
        return BaseType.SPECIAL
    try:
        if obj not in cmd.get_names("objects"):
            return BaseType.CHAINS
        n = cmd.count_atoms(f"({obj})")
        if n == 0:
            return BaseType.CHAINS
        # Chemistry-first: dominant type wins regardless of co-present solvent
        if cmd.count_atoms(f"({obj}) and polymer") > 0:
            return BaseType.MACROMOLECULAR
        if cmd.count_atoms(f"({obj}) and organic") > 0:
            return BaseType.ORGANIC
        if cmd.count_atoms(f"({obj}) and inorganic") > 0:
            return BaseType.INORGANIC
        # Only reach here for pure solvent, lone ions, CGO, axes, etc.
    except Exception:
        pass
    return BaseType.SPECIAL


_REPS_LIST = ["cartoon", "sticks", "spheres", "surface",
              "mesh", "dots", "lines", "nonbonded"]


def _capture_object(obj: str, name_list: list) -> dict:
    """Capture per-object data from the live PyMOL session."""
    object_settings = []
    for sname in _TRACKED_SETTINGS:
        try:
            typ, (val,) = cmd.get_setting_tuple(sname, obj)
            _, (gval,) = cmd.get_setting_tuple(sname)
            if val != gval:
                object_settings.append([sname, typ, val])
        except Exception:
            pass

    try:
        vis = cmd.get_vis()
        visibility = vis[0].get(obj) if vis else None
    except Exception:
        visibility = None

    representations = {}
    for rep in _REPS_LIST:
        try:
            representations[rep] = cmd.count_atoms(f"({obj}) and rep {rep}") > 0
        except Exception:
            representations[rep] = False

    base_type = _classify_live(obj)

    # Scope the colour iterate to the chemistry selector so solvent/ions
    # never bleed into the macromolecular (or other) colour bucket.
    _CHEM_SEL = {
        "macromolecular": "polymer",
        "organic":        "organic",
        "inorganic":      "inorganic",
    }
    chem_filter = _CHEM_SEL.get(base_type)
    iter_sel = f"({obj}) and {chem_filter}" if chem_filter else f"({obj})"

    atom_colors: dict[str, int] = {}
    try:
        cmd.iterate(
            iter_sel,
            "atom_colors[f'{chain}|{resi}|{name}|{alt}'] = color",
            space={"atom_colors": atom_colors},
        )
    except Exception:
        pass

    color_rgb: dict[str, list] = {}
    for cidx in set(atom_colors.values()):
        try:
            color_rgb[str(cidx)] = list(cmd.get_color_tuple(cidx))
        except Exception:
            pass

    return {
        "base_type":       base_type,
        "object_settings": object_settings or None,
        "visibility":      visibility,
        "color_index":     cmd.get_object_color_index(obj),
        "object_matrix":   list(cmd.get_object_matrix(obj)),
        "representations": representations,
        "atom_colors":     atom_colors,
        "color_rgb":       color_rgb,
    }


def _extract_scene() -> dict:
    """Extract the current PyMOL session into the canonical scene format.

    Canonical format (matches workdir/scene.json):
      global_settings:  {name: text_value}  — all 779 settings
      view_matrix:      [18 floats]          — cmd.get_view()
      camera_position:  [x, y, z]            — cmd.get_position()
      viewport:         [w, h]               — session["main"]
      objects:          {name: {object_settings, visibility, color_index,
                                object_matrix}}
    """
    session = cmd.get_session()
    name_list = _ps.get_name_list()
    return {
        "global_settings": {n: cmd.get_setting_text(n) for n in name_list},
        "view_matrix":     list(cmd.get_view()),
        "camera_position": list(cmd.get_position()),
        "viewport":        list(session.get("main", [])),
        "objects":         {
            obj: _capture_object(obj, name_list)
            for obj in cmd.get_names("objects")
        },
    }


class PyMOLController(BackendController):
    """PyMOL implementation of BackendController.

    Single class — all session reading, classification, and scene building
    happen here.  No module-level helpers.

    capture_scene reads cmd.get_session() as the authoritative source and
    maps it to (SceneRecord, [SceneObject]) for the engine to persist.
    """

    def __init__(self, path: Path = None):
        super().__init__(path=path)
        self._db.connect()
        self._db.init_schema()

    # --- MolecularClassifier abstract slots ---

    def is_chains(self, name: str, data: dict) -> bool:
        """Selection or chain group — cmd reports zero atoms."""
        if not _HAVE_CMD:
            return False
        try:
            return (
                name in cmd.get_names("selections")
                or cmd.count_atoms(f"({name})") == 0
            )
        except Exception:
            return False

    def is_special(self, name: str, data: dict) -> bool:
        """Catch-all for objects with no dominant polymer/organic/inorganic chemistry.

        Covers: pure-solvent objects, lone ions (≤ 4 atoms with no other
        chemistry), CGO objects, axes, pseudo-atoms.

        Note: a protein that also contains water is NOT special — it is
        macromolecular (is_macromolecular takes priority).  Only objects
        where polymer/organic/inorganic are all absent fall here.
        """
        if not _HAVE_CMD:
            return False
        try:
            if cmd.count_atoms(f"({name}) and polymer") > 0:
                return False
            if cmd.count_atoms(f"({name}) and organic") > 0:
                return False
            if cmd.count_atoms(f"({name}) and inorganic") > 0:
                return False
            n = cmd.count_atoms(f"({name})")
            if n > 0:
                return True
        except Exception:
            pass
        return False

    def is_macromolecular(self, name: str, data: dict) -> bool:
        """Protein or nucleic acid — cmd 'polymer' selector."""
        if not _HAVE_CMD:
            return False
        try:
            return cmd.count_atoms(f"({name}) and polymer") > 0
        except Exception:
            return False

    def is_organic(self, name: str, data: dict) -> bool:
        """Small molecule / ligand — cmd 'organic' selector."""
        if not _HAVE_CMD:
            return False
        try:
            return cmd.count_atoms(f"({name}) and organic") > 0
        except Exception:
            return False

    def is_inorganic(self, name: str, data: dict) -> bool:
        """Metal cluster or inorganic solid — cmd 'inorganic' selector."""
        if not _HAVE_CMD:
            return False
        try:
            return cmd.count_atoms(f"({name}) and inorganic") > 0
        except Exception:
            return False

    # --- BaseType → cmd keyword mapping (used by driver.apply_scene) ---

    def get_selector(self, base_type: str) -> str:
        """Return the PyMOL selection keyword for a BaseType string.

        SPECIAL returns "" intentionally — it is dual-purpose:
          As primary classification: tool doesn't recognise the chemistry
            (CGO, axes, nanomaterial) → no universal PyMOL selector exists.
          As payload subcategory: list of user-scoped object selections that
            carry statistical colour variants or arbitrary GUI selections
            (see middleware.py for future per-entry reconstruction logic).

        CHAINS also returns "" — chain groups are not a chemical category
        and are reconstructed from their member objects, not from a keyword.
        """
        return {
            "macromolecular": "polymer",
            "organic":        "organic",
            "inorganic":      "inorganic",
            "special":        "",   # no universal selector — see docstring
            "chains":         "",
        }.get(base_type, "")

    # --- SceneBackend abstract slot ---

    def capture_scene(self, source=None, name: str = None):
        """Return (SceneRecord, [SceneObject]) from a live session or a file.

        source=None   — read live PyMOL session via _extract_scene().
        source=<path> — load a pre-exported canonical JSON (tests / headless).

        For each object:
          1. classify by chemistry (BaseType) — embedded in doc by _extract_scene
          2. compress atom_colors → {base_type: {color_counts}} via condenser
        """
        if source is not None:
            with open(source) as fh:
                doc = json.load(fh)
        else:
            doc = _extract_scene()

        obj_names = list(doc.get("objects", {}).keys())

        record = self.make_scene_record(
            name=name or "untitled_scene",
            meta=json.dumps(doc),
            view=json.dumps(doc.get("view_matrix", [])),
            size=json.dumps(doc.get("viewport", [])),
        )

        scene_objects = []
        for obj_name in obj_names:  # noqa: E501
            obj_data = dict(doc["objects"][obj_name])

            # base_type was embedded by _extract_scene while cmd was live;
            # fall back to offline classification only for file-sourced docs.
            base_type = obj_data.pop("base_type", None) or \
                        self.classify_object(obj_name, obj_data)

            # Compress atom_colors → {base_type: {color_counts: {...}}}
            compressed = condenser.compress_payload(obj_data, base_type)

            scene_objects.append(
                self.make_scene_object(
                    name=obj_name,
                    base_type=base_type,
                    payload=json.dumps(compressed),
                )
            )

        return record, scene_objects

