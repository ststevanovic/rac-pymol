"""pymol-backend/middleware.py — GUI-selection detection and special-block building.

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
the algorithm.  They are intentionally *not* called from adapter.py or
driver.py yet — scene reproduction is kept simple until the full
distribution-based replay is ready (see README.md § Future Work).

Activation checklist:
  □ Call detect_special_selections() inside PyMOLController.capture_scene()
    after building objects_data, passing each object's session entry and
    the already-resolved base_type.
  □ Merge returned list into the object's payload under the "special" key
    before handing off to make_scene_object().
  □ Uncomment the apply branch in driver.apply_scene() that iterates
    payload["special"] and calls reconstruct_special_selection().
  □ Add condenser.compress_payload() call to compress atom_colors before
    storage (engine/condenser.py — see .changelog-suggestion Phase 2).
"""

from __future__ import annotations

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
    session for named *selections* (not objects) whose atoms are a proper
    subset of this object.  Each qualifying selection becomes one entry in
    the returned ``special`` list — capturing its colour pattern and
    positional distribution so it can be replayed on a different structure.

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
        PyMOL session (unused in the live-session path).

    Returns
    -------
    list[dict]
        Zero or more dicts, each with keys:
          ``name``             — selection name (user label, metadata only)
          ``base_type``        — parent BaseType (same as *base_type*)
          ``atom_type_colors`` — dict mapping atom_type → dominant color_index
          ``ratio``            — fraction of parent object atoms in this sel.
          ``distribution``     — {``start``: float, ``end``: float} percentile
                                 range within the parent object's atom list
                                 sorted by residue number.
    """
    if not _HAVE_CMD or _cmd is None:
        return []

    cmd = _cmd

    try:
        parent_total = cmd.count_atoms(f"({obj_name})")
        if parent_total == 0:
            return []

        # Collect parent atoms sorted by resi for percentile computation
        parent_atoms: list[tuple[int, int]] = []  # (resi, ID)
        cmd.iterate(
            f"({obj_name})",
            "parent_atoms.append((int(resi), ID))",
            space={"parent_atoms": parent_atoms},
        )
        parent_atoms.sort(key=lambda x: x[0])
        parent_id_to_idx = {atom_id: i for i, (_, atom_id) in enumerate(parent_atoms)}

        results: list[dict] = []

        for sel_name in cmd.get_names("selections"):
            # Must be a proper non-empty subset of obj_name
            overlap = cmd.count_atoms(f"({sel_name}) and ({obj_name})")
            if overlap == 0 or overlap == parent_total:
                # Zero overlap — unrelated; full overlap — not a sub-selection
                continue
            if cmd.count_atoms(f"({sel_name})") != overlap:
                # Selection spans atoms outside this object too — skip
                continue

            # Collect (resi, atom_id, atom_type, color_index) for this selection
            sel_data: list[tuple[int, int, str, int]] = []
            cmd.iterate(
                f"({sel_name}) and ({obj_name})",
                "sel_data.append((int(resi), ID, name, color))",
                space={"sel_data": sel_data},
            )
            if not sel_data:
                continue

            ratio = len(sel_data) / parent_total

            # Compute positional distribution (percentiles within parent)
            sel_indices = sorted(
                parent_id_to_idx[atom_id]
                for _, atom_id, _, _ in sel_data
                if atom_id in parent_id_to_idx
            )
            if not sel_indices:
                continue
            distribution = {
                "start": round(sel_indices[0] / parent_total, 2),
                "end":   round(sel_indices[-1] / parent_total, 2),
            }

            # Dominant colour per atom_type for this selection
            atom_type_colors = _dominant_color_per_atom_type(
                atom_colors={},      # unused — we use sel_data directly
                atom_ids=[],         # unused
                _sel_data=sel_data,  # internal shortcut
            )

            results.append({
                "name":             sel_name,
                "base_type":        base_type,
                "atom_type_colors": atom_type_colors,
                "ratio":            round(ratio, 2),
                "distribution":     distribution,
            })

        return results

    except Exception:
        return []


def _apply_atom_type_slice(
    cmd,
    atom_type: str,
    color_idx: int,
    parent_selector: str,
    distribution: dict,
) -> None:
    """Paint a proportional slice of atoms for one atom_type + colour."""
    if parent_selector:
        base_sel = f"name {atom_type} and {parent_selector}"
    else:
        base_sel = f"name {atom_type}"
    atom_entries: list[tuple[int, int]] = []
    try:
        cmd.iterate(
            base_sel,
            "atom_entries.append((int(resi), ID))",
            space={"atom_entries": atom_entries},
        )
    except Exception:
        return
    if not atom_entries:
        return
    atom_entries.sort(key=lambda x: x[0])
    total = len(atom_entries)
    start_idx = int(total * distribution["start"])
    end_idx   = max(start_idx + 1, int(total * distribution["end"]))
    selected_ids = [atom_id for _, atom_id in atom_entries[start_idx:end_idx]]
    if not selected_ids:
        return
    try:
        id_sel = "ID " + "+".join(map(str, selected_ids))
        rgb = cmd.get_color_tuple(color_idx)
        cmd.color(rgb, id_sel)
    except Exception:
        pass


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
        ``detect_special_selections()``.  Must have keys:
          ``name``             — selection name to (re)create
          ``atom_type_colors`` — dict mapping atom_type → color_index
          ``distribution``     — {``start``: float, ``end``: float}
    parent_selector : str
        The PyMOL keyword for the parent BaseType (e.g., "polymer").
        Obtained from ``controller.get_selector(entry["base_type"])``.
        May be "" for SPECIAL/CHAINS — in that case the chemistry filter
        is omitted.
    """
    if not _HAVE_CMD or _cmd is None:
        return

    cmd = _cmd
    distribution = entry.get("distribution", {"start": 0.0, "end": 1.0})
    atom_type_colors: dict[str, int] = entry.get("atom_type_colors", {})
    sel_name: str = entry.get("name", "")

    for atom_type, color_idx in atom_type_colors.items():
        _apply_atom_type_slice(cmd, atom_type, color_idx, parent_selector, distribution)

    # Optionally recreate the named selection in the new session
    if sel_name:
        try:
            if parent_selector:
                cmd.select(sel_name, parent_selector)
            else:
                cmd.select(sel_name, "all")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Internal helpers (referenced by TODO implementations above)
