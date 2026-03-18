"""PyMOL backend — engine integration.

Defines PyMOLController, the sole BackendController subclass for PyMOL.
Imports ONLY from engine.api.

Responsibilities:
  - Implement MolecularClassifier abstract slots (is_X methods) using
    PyMOL's native cmd selectors.
  - Implement capture_scene: read live PyMOL session → (SceneRecord, [SceneObject]).
  - Expose get_selector: BaseType → PyMOL selection keyword (used by pymol_ops).

Not responsible for:
  - DB path management (engine handles connections)
  - PyMOL command registration (see pymol_ops.py)
  - Scene restoration (see pymol_ops.py)
"""

import json
from pathlib import Path

from engine.api import BackendController

try:
    from pymol import cmd
    _HAVE_CMD = True
except Exception:
    cmd = None
    _HAVE_CMD = False


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
            return name in cmd.get_names("selections") or cmd.count_atoms(f"({name})") == 0
        except Exception:
            return False

    def is_special(self, name: str, data: dict) -> bool:
        """Catch-all for chemistry PyMOL cannot classify via its native selectors.

        Covers: solvent/water, ions (very few atoms), CGO objects, axes,
        pseudo-atoms — anything that is not polymer, organic, or inorganic.

        Dual-purpose:
          As primary base_type  → tool has no universal selector (get_selector returns "").
          As payload subcategory → statistical colour variants or user-scoped object
            selections stored as a list inside the payload (see utils.py TODO).
        """
        if not _HAVE_CMD:
            return False
        try:
            if cmd.count_atoms(f"({name}) and solvent") > 0:
                return True
            if 0 < cmd.count_atoms(f"({name})") <= 4:
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

    # --- BaseType → cmd keyword mapping (used by pymol_ops.apply_scene) ---

    def get_selector(self, base_type: str) -> str:
        """Return the PyMOL selection keyword for a BaseType string.

        SPECIAL returns "" intentionally — it is dual-purpose:
          As primary classification: tool doesn't recognise the chemistry
            (CGO, axes, nanomaterial) → no universal PyMOL selector exists.
          As payload subcategory: list of user-scoped object selections that
            carry statistical colour variants or arbitrary GUI selections
            (see utils.py for future per-entry reconstruction logic).

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
        """Read the live PyMOL session and return (SceneRecord, [SceneObject]).

        Single cmd call: cmd.get_session().
        Everything — settings, view, viewport, objects, reps, colors — is
        read from the returned session dict. 
        """
        session = cmd.get_session() # example in tests/data/*.json

        raw_settings = session.get("settings", [])
        setting_names = session.get("setting_names", [])
        if setting_names and len(setting_names) == len(raw_settings):
            global_settings = {
                setting_names[i]: raw_settings[i][2]
                for i in range(len(raw_settings))
            }
        else:
            global_settings = {str(i): v[2] for i, v in enumerate(raw_settings) if v}

        # objects: session["names"] is a list of per-object state entries.
        # Each entry is [name, ...object_state_data...].
        objects_data: dict = {}
        for entry in session.get("names", []):
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                continue
            obj_name = entry[0]
            obj_state = entry[1] if len(entry) > 1 else {}
            if not isinstance(obj_state, dict):
                continue
            objects_data[obj_name] = obj_state

        record = self.make_scene_record(
            name=name or "untitled_scene",
            meta=json.dumps(global_settings),
            view=json.dumps(list(session.get("view", []))),
            size=json.dumps(list(session.get("main", {}).get("viewport", []))),
        )
        objects = [
            self.make_scene_object(
                name=obj_name,
                base_type=self.classify_object(obj_name, obj_data),
                payload=json.dumps(obj_data),
            )
            for obj_name, obj_data in objects_data.items()
        ]
        return record, objects

