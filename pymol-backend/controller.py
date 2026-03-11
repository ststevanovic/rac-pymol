"""PyMOL backend implementation of DBController.

This is the ONLY place that knows about:
  - PyMOL's visual_system_state JSON structure
  - How to classify objects into BaseType
  - How to decompose the export into meta / view / size / objects

The engine (engine/controller.py) stays completely renderer-agnostic.
"""

import json
from pathlib import Path

from engine.controller import DBController
from engine.models import BaseType

# Try to import PyMOL command API. If running inside a PyMOL-enabled
# virtualenv this will be available and we prefer to use its selection
# keywords for robust classification. Otherwise fall back to heuristics
# based on the exported JSON payload.
try:
  from pymol import cmd
  _HAVE_CMD = True
except Exception:
  cmd = None
  _HAVE_CMD = False


# ---------------------------------------------------------------------------
# Base type classification — PyMOL-specific heuristics
# ---------------------------------------------------------------------------

# Atom name sets used to classify molecules
_SOLVENT_RESIDUES = {"HOH", "WAT", "H2O", "TIP", "TIP3", "TIP4", "SOL"}
_ION_RESIDUES = {
    "NA", "NA+", "K", "K+", "CL", "CL-", "MG", "CA", "ZN", "FE",
    "MN", "CU", "NI", "CO", "CD", "HG", "PB",
}
_NUCLEIC_ACID_ATOMS = {"P", "OP1", "OP2", "O5'", "C5'", "C4'", "C3'", "O3'"}
def _classify_with_cmd(name: str):
    if not _HAVE_CMD:
        return None

    try:
        names = set(cmd.get_names("objects"))
    except Exception:
        return None

    if name not in names:
        return None

    try:
        if cmd.count_atoms(f"({name}) and solvent") > 0:
            return BaseType.SPECIAL
        if cmd.count_atoms(f"({name}) and polymer and nucleic") > 0:
            return BaseType.MACROMOLECULAR
        if cmd.count_atoms(f"({name}) and polymer and protein") > 0:
            return BaseType.MACROMOLECULAR
        if cmd.count_atoms(f"({name}) and polymer") > 0:
            return BaseType.MACROMOLECULAR
        total_atoms = cmd.count_atoms(f"({name})")
        if 0 < total_atoms <= 4:
            return BaseType.SPECIAL
    except Exception:
        return None

    return None


def _classify_with_heuristics(
    name: str,
    reps: dict,
    atom_colors: dict,
    atom_names: set,
) -> str:
    # heuristic 1: selection / chain pseudo-objects (no atoms, no reps)
    if not atom_colors and not any(reps.values()):
        return BaseType.CHAINS

    # heuristic 2: nucleic acid backbone atoms
    if atom_names & _NUCLEIC_ACID_ATOMS:
        return BaseType.MACROMOLECULAR

    # heuristic 3: water / ion objects by name
    name_upper = name.upper()
    if name_upper in _SOLVENT_RESIDUES or name_upper in _ION_RESIDUES:
        return BaseType.SPECIAL

    # heuristic 4: only one or two atoms total → likely a special/ion object
    if 0 < len(atom_colors) <= 4 and not reps.get("cartoon"):
        return BaseType.SPECIAL

    # heuristic 5: cartoon → macromolecule (protein chain)
    if reps.get("cartoon"):
        return BaseType.MACROMOLECULAR

    # heuristic 6: sticks / lines / nonbonded → organic small molecule
    if reps.get("sticks") or reps.get("lines") or reps.get("nonbonded"):
        return BaseType.ORGANIC

    return BaseType.INORGANIC


def _classify_object(obj_name: str, obj_data: dict) -> str:
    """Return a BaseType string for a PyMOL object.

    Classification order (first match wins):
      1. Chain-only selection objects  → BaseType.CHAINS
      2. Nucleic acid atoms present    → BaseType.MACROMOLECULAR
      3. Solvent residue atoms present → BaseType.SPECIAL  (water/ions)
      4. Cartoon representation active → BaseType.MACROMOLECULAR
      5. Sticks/lines/nonbonded only   → BaseType.ORGANIC
      6. Fallback                      → BaseType.INORGANIC
    """
    reps = obj_data.get("representations", {})
    atom_colors: dict = obj_data.get("atom_colors", {})

    # atom_colors keys are "chain|resi|atomname|alt"
    # extract unique atom names from the key set
    atom_names = set()
    for key in atom_colors:
        parts = key.split("|")
        if len(parts) >= 3:
            atom_names.add(parts[2])

    # Prefer selection-based classification when available
    if _HAVE_CMD:
        cmd_result = _classify_with_cmd(obj_name)
        if cmd_result:
            return cmd_result

    return _classify_with_heuristics(obj_name, reps, atom_colors, atom_names)


# ---------------------------------------------------------------------------
# PyMOL concrete controller
# ---------------------------------------------------------------------------

class PyMOLController(DBController):
    """Concrete DBController for the PyMOL backend.

    Knows how to read visual_system_state.json (produced by scene_control.py)
    and decompose it into the abstract schema understood by engine/controller.py.
    """

    def ingest_scene(self, filepath: str, name: str = None) -> int:
        """Parse a PyMOL visual_system_state export and persist it.

        The JSON structure produced by scene_control.export_visual_system_state:
          {
            "global_settings": {...},   → stored in scenes.meta
            "view_matrix":    [...],    → stored in scenes.view
            "viewport":       [...],    → stored in scenes.size
            "objects": {
              "<name>": {
                "object_matrix":       [...],
                "representations":     {...},
                "object_settings":     {...|null},
                "object_color_index":  int,
                "atom_colors":         {"chain|resi|atom|alt": color_index}
              },
              ...
            }
          }

        Parameters
        ----------
        filepath : str
            Path to the JSON export file (if provided) OR None to capture
            from the current live PyMOL session.
        name : str, optional
            Scene name for the database record.
        """
        # If filepath provided, load from JSON (legacy/debug path)
        if filepath:
            with open(filepath, "r") as f:
                doc = json.load(f)
            scene_name = name or Path(filepath).stem
        else:
            # Capture directly from live PyMOL session
            from . import scene
            doc = scene.export_visual_system_state()
            scene_name = name or "untitled_scene"

        meta = json.dumps(doc.get("global_settings", {}))
        view = json.dumps(doc.get("view_matrix", []))
        size = json.dumps(doc.get("viewport", []))

        scene_id = self.save_scene(scene_name, meta, view, size)

        for obj_name, obj_data in doc.get("objects", {}).items():
            base_type = _classify_object(obj_name, obj_data)
            payload = json.dumps(obj_data)
            self.store_object(scene_id, obj_name, base_type, payload)

        return scene_id
