"""pymol-backend/utils.py — GUI-selection detection and special-block building.

This module handles the detection of *user-defined GUI selections* that are
scoped below a full BaseType (e.g., an organic ligand captured as a named
selection, a chain subset, a hand-picked active-site residue range).

The result is the ``special`` block of a scene-object payload — a list of
entries, one per detected user selection:

    payload = {
        "macromolecular": {"atom_type_colors": {"CA": 11, ...}},
        "special": [
            # Each entry corresponds to one user-defined PyMOL selection
            # that overlaps this object's base_type but was stored separately.
            {
                "name":             "active_site_residues",   # selection name
                "base_type":        "macromolecular",         # parent chemistry
                "atom_type_colors": {"CA": 25},
                "ratio":            0.20,
                "distribution":     {"start": 0.80, "end": 1.0}
            },
            ...
        ]
    }

The ``special`` key is a **list** so that:
  - Multiple user selections within the same chemical category are all
    preserved (e.g., two active-site annotations on the same protein).
  - Each entry carries enough metadata to reconstruct the selection on a
    *different* structure via distribution-based positional mapping.

--------------------------------------------------------------------------
Relationship to BaseType semantics
--------------------------------------------------------------------------

SPECIAL has two distinct roles:

  1. Primary base_type  — The tool has no native selector for this object
     (CGO axes, nanomaterial, graphene sheet).  get_selector() returns "".
     No special-block logic applies here; the whole object is opaque.

  2. Payload subcategory  — The tool *does* recognise the base chemistry
     (polymer, organic, inorganic), but the user further partitioned the
     object into named selections inside PyMOL's GUI.  These sub-selections
     are detected here and stored as the ``special`` list so they can be
     replayed (approximately) on a different structure.

--------------------------------------------------------------------------
TODO: wire this module into the save/apply pipeline
--------------------------------------------------------------------------

The functions below are stubs.  They define the intended API and document
the algorithm.  They are intentionally *not* called from backend.py or
pymol_ops.py yet — scene reproduction is kept simple until the full
distribution-based replay is ready (see README.md § Future Work).

Activation checklist:
  □ Call detect_special_selections() inside PyMOLController.capture_scene()
    after building objects_data, passing each object's session entry and
    the already-resolved base_type.
  □ Merge returned list into the object's payload under the "special" key
    before handing off to make_scene_object().
  □ Uncomment the apply branch in pymol_ops.apply_scene() that iterates
    payload["special"] and calls reconstruct_special_selection().
  □ Add condenser.compress_payload() call to compress atom_colors before
    storage (engine/condenser.py — see .changelog-suggestion Phase 2).
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only for type hints — avoids hard PyMOL import at module level.
    pass

try:
    from pymol import cmd as _cmd
    _HAVE_CMD = True
except Exception:
    _cmd = None
    _HAVE_CMD = False


# ---------------------------------------------------------------------------
# Public API (stubs — not wired into pipeline yet)
# ---------------------------------------------------------------------------


def detect_special_selections(
    obj_name: str,
    base_type: str,
    session_entry: dict,
) -> list[dict]:
    """Detect user-defined GUI selections that sub-scope *obj_name*.

    For a given PyMOL object and its resolved base_type, scans the live
    session for named *selections* (not objects) whose atoms are a subset
    of this object.  Each qualifying selection becomes one entry in the
    returned ``special`` list.

    Parameters
    ----------
    obj_name : str
        Name of the parent PyMOL object (e.g., "9ax6").
    base_type : str
        Already-resolved BaseType constant for this object
        ("macromolecular", "organic", "inorganic", "special", "chains").
    session_entry : dict
        The per-object dict from ``cmd.get_session()["names"]`` for this
        object.  Passed in so the function stays testable without a live
        PyMOL session.

    Returns
    -------
    list[dict]
        Zero or more dicts, each with keys:
          ``name``             — selection name (user label, metadata only)
          ``base_type``        — parent BaseType (same as *base_type*)
          ``atom_type_colors`` — dict mapping atom_type → color_index
          ``ratio``            — fraction of parent object atoms in this sel.
          ``distribution``     — {``start``: float, ``end``: float} percentile
                                 range within the parent object's atom list
                                 sorted by residue number.

    Notes
    -----
    TODO: Implement.
      1. Call cmd.get_names("selections") to enumerate all named selections.
      2. For each selection, check if it is a proper subset of obj_name:
             cmd.count_atoms(f"({sel}) and ({obj_name})") == cmd.count_atoms(sel)
         and the count is > 0.
      3. Extract atom colors from session_entry (or iterate live session).
      4. Compute ratio = len(sel_atoms) / len(obj_atoms).
      5. Sort obj_atoms by resi, find index range covered by sel_atoms.
      6. Store distribution = {start: min_idx/total, end: max_idx/total}.
      7. Collect atom_type → dominant_color mapping for the selection.
    """
    # TODO: implement — return [] until wired in
    return []


def reconstruct_special_selection(
    entry: dict,
    parent_selector: str,
) -> None:
    """Replay one ``special`` list entry onto the current PyMOL structure.

    Uses the stored distribution percentiles to map the original selection's
    positional range onto the (possibly different) current structure.

    Parameters
    ----------
    entry : dict
        One item from ``payload["special"]``, as produced by
        ``detect_special_selections()``.
    parent_selector : str
        The PyMOL keyword for the parent BaseType (e.g., "polymer").
        Obtained from ``controller.get_selector(entry["base_type"])``.
        May be "" for SPECIAL/CHAINS — in that case reconstruct without
        a chemistry filter.

    Notes
    -----
    TODO: Implement.
      1. Build base selection: "name {atom_type} and {parent_selector}" (or
         just "name {atom_type}" when parent_selector == "").
      2. cmd.iterate(base_sel, "data.append((int(resi), ID))", ...)
      3. Sort by resi.  Map distribution["start"] / ["end"] to index range.
      4. Extract IDs in range → cmd.color(color_idx, f"ID {ids}").
      5. Optionally recreate the named selection:
             cmd.select(entry["name"], base_sel)
         so the user's label is available in the new session.

    IMPORTANT: Call after the dominant atom_type_colors pass in apply_scene
    so that special entries *override* (not get overridden by) the base coloring.
    """
    # TODO: implement — no-op until wired in
    pass


# ---------------------------------------------------------------------------
# Internal helpers (referenced by TODO implementations above)
# ---------------------------------------------------------------------------


def _build_atom_distribution(
    atom_entries: list[tuple[int, int]],
) -> dict[str, float]:
    """Given [(resi, atom_id), ...] sorted by resi, return percentile range.

    Parameters
    ----------
    atom_entries : list of (resi, atom_id)
        Atoms belonging to one selection, already sorted by residue number.
        The list must be a *sub-sequence* of the parent object's full atom
        list (same ordering by resi).

    Returns
    -------
    dict with ``start`` and ``end`` keys (normalised 0.0 – 1.0).

    Notes
    -----
    TODO: needs the parent object's total sorted atom list to convert
    absolute indices to percentiles.  Signature will be extended when
    implemented.
    """
    # TODO: implement
    return {"start": 0.0, "end": 1.0}


def _dominant_color_per_atom_type(
    atom_colors: dict[str, int],
    atom_ids: list[int],
) -> dict[str, int]:
    """Compute the dominant (most frequent) color per atom type for a subset.

    Parameters
    ----------
    atom_colors : dict
        Full mapping of ``"chain|resi|atom_type|alt"`` → color_index for
        the parent object (from the raw session entry).
    atom_ids : list of int
        PyMOL atom IDs belonging to this specific selection.

    Returns
    -------
    dict mapping atom_type → dominant_color_index.

    Notes
    -----
    TODO: implement using the same distribution analysis logic planned for
    engine/condenser.py so the two are consistent.
    """
    # TODO: implement
    return {}
