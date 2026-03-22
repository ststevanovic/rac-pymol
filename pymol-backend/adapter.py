"""PyMOL backend - engine integration.

Defines PyMOLController, the sole BackendController subclass for PyMOL.
Imports ONLY from engine.api.

No private helpers. All session capture logic lives in middleware.py.
capture_scene delegates entirely to DataPipeline.
"""

import json
from pathlib import Path

from engine.api import BackendController
from . import middleware

try:
    from pymol import cmd
    _HAVE_CMD = True
except Exception:
    cmd = None
    _HAVE_CMD = False


class PyMOLController(BackendController):

    def __init__(self, path: Path = None):
        super().__init__(path=path)
        self._db.connect()
        self._db.init_schema()

    # --- MolecularClassifier abstract slots --- pure cmd calls ---

    def is_chains(self, name: str, data: dict) -> bool:
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
        if not _HAVE_CMD:
            return False
        try:
            if cmd.count_atoms(f"({name}) and polymer")  > 0: return False
            if cmd.count_atoms(f"({name}) and organic")  > 0: return False
            if cmd.count_atoms(f"({name}) and inorganic") > 0: return False
            return cmd.count_atoms(f"({name})") > 0
        except Exception:
            return False

    def is_macromolecular(self, name: str, data: dict) -> bool:
        if not _HAVE_CMD:
            return False
        try:
            return cmd.count_atoms(f"({name}) and polymer") > 0
        except Exception:
            return False

    def is_organic(self, name: str, data: dict) -> bool:
        if not _HAVE_CMD:
            return False
        try:
            return cmd.count_atoms(f"({name}) and organic") > 0
        except Exception:
            return False

    def is_inorganic(self, name: str, data: dict) -> bool:
        if not _HAVE_CMD:
            return False
        try:
            return cmd.count_atoms(f"({name}) and inorganic") > 0
        except Exception:
            return False

    # --- BaseType -> PyMOL native selector (used by driver) ---

    _BT_SELECTOR: dict[str, str] = {
        "macromolecular": "polymer",
        "organic":        "organic",
        "inorganic":      "inorganic",
        "special":        "solvent",
        "chains":         "",
    }

    def get_selector(self, base_type: str) -> str:
        return self._BT_SELECTOR.get(base_type, "")

    # --- SceneBackend abstract slot ---

    def capture_scene(self, source=None, name: str = None):
        """Delegate entirely to DataPipeline.

        source=None -> live PyMOL session via DataPipeline.capture_live()
        source=path -> load raw JSON from file, run through DataPipeline
        """
        if source is not None:
            with open(source) as fh:
                raw = json.load(fh)
            staged = middleware.DataPipeline().process(raw)
        else:
            raw, staged = middleware.DataPipeline().capture_live()

        record = self.make_scene_record(
            name=name or "untitled_scene",
            meta=json.dumps(raw),
            view=json.dumps(raw.get("view_matrix", [])),
            size=json.dumps(raw.get("viewport", [])),
        )

        # Each BT bucket is stored as its own scene_object.
        # name=bt, base_type=bt, payload wraps the bucket under "objects"
        # so that apply_object's payload.get("objects")[bt] resolves correctly.
        scene_objects = [
            self.make_scene_object(
                name=bt,
                base_type=bt,
                payload=json.dumps({"objects": {bt: bucket}}),
            )
            for bt, bucket in (staged.get("objects") or {}).items()
        ]

        return record, scene_objects