# ---------------------------------------------------------------------------


def _build_atom_distribution(
    atom_entries: list[tuple[int, int]],
    parent_total: int,
) -> dict[str, float]:
    """Given [(resi, atom_id), ...] sorted by resi, return percentile range.

    Parameters
    ----------
    atom_entries : list of (resi, atom_id)
        Atoms belonging to one selection, already sorted by residue number.
    parent_total : int
        Total number of atoms in the parent object (denominator for percentile).

    Returns
    -------
    dict with ``start`` and ``end`` keys (normalised 0.0 – 1.0).
    """
    if not atom_entries or parent_total == 0:
        return {"start": 0.0, "end": 1.0}
    indices = [i for i, _ in enumerate(atom_entries)]
    return {
        "start": round(indices[0]  / parent_total, 2),
        "end":   round(indices[-1] / parent_total, 2),
    }


def _dominant_color_per_atom_type(
    atom_colors: dict[str, int],
    atom_ids: list[int],
    _sel_data: list[tuple[int, int, str, int]] | None = None,
) -> dict[str, int]:
    """Compute the dominant (most frequent) color per atom type for a subset.

    Parameters
    ----------
    atom_colors : dict
        Full mapping of ``"chain|resi|atom_type|alt"`` → color_index for
        the parent object.  Used when ``_sel_data`` is not provided.
    atom_ids : list of int
        PyMOL atom IDs belonging to this specific selection.  Used with
        ``atom_colors`` to filter relevant entries.
    _sel_data : list of (resi, ID, name, color), optional
        Pre-iterated selection data from a live ``cmd.iterate`` call.
        When provided, ``atom_colors`` / ``atom_ids`` are ignored.

    Returns
    -------
    dict mapping atom_type → dominant_color_index.
    """
    from collections import defaultdict, Counter

    counts: dict[str, Counter] = defaultdict(Counter)

    if _sel_data is not None:
        for _resi, _atom_id, atom_type, color_idx in _sel_data:
            counts[atom_type][color_idx] += 1
    else:
        for key, color_idx in atom_colors.items():
            parts = key.split("|")
            if len(parts) >= 3:
                atom_type = parts[2]
                counts[atom_type][color_idx] += 1

    return {
        atom_type: color_counter.most_common(1)[0][0]
        for atom_type, color_counter in counts.items()
        if color_counter
    }
